"""person gender

Revision ID: d5e17b93a204
Revises: c7a1f0b2d3e4
Create Date: 2026-10-10 15:40:00.000000

性别字段（female/male/other，NULL = 未知）。

为什么要它：生理期模块跟性别强相关（男性不该有），而「伴侣」这一个关系类型里
两种性别都有 —— 光靠 relation_type 判不出来。规则本身在 config.Settings，
本迁移**只加列**：真人的性别属于数据，回填走仓库外的一次性脚本，不进这里。
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e17b93a204'
down_revision = 'c7a1f0b2d3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('persons', sa.Column('gender', sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column('persons', 'gender')
