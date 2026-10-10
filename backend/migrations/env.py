"""Alembic 环境：连接串从 deploy/.env + deploy/config.toml 组装（仓库内无口令）。

Python 3.9 兼容：不用 PEP 604 语法。
"""
from __future__ import annotations

import pathlib
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# 让 `backend` 可导入（从仓库根运行 alembic 时也成立）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from backend.config import settings  # noqa: E402
from backend.db import Base  # noqa: E402
import backend.models  # noqa: E402,F401  —— 必须导入以注册全部表

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
