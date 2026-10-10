"""配置加载：config.toml（仓库外）+ 环境变量。

设计原则（隐私）：仓库内不得出现任何本机路径/口令/真名。
所有可变项从 ARCHIVE_CONFIG / ARCHIVE_DEPLOY_DIR 指向的外部文件与环境变量读取。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

if sys.version_info >= (3, 11):
    import tomllib as _toml
else:  # Python 3.9 / 3.10
    import tomli as _toml


def _bool(v: Any) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


# 服装单品类别兜底（配置里 [[wardrobe_categories]] 可覆盖）。
# 放在代码里只是为了让「配置还没更新」时功能不塌掉 —— 类别本身不是个人数据。
DEFAULT_WARDROBE_CATEGORIES: List[Dict[str, Any]] = [
    {"key": "top", "label": "上衣", "slot": "top"},
    {"key": "bottom", "label": "下装", "slot": "bottom"},
    {"key": "outer", "label": "外套/马甲", "slot": "outer"},
    {"key": "dress", "label": "裙装", "slot": "dress"},
    {"key": "shoes", "label": "鞋", "slot": "shoes"},
    {"key": "accessory", "label": "配饰", "slot": "accessory"},
    {"key": "bag", "label": "包", "slot": "bag"},
    {"key": "other", "label": "其他", "slot": "other"},
]


@dataclass
class Settings:
    app_title: str = "Kinship Archive"
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"

    host: str = "127.0.0.1"
    port: int = 8787
    token: str = ""

    deploy_dir: Path = field(default_factory=lambda: Path(".").resolve())
    config_path: Path | None = None

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "kinship_archive"
    db_user: str = "archive_app"
    db_password: str = ""

    media_dir: str = "media"
    max_upload_mb: int = 25
    thumbnail_max_px: int = 800
    keep_original: bool = True

    like_fallback_max_chars: int = 2

    daily_digest_time: str = "07:00"
    no_contact_days: int = 14
    upcoming_days: int = 10
    cycle_window_margin_days: int = 3
    todo_backlog_threshold: int = 5

    relation_types: List[Dict[str, Any]] = field(default_factory=list)
    modules: List[Dict[str, Any]] = field(default_factory=list)
    attribute_categories: List[Dict[str, Any]] = field(default_factory=list)
    # 服装：单品类别（key/label/slot）+ 归一化同义词表（去重判定用，人工可加）
    wardrobe_categories: List[Dict[str, Any]] = field(
        default_factory=lambda: list(DEFAULT_WARDROBE_CATEGORIES)
    )
    wardrobe_synonyms: List[List[str]] = field(default_factory=list)

    # ---- 派生 ----
    @property
    def media_path(self) -> Path:
        return (self.deploy_dir / self.media_dir).resolve()

    @property
    def dist_path(self) -> Path:
        return (self.deploy_dir / "dist").resolve()

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    def module(self, key: str) -> Dict[str, Any] | None:
        for m in self.modules:
            if m.get("key") == key:
                return m
        return None

    def default_modules_for(self, relation_type: str) -> List[str]:
        for rt in self.relation_types:
            if rt.get("key") == relation_type:
                return list(rt.get("default_modules") or [])
        return []

    def is_sensitive_module(self, key: str) -> bool:
        m = self.module(key)
        return bool(m and m.get("sensitivity") == "sensitive")

    # ---- 服装 ----
    def wardrobe_slot(self, category: str) -> str:
        """类别 → 穿搭槽位（排版用：上/下/外套/鞋/配饰…）。"""
        for c in self.wardrobe_categories:
            if c.get("key") == category:
                return str(c.get("slot") or category)
        return "other"

    def wardrobe_category_label(self, key: str) -> str:
        for c in self.wardrobe_categories:
            if c.get("key") == key:
                return str(c.get("label") or key)
        return key


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def load_dotenv(path: Path) -> int:
    """把 deploy/.env 读进 os.environ（不覆盖已存在的变量）。

    为什么需要：launchd 启动 uvicorn 时不会自动加载 .env，
    而口令只能由环境变量提供。返回值 = 加载的条目数。
    """
    if not path.is_file():
        return 0
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
            n += 1
    return n


def _default_deploy_dir() -> Path:
    """默认部署目录 = 仓库根的同级 deploy/（本方案里它在 git 工作区之外）。

    config.py 位于 <repo>/backend/config.py：
      parents[0] = backend, parents[1] = <repo>, parents[2] = <项目根>
    """
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root.parent / "deploy"


def load_settings() -> Settings:
    deploy_dir = Path(_env("ARCHIVE_DEPLOY_DIR", str(_default_deploy_dir()))).resolve()
    load_dotenv(deploy_dir / ".env")
    # .env 里可能又指定了部署目录，重新解析一次
    deploy_dir = Path(_env("ARCHIVE_DEPLOY_DIR", str(deploy_dir))).resolve()
    config_path = Path(_env("ARCHIVE_CONFIG", str(deploy_dir / "config.toml"))).resolve()

    data: Dict[str, Any] = {}
    if config_path.is_file():
        with open(config_path, "rb") as fh:
            data = _toml.load(fh)

    s = Settings(
        app_title=data.get("app_title", "Kinship Archive"),
        locale=data.get("locale", "zh-CN"),
        timezone=data.get("timezone", "Asia/Shanghai"),
        deploy_dir=deploy_dir,
        config_path=config_path if config_path.is_file() else None,
        relation_types=data.get("relation_types", []),
        modules=data.get("modules", []),
        attribute_categories=data.get("attribute_categories", []),
        wardrobe_categories=data.get("wardrobe_categories") or list(DEFAULT_WARDROBE_CATEGORIES),
        wardrobe_synonyms=data.get("wardrobe_synonyms", []) or [],
    )

    server = data.get("server", {})
    s.host = _env("ARCHIVE_HOST", str(server.get("host", s.host)))
    s.port = int(_env("ARCHIVE_PORT", str(server.get("port", s.port))))
    # 口令只从环境变量读（不进 config.toml，避免被误提交）
    s.token = _env("ARCHIVE_TOKEN", "")

    db = data.get("database", {})
    s.db_host = _env("ARCHIVE_DB_HOST", str(db.get("host", s.db_host)))
    s.db_port = int(_env("ARCHIVE_DB_PORT", str(db.get("port", s.db_port))))
    s.db_name = _env("ARCHIVE_DB_NAME", str(db.get("name", s.db_name)))
    s.db_user = _env("ARCHIVE_DB_USER", str(db.get("user", s.db_user)))
    s.db_password = _env("ARCHIVE_DB_PASSWORD", "")

    media = data.get("media", {})
    s.media_dir = str(media.get("dir", s.media_dir))
    s.max_upload_mb = int(media.get("max_upload_mb", s.max_upload_mb))
    s.thumbnail_max_px = int(media.get("thumbnail_max_px", s.thumbnail_max_px))
    s.keep_original = bool(media.get("keep_original", s.keep_original))

    search = data.get("search", {})
    s.like_fallback_max_chars = int(search.get("like_fallback_max_chars", s.like_fallback_max_chars))

    rem = data.get("reminder", {})
    s.daily_digest_time = str(rem.get("daily_digest_time", s.daily_digest_time))
    s.no_contact_days = int(rem.get("no_contact_days", s.no_contact_days))
    s.upcoming_days = int(rem.get("upcoming_days", s.upcoming_days))
    s.cycle_window_margin_days = int(rem.get("cycle_window_margin_days", s.cycle_window_margin_days))
    s.todo_backlog_threshold = int(rem.get("todo_backlog_threshold", s.todo_backlog_threshold))

    return s


settings = load_settings()
