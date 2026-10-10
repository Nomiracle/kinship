"""wardrobe items wears

Revision ID: c7a1f0b2d3e4
Revises: b104e103f161
Create Date: 2026-10-08 18:30:00.000000

服装「彻底版」：单品档案 + 穿搭↔单品引用。

去重的落点在这里：
  · wardrobe_items 唯一键 (person_id, category, name, color_key) —— 结构上建不出重复
  · merged_into_id 软删 —— 合并可回滚
  · outfit_wears 让「同一件被反复穿」变成多条引用，而不是重复的记录
"""
from alembic import op
import sqlalchemy as sa


revision = 'c7a1f0b2d3e4'
down_revision = 'b104e103f161'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'wardrobe_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=32), server_default='other', nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('color', sa.String(length=32), nullable=True),
        # 归一化色：唯一索引里不能放可空列（多个 NULL 互不相等 → 空色会绕过去重）
        sa.Column('color_key', sa.String(length=32), server_default='', nullable=False),
        sa.Column('tags', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('sensitivity', sa.String(length=16), server_default='normal', nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('merged_into_id', sa.Integer(), nullable=True),
        sa.Column('first_worn_on', sa.Date(), nullable=True),
        sa.Column('last_worn_on', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        # ★ 外键一律给名字：autogenerate 生成的 None 会让 downgrade 直接失败
        sa.ForeignKeyConstraint(['person_id'], ['persons.id'],
                                name='fk_wardrobe_items_person', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merged_into_id'], ['wardrobe_items.id'],
                                name='fk_wardrobe_items_merged_into', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person_id', 'category', 'name', 'color_key',
                            name='uq_wardrobe_item'),
    )
    op.create_index('ix_wardrobe_person_cat', 'wardrobe_items',
                    ['person_id', 'category', 'active'], unique=False)

    op.create_table(
        'outfit_wears',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('slot', sa.String(length=16), server_default='other', nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'],
                                name='fk_outfit_wears_event', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['item_id'], ['wardrobe_items.id'],
                                name='fk_outfit_wears_item', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'item_id', name='uq_outfit_wear'),
    )
    op.create_index('ix_outfit_wears_item', 'outfit_wears', ['item_id'], unique=False)

    # 单品照片：与 person_id / event_id 同一个多态挂载模式
    op.add_column('media', sa.Column('wardrobe_item_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_media_wardrobe_item', 'media', 'wardrobe_items',
                          ['wardrobe_item_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_media_wardrobe_item', 'media', ['wardrobe_item_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_media_wardrobe_item', table_name='media')
    op.drop_constraint('fk_media_wardrobe_item', 'media', type_='foreignkey')
    op.drop_column('media', 'wardrobe_item_id')
    op.drop_index('ix_outfit_wears_item', table_name='outfit_wears')
    op.drop_table('outfit_wears')
    op.drop_index('ix_wardrobe_person_cat', table_name='wardrobe_items')
    op.drop_table('wardrobe_items')
