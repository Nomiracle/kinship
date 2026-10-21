"""持久幂等键表 idempotency_keys

Revision ID: f1a2b3c4d5e6
Revises: b2f7c0a91d34
Create Date: 2026-10-21

增量迁移：新增 idempotency_keys，存储 Idempotency-Key →  fingerprint + response，
与新增衣物/事件/穿搭/媒体的写操作同事务提交，避免仅内存去重。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "b2f7c0a91d34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_idempotency_key"),
    )
    op.create_index("ix_idempotency_key", "idempotency_keys", ["idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idempotency_key", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
