"""SQLAlchemy 引擎与会话。

约定（务必遵守）：
  · 字符集 utf8mb4（中文 + emoji）
  · 会话时区固定 UTC（服务器亦为 +00:00），DATETIME 一律存 UTC 瞬时
  · DATE 列存「本地日期语义」（生日、生理期、事件发生日），不带时区
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from fastapi import Request
from fastapi.routing import APIRoute

from .config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)


@event.listens_for(engine, "connect")
def _set_session_vars(dbapi_conn, _record):  # pragma: no cover - 基础设施
    cur = dbapi_conn.cursor()
    cur.execute("SET time_zone = '+00:00'")
    cur.execute("SET NAMES utf8mb4")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class CommitRoute(APIRoute):
    """保证写操作在**响应发出之前**提交。

    为什么必须这么做：FastAPI 的 yield 依赖（session 生命周期）清理运行在响应
    发出之后，于是「DELETE 返回 204，紧接着 GET 仍能看到那条」—— 冒烟测试里
    真实复现过。前端删完立刻刷新列表会看到幽灵数据，很难查。
    """

    def get_route_handler(self):
        original = super().get_route_handler()

        async def custom_handler(request):  # type: ignore[no-untyped-def]
            response = await original(request)
            session = getattr(request.state, "archive_session", None)
            if session is not None:
                try:
                    if session.in_transaction():
                        session.commit()
                except Exception:
                    session.rollback()
                    raise
            return response

        return custom_handler


@contextmanager
def session_scope() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI 依赖。会话挂到 request.state，交给 CommitRoute 提交。"""
    s = SessionLocal()
    request.state.archive_session = s
    try:
        yield s
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ping() -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar() == 1
