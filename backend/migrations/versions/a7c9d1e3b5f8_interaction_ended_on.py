"""interaction ended_on（跨日相处的结束日）

Revision ID: a7c9d1e3b5f8
Revises: f1a2b3c4d5e6
Create Date: 2026-10-26

相处记录原来只有 occurred_on（单日）+ overnight 开关 + 手填 hours，
表达不了「周五去、周日回」这种跨度。这里只加一列：

- `ended_on NULL` = 单日，语义等价于 occurred_on；**不回填**，老数据零变化。
- 时间轴锚点仍是 occurred_on（events.event_date），ended_on 只描述跨度，
  不参与按日分组、不参与 date_from/date_to 过滤。

overnight 与 hours 的派生规则在应用层（routers/records.py），不在数据库里：
跨日 → overnight 真、hours 置空（多日折算成小时没有意义）。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c9d1e3b5f8"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("interactions", sa.Column("ended_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("interactions", "ended_on")
