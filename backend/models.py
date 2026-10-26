"""通用关系档案 —— 数据模型。

核心思想：**人（person）为中心 + 统一事件时间轴 + 模块按人开关**。
「伴侣 / 家人 / 朋友 / 同事」共用同一套表，差异只体现在
`relation_type` 与 `person_modules` 的开关上，而不是各建一套表。

本文件不含任何个人数据（仓库公开）。

★ Python 3.9 兼容：注解一律用 Optional[...]，不写 `X | None`
  —— SQLAlchemy 会 eval 注解字符串，PEP 604 语法在 3.9 上直接 TypeError。
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

RELATION_TYPES = ("self", "partner", "family", "friend", "colleague")
# 性别：决定「默认自动开哪些模块」以及生理期这类模块对谁可见（见 config.Settings）。
# NULL = 未知 —— 未知性别不自动开敏感模块，但允许手动开（不阻塞任何历史数据）。
GENDERS = ("female", "male", "other")


class Person(Base):
    """被维护的对象。用户自己也是一条记录（is_self=1），
    这样礼物方向、双人事件、相处记录都天然对称。"""

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="friend")
    is_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 性别（female/male/other；NULL = 未知）。生理期模块只对女性可见/可开，
    # 「伴侣 + 女」新建时自动开 —— 规则在 config.Settings.default_modules_for /
    # gender_allows_module，别在别处再写一份。
    gender: Mapped[Optional[str]] = mapped_column(String(16))

    birthday: Mapped[Optional[dt.date]] = mapped_column(Date)
    birthday_lunar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lunar_month: Mapped[Optional[int]] = mapped_column(Integer)
    lunar_day: Mapped[Optional[int]] = mapped_column(Integer)
    lunar_leap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    aliases: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- 圈子视角：解决「她是她的圈子的人，而我只是间接认识」这类问题 ---
    # 为什么不用新增 relation_type 表达：同一个人可以同时在两个圈里（共同朋友），
    # 而 relation_type 只有一个值。circle 描述「从谁的视角认识」，具体关系交给
    # person_relations 那张图（可多条边）。
    circle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="self", server_default="self"
    )
    # 熟悉度：1 只闻其名 / 2 见过 / 3 常见 / 4 很熟（int 便于排序与统计）
    familiarity: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    # 通过谁认识（指向另一个人；删除中间人时置空而不是连带删除）
    via_person_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL")
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    modules: Mapped[List["PersonModule"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    attributes: Mapped[List["Attribute"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_persons_active", "active", "relation_type"),)


class PersonRelation(Base):
    """人与人之间的关系边：支撑「三姥爷」「大舅的妻子」这类关系网。"""

    __tablename__ = "person_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    to_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint("from_person_id", "to_person_id", "label", name="uq_relation_edge"),
    )


class PersonModule(Base):
    """模块开关：同一个人开哪些功能（生理期/服装/相处/礼物…）。"""

    __tablename__ = "person_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    module_key: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    person: Mapped[Person] = relationship(back_populates="modules")

    __table_args__ = (UniqueConstraint("person_id", "module_key", name="uq_person_module"),)


class Attribute(Base):
    """每人的属性 KV（喜欢 / 忌口 / 常喝 / 工作 / 雷区…），分类由配置定义。"""

    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    person: Mapped[Person] = relationship(back_populates="attributes")

    __table_args__ = (Index("ix_attributes_person_cat", "person_id", "category"),)


class EventType(Base):
    """事件类型注册表（text/outfit/period/meeting/gift/health/mood/milestone/contact）。"""

    __tablename__ = "event_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Event(Base):
    """统一时间轴：四类记录都在这里，靠 type_key 区分。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    type_key: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    # ★ 发生时刻（本机墙钟，Asia/Shanghai），精确到秒。用 DATETIME 而不是 TIMESTAMP：
    #   本库 @@time_zone=+00:00，TIMESTAMP 会被会话时区换算。
    #   时间部分为 00:00:00 = 「只记到日」（历史数据与「记到某一天」的场景），
    #   界面据此决定要不要显示时分（见 schemas.parse_event_at / 前端 lib/event-day.js）。
    event_date: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    body: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(255))
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="web")

    @property
    def event_day(self) -> dt.date:
        """只到「日」的部分。

        扇出明细（cycle_records.start_date / interactions.occurred_on / 图片拍摄日）与
        生日倒计时这类「按天」的语义都用它 —— 直接拿 event_date(datetime) 去比 DATE 列
        会漏配（踩坑 34/35：时间轴与统计会从此刻开始悄悄分叉）。
        """
        return self.event_date.date()

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_events_person_date", "person_id", "event_date"),
        Index("ix_events_type_date", "type_key", "event_date"),
        # ★ 这里没有中文全文索引：ngram parser 只有 MySQL 有，MariaDB 会直接报
        #   `Function 'ngram' is not defined` —— 同一份代码在两套数据库上行为分叉。
        #   检索统一走 LIKE（见 routers/insight.py 的 /api/search，档案量级下开销可忽略）。
    )


