"""公共路由（无需口令）。"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
def health(session: Session = Depends(get_session)):
    """launchd / 反向代理就绪探针，也可用来排查「服务没起来」。"""
    db_ok = True
    db_error = None
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - 运维路径
        db_ok = False
        db_error = str(exc)[:200]
    return {
        "ok": db_ok,
        "app": settings.app_title,
        "version": "0.1.0",
        "server_time": dt.datetime.now().isoformat(timespec="seconds"),
        "timezone": settings.timezone,
        "database": {"ok": db_ok, "name": settings.db_name, "error": db_error},
        "auth_required": bool(settings.token),
        "config_loaded": bool(settings.config_path),
        "deploy_dir": str(settings.deploy_dir),
        "dist_present": settings.dist_path.is_dir(),
    }
