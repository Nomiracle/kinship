"""媒体（图片/视频）上传与管理。

文件本体在 deploy/media/（仓库之外），数据库只存相对路径。
"""
from __future__ import annotations

import datetime as dt
import mimetypes
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import CommitRoute, get_session
from ..models import Event, Media, Person, WardrobeItem
from ..schemas import MediaOut
from ..services import media as media_svc
from ..services.audit import write_audit

router = APIRouter(prefix="/api", tags=["media"], route_class=CommitRoute)


def _out(m: Media, names: dict) -> dict:
    return {
        "id": m.id,
        "person_id": m.person_id,
        "person_name": names.get(m.person_id),
        "event_id": m.event_id,
        "wardrobe_item_id": m.wardrobe_item_id,
        "kind": m.kind,
        "path": m.path,
        "source_path": m.source_path,
        "thumb_path": m.thumb_path,
        "original_name": m.original_name,
        "mime": m.mime,
        "bytes": m.bytes,
        "captured_on": m.captured_on,
        "created_at": m.created_at,
    }


def _own(col, value):
    """归属列比对：None 必须是 IS NULL —— 写成 `= NULL` 永远不成立（会漏判重复）。"""
    return col.is_(None) if value is None else col == value


def _find_same_upload(session: Session, rel: str, person_id: Optional[int],
                      event_id: Optional[int],
                      wardrobe_item_id: Optional[int]) -> Optional[Media]:
    """这张图 + 这个归属是不是已经录过？用于上传幂等（重复上传不再插新行）。

    文件名 = 「日期 + 内容哈希」，所以同内容重复上传落在同一个相对路径上；
    HEIC 转码后 path 是 .jpg、原图记在 source_path 里 → 两边都要比。
    只有磁盘文件还在时才复用：文件被手工删过时宁可新建一行，也不留破图引用。
    """
    cands = {rel}
    if Path(rel).suffix.lower() in media_svc.SIPS_CONVERT:
        cands.add(str(Path(rel).with_suffix(".jpg")))
    row = session.scalar(
        select(Media).where(
            or_(Media.path.in_(cands), Media.source_path.in_(cands)),
            _own(Media.person_id, person_id),
            _own(Media.event_id, event_id),
            _own(Media.wardrobe_item_id, wardrobe_item_id),
        )
    )
    if row is None:
        return None
    return row if (settings.media_path / row.path).is_file() else None


@router.get("/media", response_model=List[MediaOut])
def list_media(person_id: Optional[int] = None, event_id: Optional[int] = None,
               wardrobe_item_id: Optional[int] = None,
               limit: int = Query(200, ge=1, le=1000),
               session: Session = Depends(get_session)):
    stmt = select(Media).order_by(desc(Media.captured_on), desc(Media.id))
    if person_id:
        stmt = stmt.where(Media.person_id == person_id)
    if event_id:
        stmt = stmt.where(Media.event_id == event_id)
    if wardrobe_item_id:
        stmt = stmt.where(Media.wardrobe_item_id == wardrobe_item_id)
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    return [_out(m, names) for m in session.scalars(stmt.limit(limit))]


@router.post("/media", response_model=List[MediaOut], status_code=201)
async def upload_media(
    file: List[UploadFile] = File(...),
    person_id: Optional[int] = Form(None),
    event_id: Optional[int] = Form(None),
    wardrobe_item_id: Optional[int] = Form(None),
    captured_on: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    """一次可传多张。手机直传的 HEIC 会自动转 JPG，并统一生成缩略图。"""
    if person_id and not session.get(Person, person_id):
        raise HTTPException(404, "找不到这个人")
    if event_id and not session.get(Event, event_id):
        raise HTTPException(404, "找不到该记录")
    if wardrobe_item_id and not session.get(WardrobeItem, wardrobe_item_id):
        raise HTTPException(404, "找不到该单品")

    cap: Optional[dt.date] = None
    if captured_on:
        try:
            cap = dt.date.fromisoformat(captured_on)
        except ValueError:
            raise HTTPException(400, "captured_on 需为 YYYY-MM-DD")

    created: List[Media] = []
    for up in file:
        data = await up.read()
        if not data:
            continue
        try:
            rel, ext, size = media_svc.save_upload(data, up.filename or "", )
        except media_svc.MediaError as exc:
            raise HTTPException(400, str(exc))

        # ★ 同一张图重复上传（用户连点「上传」、网络重试、同一张全身照先挂事件又挂单品）：
        #   文件名 = 日期 + 内容哈希 → 同内容 + 同归属必然落在同一个 path 上。
        #   这时**复用已有那行**，不再插新行：否则相册里同一张图出现多次，
        #   删除时还会互相牵连（多行共用同一个磁盘文件，见 delete_media 的注释）。
        dup = _find_same_upload(session, rel, person_id, event_id, wardrobe_item_id)
        if dup is not None:
            created.append(dup)
            continue

        kind = "video" if ext in media_svc.VIDEO_EXTS else "image"
        display_rel = rel
        source_rel = None
        if kind == "image":
            display_rel, source_rel = media_svc.convert_heic(rel)
        thumb = media_svc.make_thumbnail(display_rel) if kind == "image" else None
        w, h = media_svc.dimensions(thumb or display_rel) if kind == "image" else (None, None)

        row = Media(
            person_id=person_id,
            event_id=event_id,
            wardrobe_item_id=wardrobe_item_id,
            kind=kind,
            path=display_rel,
            source_path=source_rel,
            thumb_path=thumb,
            original_name=up.filename,
            mime=mimetypes.guess_type(display_rel)[0] or up.content_type,
            bytes=size,
            captured_on=cap or dt.date.today(),
        )
        session.add(row)
        session.flush()
        write_audit(session, "media", row.id, "create")
        created.append(row)

    if not created:
        raise HTTPException(400, "没有可用的文件")
    session.flush()
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    return [_out(m, names) for m in created]


@router.delete("/media/{media_id}", status_code=204)
def delete_media(media_id: int, session: Session = Depends(get_session)):
    row = session.get(Media, media_id)
    if not row:
        raise HTTPException(404, "找不到该媒体")
    # ★ 文件名 = 时间戳 + 内容哈希 → 同内容的两条记录会**共用同一个文件**。
    #   删之前必须先看还有没有别的行引用它，否则会把别人的图一起删掉（真踩过：
    #   一条日记的图被测试上传的删除操作连带删掉，页面直接破图）。
    others = session.scalars(select(Media).where(Media.id != media_id)).all()
    referenced = set()
    for o in others:
        for v in (o.path, o.thumb_path, o.source_path):
            if v:
                referenced.add(v)
    media_svc.delete_files(*[p for p in (row.path, row.thumb_path, row.source_path)
                             if p and p not in referenced])
    session.delete(row)
    write_audit(session, "media", media_id, "delete")
    return None


@router.get("/media/storage")
def storage_info():
    """给「设置」页看的用量概览。"""
    root = settings.media_path
    files = 0
    total = 0
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file():
                files += 1
                total += p.stat().st_size
    return {
        "dir": str(root),
        "files": files,
        "bytes": total,
        "mb": round(total / 1024 / 1024, 1),
        "max_upload_mb": settings.max_upload_mb,
        "thumbnail_max_px": settings.thumbnail_max_px,
        "sips_available": media_svc._sips() is not None,
    }