class EventPerson(Base):
    """多人事件（家庭聚会、双人开黑）。"""

    __tablename__ = "event_persons"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )


class Media(Base):
    """多态挂载的图片/视频。文件本体在 deploy/media/（仓库之外）。"""

    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    # 单品照片（同一个多态挂载模式；单品被合并/删除时置空而不是连带删图）
    wardrobe_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="image")
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    thumb_path: Mapped[Optional[str]] = mapped_column(String(255))
    original_name: Mapped[Optional[str]] = mapped_column(String(255))
    mime: Mapped[Optional[str]] = mapped_column(String(64))
    bytes: Mapped[Optional[int]] = mapped_column(Integer)
    # 转换前的原始文件（如 iPhone 的 HEIC）。keep_original=true 时保留，
    # 删媒体时要连它一起删，否则会留磁盘垃圾
    source_path: Mapped[Optional[str]] = mapped_column(String(255))
    captured_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_media_event", "event_id"),
        Index("ix_media_wardrobe_item", "wardrobe_item_id"),
    )


# 单品类别：与配置 [[wardrobe_categories]] 对应（配置缺省时用这份兜底）
WARDROBE_CATEGORIES = ("top", "bottom", "outer", "dress", "shoes", "accessory", "bag", "other")

# 单品状态：一件东西「现在在哪」。
# 前两个 = 在手（还能穿、算重复候选、默认出现在衣橱）；其余 = 已离手（默认隐藏，可切换查看）。
# ★ 写死在代码里、不放 config：status 直接决定列表与去重的口径，
#   配置漂移会让「已卖掉的旧项链」被当成重复候选，静默拦下同名新项链。
WARDROBE_STATUSES = ("in_use", "idle", "sold", "gifted", "lost", "damaged", "discarded")
WARDROBE_STATUS_LABELS = {
    "in_use": "在役",
    "idle": "闲置收纳",
    "sold": "已卖出",
    "gifted": "已送人",
    "lost": "已丢失",
    "damaged": "损坏待修",
    "discarded": "已丢弃",
}
WARDROBE_ON_HAND_STATUSES = ("in_use", "idle")
WARDROBE_OFF_HAND_STATUSES = tuple(s for s in WARDROBE_STATUSES if s not in WARDROBE_ON_HAND_STATUSES)


class WardrobeItem(Base):
    """单品档案：一件**实际存在**的衣物/配饰 = 一行，全局唯一。

    为什么独立成表，而不是「给 outfit 事件加个 item_key 字段」：
      · 单品本身**没有日期**，它是可以被反复穿着的实体 ——「去重 / 挂照片 / 统计穿着次数」
        都要求它有自己的一行，而不是散在时间轴里的事件
      · 同一件被反复穿 → 变成 outfit_wears 里的多条引用，而不是重复的记录

    ★ 穿着次数与最近穿着**不冗余存**：一律由 outfit_wears 聚合（双份事实必然漂移，
      同「生日只留一个源」的教训）。first/last_worn_on 只是缓存，由服务端统一重算。
    """

    __tablename__ = "wardrobe_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(32))
    # ★ 唯一索引里不能放可空列：MySQL 认为多个 NULL 互不相等，空颜色会直接绕过去重。
    #   所以另存一份「归一化色」永远非空（'' 表示未填），唯一约束用它。
    color_key: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default=""
    )
    tags: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    # 状态：in_use 在役 / idle 闲置收纳 / sold 已卖出 / gifted 已送人 /
    #       lost 已丢失 / damaged 损坏待修 / discarded 已丢弃（见 WARDROBE_STATUSES）
    # ★ 当前状态只留这一个源（列表/去重要用）；变更历史在 wardrobe_item_status_log。
    #   旧的 active 布尔已删：「两套事实」必然漂移（卖掉却没停用 = 列表与去重各说各话）。
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_use", server_default="in_use"
    )
    status_reason: Mapped[Optional[str]] = mapped_column(String(255))
    status_changed_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    # 替换关系：**新件**指向被它替代的旧件（1 旧 → N 新），旧件那侧按反查列出
    replaces_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="SET NULL")
    )
    # 去重是**软删**：被合并到哪一条。作废的行不再出现在任何列表，但可回滚
    merged_into_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="SET NULL")
    )
    first_worn_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    last_worn_on: Mapped[Optional[dt.date]] = mapped_column(Date)

    # ★ 时间口径：本地墙钟（Asia/Shanghai），与 events 一致，由 Python 在插入时写。
    #   不要依赖 DB 的 CURRENT_TIMESTAMP —— 生产 MariaDB 宿主是 UTC，本机 MySQL 是 +08，
    #   同一段代码两处跑出来的「新增时间」会差 8 小时（跨零点还会差一天）。
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.now,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.now, onupdate=dt.datetime.now,
        server_default=func.current_timestamp(),
    )

    __table_args__ = (
        # 结构级防重复：同一个人 + 同类别 + 同名 + 同色 建不出第二条。
        # ★ 状态进了唯一键：卖掉旧项链后，同名的「新项链」必须建得出来（这才是「换新」）。
        UniqueConstraint("person_id", "category", "name", "color_key", "status",
                         name="uq_wardrobe_item"),
        Index("ix_wardrobe_person_cat", "person_id", "category", "status"),
    )


