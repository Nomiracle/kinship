"""图片/视频落盘与缩略图。

设计：
  · 文件写进 deploy/media/YYYY/MM/（仓库之外），文件名由服务端生成，杜绝路径穿越
  · 图片处理用 **Pillow**（+ pillow-heif 解 HEIC）：HEIC/WebP → JPG、等比缩放到 <= N px
    ★ 不用 macOS 的 `sips`：它只在 macOS 存在，服务搬到 Linux 后缩略图与 HEIC 转码会**静默失效**
      （大图不缩、iPhone 原图直接进库，安卓/Chrome 打不开）。Pillow 两端行为一致，
      而且它跟代码一起走（同一份 requirements.txt），换机器不用另外装系统包。
  · 没装 Pillow 时所有图片处理降级为「原样返回」，绝不因此丢文件或让上传失败
  · 原图默认保留（keep_original=true），缩略图糊了还能回原图
  · 数据库只存相对路径，换机器/搬目录不用改数据
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Optional, Tuple

from ..config import settings

try:  # Pillow 是运行依赖，但缺了也不该让服务起不来
    from PIL import Image, ImageOps

    _PIL_OK = True
except Exception:  # pragma: no cover - 只在缺依赖的环境触发
    Image = ImageOps = None  # type: ignore[assignment]
    _PIL_OK = False

_HEIF_OK = False
if _PIL_OK:
    try:
        import pillow_heif

        # 注册后 Image.open 能直接读 .heic/.heif（iPhone 直传的原图）
        pillow_heif.register_heif_opener()
        _HEIF_OK = True
    except Exception:  # pragma: no cover
        _HEIF_OK = False

# 等比缩放要用的重采样滤镜（Pillow 10 起搬到 Image.Resampling；标 Any 只为免去可空包裹）
_RESAMPLE: Any = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1) if _PIL_OK else 1

# 只认这些扩展名（其余一律拒绝，避免把任意文件塞进媒体目录）
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS

# 需要转成 JPG 才能给浏览器看的格式（HEIC 只有 Safari 认）
TRANSCODE_EXTS = {".heic", ".heif", ".webp"}


class MediaError(Exception):
    pass


def image_backend() -> Optional[str]:
    """当前图片处理后端（`/api/media/storage` 与设置页用它自检）。

    None = 没装 Pillow：缩略图与 HEIC 转码会静默跳过，上传仍然成功（只是没缩略图）。
    """
    if not _PIL_OK:
        return None
    return "pillow+heif" if _HEIF_OK else "pillow"


def extension_of(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext == ".heif":
        ext = ".heic"
    return ext


def sniff_kind(data: bytes) -> Optional[str]:
    """按**内容**（魔数）判断真实类型。

    后缀是可以骗人的：2026-10 导入的日记导出里有一批「.jpg/.jpeg/.png 外壳、里面其实是 HEIC」，
    按后缀判断就不会走转码，前端拿到的是"浏览器解不开的 jpg" = 破图。所以判定一律以内容为准。
    """
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis", b"hevm", b"hevs"):
            return "heic"
        return "video"          # mp4/mov 家族（ftyp 但品牌不是 HEIC 系）
    return None


def save_upload(data: bytes, original_name: str, kind_hint: str = "image") -> Tuple[str, str, int]:
    """把上传内容写到 media/YYYY/MM/，返回 (相对路径, 扩展名, 字节数)。"""
    ext = extension_of(original_name)
    if ext not in ALLOWED_EXTS:
        raise MediaError("不支持的文件类型：%s（允许：%s）" % (
            ext or "无扩展名", "、".join(sorted(ALLOWED_EXTS))))
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise MediaError("文件超过 %d MB 上限" % settings.max_upload_mb)

    # 后缀不可信：内容确实 HEIC 却挂着 .jpg/.jpeg/.png 的，按 .heic 存，
    # 这样后面的 convert_heic 才会真的转码（否则浏览器拿到 HEIC 外壳的 jpg = 破图）
    if sniff_kind(data) == "heic" and ext in {".jpg", ".jpeg", ".png"}:
        ext = ".heic"

    today = dt.date.today()
    rel_dir = Path("%04d" % today.year) / ("%02d" % today.month)
    abs_dir = settings.media_path / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha1(data).hexdigest()[:10]
    name = "%s-%s%s" % (today.strftime("%Y%m%d"), digest, ext)
    target = abs_dir / name
    target.write_bytes(data)
    return str(rel_dir / name), ext, len(data)


def convert_heic(rel_path: str) -> Tuple[str, Optional[str]]:
    """HEIC/HEIF/WebP → JPG（iPhone 直传的原图）。

    返回 (展示用相对路径, 原始文件相对路径或 None)。
    转换失败或没有 Pillow 时原样返回输入路径，绝不因此丢文件。
    """
    ext = Path(rel_path).suffix.lower()
    if ext not in TRANSCODE_EXTS or not _PIL_OK:
        return rel_path, None
    assert Image is not None and ImageOps is not None  # _PIL_OK 已保证；此处只为类型收窄
    src = settings.media_path / rel_path
    dst = src.with_suffix(".jpg")
    try:
        with Image.open(src) as im:
            # EXIF 方向要先应用，否则 iPhone 竖拍的照片在网页里是躺着的
            im = ImageOps.exif_transpose(im) or im
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.save(dst, format="JPEG", quality=88)
    except Exception:
        return rel_path, None
    display = str(Path(*Path(rel_path).parts[:-1]) / dst.name)
    if settings.keep_original:
        return display, rel_path
    src.unlink(missing_ok=True)
    return display, None


def make_thumbnail(rel_path: str) -> Optional[str]:
    """等比缩到 <= thumbnail_max_px，输出到同目录 thumbs/。

    ★ 如果原图本来就小于阈值，直接返回 None（前端会回退用原图）——
      放大到目标尺寸只会更糊、白占空间（sips 时代真踩过）。
    """
    if not _PIL_OK:
        return None
    assert Image is not None and ImageOps is not None  # _PIL_OK 已保证；此处只为类型收窄
    src = settings.media_path / rel_path
    if not src.is_file() or src.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    w, h = dimensions(rel_path)
    if w and h and max(w, h) <= settings.thumbnail_max_px:
        return None
    thumb_dir = settings.media_path / Path(*Path(rel_path).parts[:-1]) / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    dst = thumb_dir / src.name
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im) or im
            im.thumbnail((settings.thumbnail_max_px, settings.thumbnail_max_px), _RESAMPLE)
            # ★ 显式指定输出格式（跟 sips 时代的坑同源）：沿用输入格式会让 HEIC 写出 HEIC 字节
            #   挂 .jpg 名字 —— 前端破图。PNG 走 PNG（保住透明通道），其余一律 JPEG。
            if src.suffix.lower() == ".png":
                if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    im = im.convert("RGBA")
                im.save(dst, format="PNG", optimize=True)
            else:
                if im.mode != "RGB":
                    im = im.convert("RGB")
                im.save(dst, format="JPEG", quality=85)
    except Exception:
        return None
    return str(Path(*Path(rel_path).parts[:-1]) / "thumbs" / src.name)


def dimensions(rel_path: str) -> Tuple[Optional[int], Optional[int]]:
    if not _PIL_OK:
        return None, None
    assert Image is not None  # _PIL_OK 已保证；此处只为类型收窄
    src = settings.media_path / rel_path
    try:
        with Image.open(src) as im:
            return im.width, im.height
    except Exception:
        return None, None


def delete_files(*rel_paths: Optional[str]) -> None:
    """删媒体文件：本体、缩略图、转换前的原图。

    兜底：同名不同扩展（同一 sha1 stem）的兄弟文件也一并清掉 ——
    历史数据可能没有记录 source_path，不删就留永久垃圾。
    """
    root = settings.media_path
    for rel in rel_paths:
        if not rel:
            continue
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)):
            continue
        if target.is_file():
            target.unlink(missing_ok=True)
        thumb = target.parent / "thumbs" / target.name
        if thumb.is_file():
            thumb.unlink(missing_ok=True)
        # 同 stem 的其它扩展（如保留下来的 .heic 原图）
        for sibling in target.parent.glob(target.stem + ".*"):
            if sibling.is_file() and sibling.name != target.name:
                sibling.unlink(missing_ok=True)
