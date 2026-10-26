"""衣橱单品的状态 / 状态原因 / 变更历史 / 替换关系

Revision ID: c4e8f1a2b6d9
Revises: a7c9d1e3b5f8
Create Date: 2026-10-26 18:20:00.000000

为什么：
  · 原来只有 `active` 布尔（= 停用/恢复），说不出「卖掉、送人、丢了、闲置」，
    也没有原因与日期 —— 而「这条项链卖掉了，换了一条项链 + 一枚戒指」恰恰是
    衣橱最常见的真实叙事。
  · `created_at` 一直存在但从没出参；而且它取的是 DB 的 CURRENT_TIMESTAMP：
    生产 MariaDB 宿主是 UTC，本机 MySQL 是 +08 —— 同一段代码两处跑会差 8 小时。

本迁移做四件事：
  1. wardrobe_items 加 status / status_reason / status_changed_on / replaces_item_id；
  2. 新建 wardrobe_item_status_log（每次状态变更追加一行，原因不被覆盖）；
  3. 撒掉 active：状态成为唯一事实源（active 改由 status 派生，见 router）；
     唯一键与索引把 status 纳入 —— 卖掉旧项链后，同名的「新项链」必须建得出来；
  4. 把已有的 created_at/updated_at 归一到**本地墙钟**（= 8h − 数据库时区偏移，
     于是生产 UTC 库 +8、本机 +08 库 +0，两边口径一致）。此后由 Python 写入。
"""
from alembic import op
import sqlalchemy as sa


revision = "c4e8f1a2b6d9"
down_revision = "a7c9d1e3b5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wardrobe_items",
        sa.Column("status", sa.String(length=16), server_default="in_use", nullable=False),
    )
    op.add_column("wardrobe_items", sa.Column("status_reason", sa.String(length=255), nullable=True))
    op.add_column("wardrobe_items", sa.Column("status_changed_on", sa.Date(), nullable=True))
    op.add_column("wardrobe_items", sa.Column("replaces_item_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_wardrobe_items_replaces", "wardrobe_items", "wardrobe_items",
        ["replaces_item_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "wardrobe_item_status_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("effective_on", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["wardrobe_items.id"],
                                name="fk_wardrobe_status_log_item", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wardrobe_status_log_item", "wardrobe_item_status_log",
                    ["item_id", "id"], unique=False)

    # 已有单品补一条初始状态（生效日取加入日期）——历史从第一天起就是完整的
    op.execute(sa.text(
        "INSERT INTO wardrobe_item_status_log (item_id, status, reason, effective_on, created_at, source) "
        "SELECT id, 'in_use', NULL, DATE(created_at), created_at, 'migrate' FROM wardrobe_items"
    ))

    # created_at/updated_at 归一到本地墙钟：偏移 = 8h − DB 自己的时区偏移
    bind = op.get_bind()
    offset = bind.execute(sa.text(
        "SELECT 8 - TIMESTAMPDIFF(HOUR, UTC_TIMESTAMP(), NOW())"
    )).scalar()
    if offset:
        bind.execute(sa.text(
            "UPDATE wardrobe_items "
            "SET created_at = DATE_ADD(created_at, INTERVAL :h HOUR), "
            "    updated_at = DATE_ADD(updated_at, INTERVAL :h HOUR)"
        ), {"h": int(offset)})

    # 唯一键与索引：把 status 纳入，同时去掉 active。
    # ★ 顺序有讲究：MySQL 不允许删掉「外键还靠着」的索引 ——
    #   uq_wardrobe_item 的左列 person_id 正好在替 fk_wardrobe_items_person 撑索引，
    #   所以先建一个临时索引顶上，再换唯一键，最后才删旧索引。
    op.create_index("ix_wardrobe_person_cat_tmp", "wardrobe_items",
                    ["person_id", "category", "status"], unique=False)
    op.drop_constraint("uq_wardrobe_item", "wardrobe_items", type_="unique")
    op.create_unique_constraint(
        "uq_wardrobe_item", "wardrobe_items",
        ["person_id", "category", "name", "color_key", "status"],
    )
    op.drop_index("ix_wardrobe_person_cat", table_name="wardrobe_items")
    op.create_index("ix_wardrobe_person_cat", "wardrobe_items",
                    ["person_id", "category", "status"], unique=False)
    op.drop_index("ix_wardrobe_person_cat_tmp", table_name="wardrobe_items")
    op.drop_column("wardrobe_items", "active")


def downgrade() -> None:
    op.add_column(
        "wardrobe_items",
        sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.execute(sa.text(
        "UPDATE wardrobe_items SET active = (status IN ('in_use', 'idle') "
        "AND merged_into_id IS NULL)"
    ))
    op.create_index("ix_wardrobe_person_cat_tmp", "wardrobe_items",
                    ["person_id", "category", "active"], unique=False)
    op.drop_constraint("uq_wardrobe_item", "wardrobe_items", type_="unique")
    op.create_unique_constraint(
        "uq_wardrobe_item", "wardrobe_items",
        ["person_id", "category", "name", "color_key"],
    )
    op.drop_index("ix_wardrobe_person_cat", table_name="wardrobe_items")
    op.create_index("ix_wardrobe_person_cat", "wardrobe_items",
                    ["person_id", "category", "active"], unique=False)
    op.drop_index("ix_wardrobe_person_cat_tmp", table_name="wardrobe_items")

    op.drop_index("ix_wardrobe_status_log_item", table_name="wardrobe_item_status_log")
    op.drop_table("wardrobe_item_status_log")
    op.drop_constraint("fk_wardrobe_items_replaces", "wardrobe_items", type_="foreignkey")
    op.drop_column("wardrobe_items", "replaces_item_id")
    op.drop_column("wardrobe_items", "status_changed_on")
    op.drop_column("wardrobe_items", "status_reason")
    op.drop_column("wardrobe_items", "status")