class WardrobeItemStatusLog(Base):
    """单品状态变更历史：一件东西「什么时候、因为什么」变成现在这样。

    ★ 只把**当前**状态冗余在 wardrobe_items（列表筛选要用），历史一律落这张表：
      改一次状态追加一行、不覆盖 —— 覆盖掉原因，等于「为什么卖掉」永久丢失。
    """

    __tablename__ = "wardrobe_item_status_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    effective_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    source: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.now,
        server_default=func.current_timestamp(),
    )

    __table_args__ = (
        Index("ix_wardrobe_status_log_item", "item_id", "id"),
    )


class OutfitWear(Base):
    """穿搭 ↔ 单品：一次穿着里「穿了哪几件」。

    单品「穿过几次 / 最近一次」全部由这张表聚合得出，见 services/wardrobe.py。
    """

    __tablename__ = "outfit_wears"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("wardrobe_items.id", ondelete="CASCADE"), nullable=False
    )
    # 冗余自 item.category，允许覆盖（马甲叠穿可以算 outer）
    slot: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        UniqueConstraint("event_id", "item_id", name="uq_outfit_wear"),
        Index("ix_outfit_wears_item", "item_id"),
    )


class CycleRecord(Base):
    """生理期记录（仅对启用 cycle 模块的人）。"""

    __tablename__ = "cycle_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    flow: Mapped[Optional[str]] = mapped_column(String(16))
    symptoms: Mapped[Optional[str]] = mapped_column(String(255))
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (UniqueConstraint("person_id", "start_date", name="uq_cycle_start"),)


class Interaction(Base):
    """见面 / 相处 / 过夜。"""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    occurred_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # 跨日相处的「结束日」：NULL = 单日（等价于 ended_on == occurred_on）
    # ★ 时间轴的锚点仍是 occurred_on，ended_on 只描述跨度；不要把它当第二个事件日。
    ended_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    location: Mapped[Optional[str]] = mapped_column(String(128))
    overnight: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hours: Mapped[Optional[float]] = mapped_column(Numeric(4, 1))
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (Index("ix_interactions_person_date", "person_id", "occurred_on"),)


class Gift(Base):
    """礼物往来：giver → receiver（两边都是 person，方向天然对称）。"""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    giver_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    receiver_person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    item: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(8))
    reaction: Mapped[Optional[str]] = mapped_column(String(255))
    return_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    happened_on: Mapped[Optional[dt.date]] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class SpecialDay(Base):
    """特殊日子：生日（公历/农历）、纪念日、节日。"""

    __tablename__ = "special_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="anniversary")
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    solar_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    lunar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lunar_month: Mapped[Optional[int]] = mapped_column(Integer)
    lunar_day: Mapped[Optional[int]] = mapped_column(Integer)
    lunar_leap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (Index("ix_special_days_person", "person_id", "kind"),)


class Todo(Base):
    """待办池：待补信息 / 待回礼 / 观察项。散在正文里的东西最容易丢。"""

    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="missing_info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    due_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    done_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (Index("ix_todos_done_person", "done", "person_id"),)


class IdempotencyKey(Base):
    """持久幂等键：Idempotency-Key → 指纹 + 响应原子持久。"""

    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[Optional[int]] = mapped_column(Integer)
    response_body: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (Index("ix_idempotency_key", "idempotency_key"),)


class AuditLog(Base):
    """写入留痕：什么来源、什么时候、改了哪个实体。
    用于「她纠正过生日」这类事实的可追溯，而不是重蹈覆辙。"""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="web")
    at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
