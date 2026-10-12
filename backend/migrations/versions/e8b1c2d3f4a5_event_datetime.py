"""events.event_date 精确到秒（DATE → DATETIME）

Revision ID: e8b1c2d3f4a5
Revises: d5e17b93a204
Create Date: 2026-10-12 12:10:00.000000

为什么：原来只精确到日，同一天发生的多件事分不出先后，时间轴排序只能靠 id。
改成 DATETIME 后同一天内按时刻倒序；**时间部分 00:00:00 = 「只记到日」**
（历史数据全部落在这个形态上，不猜时间、不假造时刻）。

- 旧值 `'2026-10-12'` → `'2026-10-12 00:00:00'`，MySQL 自己补零，无损；
- 索引不用重建（B-tree 照旧），扇出表（cycle_records / interactions / media.captured_on）
  仍是 DATE —— 那些是「日」的语义，数据取 .date() 即可。
- 回滚会把时间截掉，所以 downgrade 前先备份（ops/backup.sh）。
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8b1c2d3f4a5'
down_revision = 'd5e17b93a204'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'events', 'event_date',
        existing_type=sa.Date(), type_=sa.DateTime(),
        existing_nullable=False, existing_server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        'events', 'event_date',
        existing_type=sa.DateTime(), type_=sa.Date(),
        existing_nullable=False, existing_server_default=None,
    )
