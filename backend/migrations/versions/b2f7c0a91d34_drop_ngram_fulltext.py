"""drop ft_events_ngram（中文全文索引退役）

为什么删：
  ngram 分词器只有 MySQL 有，MariaDB 会直接报 `Function 'ngram' is not defined`
  —— 同一份代码在两套数据库上行为分叉，连迁移都跑不过（搬服务到 MariaDB 时实测）。
  档案量级在千条以内，检索统一走 LIKE（见 routers/insight.py 的 /api/search）。

注意：
  · 用 inspector 先查再删，不写 `DROP INDEX IF EXISTS` —— MySQL 8 不支持 IF EXISTS 语法。
  · downgrade 只重建**不带 parser** 的普通 FULLTEXT 索引：MariaDB 建不了 ngram 版，
    重建 ngram 版会让回滚在 MariaDB 上直接失败。

Revision ID: b2f7c0a91d34
Revises: e8b1c2d3f4a5
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f7c0a91d34"
down_revision: Union[str, None] = "e8b1c2d3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ft_events_ngram"


def upgrade() -> None:
    bind = op.get_bind()
    names = {ix["name"] for ix in sa.inspect(bind).get_indexes("events")}
    if INDEX_NAME in names:
        op.drop_index(INDEX_NAME, table_name="events")


def downgrade() -> None:
    bind = op.get_bind()
    names = {ix["name"] for ix in sa.inspect(bind).get_indexes("events")}
    if INDEX_NAME not in names:
        op.create_index(INDEX_NAME, "events", ["title", "body"], unique=False,
                        mysql_prefix="FULLTEXT")
