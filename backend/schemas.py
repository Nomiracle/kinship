"""请求/响应模型（Pydantic v2）。

★ Python 3.9 兼容：一律 Optional[...]，不写 `X | None`（pydantic 会 eval 注解）。
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

ORM = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- 人

class PersonIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    relation_type: str = "friend"
    is_self: bool = False
    # 性别：female/male/other；不传 = 未知（未知性别不自动开生理期，但可手动开）
    gender: Optional[str] = None
    birthday: Optional[dt.date] = None
    birthday_lunar: bool = False
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    lunar_leap: bool = False
    aliases: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: str = "normal"
    sort_order: int = 0
    # 圈子视角
    circle: str = "self"
    familiarity: int = Field(default=1, ge=1, le=4)
    via_person_id: Optional[int] = None
    modules: Optional[List[str]] = None  # 不传则按 relation_type 的默认模块


class PersonPatch(BaseModel):
    display_name: Optional[str] = None
    relation_type: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[dt.date] = None
    birthday_lunar: Optional[bool] = None
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    lunar_leap: Optional[bool] = None
    aliases: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: Optional[str] = None
    sort_order: Optional[int] = None
    active: Optional[bool] = None
    circle: Optional[str] = None
    familiarity: Optional[int] = Field(default=None, ge=1, le=4)
    via_person_id: Optional[int] = None


class PersonOut(BaseModel):
    model_config = ORM
    id: int
    display_name: str
    relation_type: str
    is_self: bool
    gender: Optional[str] = None
    birthday: Optional[dt.date] = None
    birthday_lunar: bool
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    lunar_leap: bool
    aliases: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: str
    active: bool
    sort_order: int
    circle: str = "self"
    familiarity: int = 1
    via_person_id: Optional[int] = None
    via_name: Optional[str] = None
    # 生日的「明确写法 + 还有几天 + 满几岁」（GET /persons 时算好；写入接口为 None）。
    # 为什么不只在今天卡片给：只有天数没有日期，最容易被误读成别的东西的倒计时。
    birthday_text: Optional[str] = None
    birthday_next: Optional[dt.date] = None
    birthday_days_left: Optional[int] = None
    age_next: Optional[int] = None


class ModulesIn(BaseModel):
    modules: List[str]


class RelationIn(BaseModel):
    from_person_id: int
    to_person_id: int
    label: str
    notes: Optional[str] = None


# ---------------------------------------------------------------- 属性 KV

class AttributeIn(BaseModel):
    person_id: int
    category: str
    value: str
    note: Optional[str] = None
    sensitivity: str = "normal"


class AttributeOut(BaseModel):
    model_config = ORM
    id: int
    person_id: int
    category: str
    value: str
    note: Optional[str] = None
    sensitivity: str


# ---------------------------------------------------------------- 事件

class EventIn(BaseModel):
    person_id: Optional[int] = None
    type_key: str = "text"
    event_date: dt.date
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None
    sensitivity: str = "normal"
    source: str = "web"
    # 结构化附加（按 type_key 生效；省略即只写时间轴）
    overnight: Optional[bool] = None
    location: Optional[str] = None
    hours: Optional[float] = None
    # 多个人（家庭聚会等）
    person_ids: Optional[List[int]] = None


class EventPatch(BaseModel):
    person_id: Optional[int] = None
    type_key: Optional[str] = None
    event_date: Optional[dt.date] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None
    sensitivity: Optional[str] = None
    # 相处记录的结构化字段（只对 meeting 生效：同步更新 interactions 明细）
    location: Optional[str] = None
    hours: Optional[float] = None
    overnight: Optional[bool] = None
    # 穿搭：**全量替换**引用的单品 [{item_id} 或 {category,name,color}]。
    # 元素结构由 services.wardrobe.resolve_refs 校验，所以这里用宽松的 Dict
    # （OutfitItemRef 定义在本文件靠后的「服装」段，pydantic 在这里解析不到）
    items: Optional[List[Dict]] = None


class EventOut(BaseModel):
    model_config = ORM
    id: int
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    type_key: str
    event_date: dt.date
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[str] = None
    sensitivity: str
    source: str
    created_at: Optional[dt.datetime] = None
    # 穿搭事件引用的单品（其他类型为空）
    items: List[Dict] = Field(default_factory=list)


# ---------------------------------------------------------------- 生理期

class CycleIn(BaseModel):
    person_id: int
    start_date: dt.date
    end_date: Optional[dt.date] = None
    flow: Optional[str] = None
    symptoms: Optional[str] = None
    note: Optional[str] = None


class CycleOut(BaseModel):
    model_config = ORM
    id: int
    person_id: int
    start_date: dt.date
    end_date: Optional[dt.date] = None
    flow: Optional[str] = None
    symptoms: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------- 相处

class InteractionIn(BaseModel):
    person_id: int
    occurred_on: dt.date
    location: Optional[str] = None
    overnight: bool = False
    hours: Optional[float] = None
    note: Optional[str] = None


class InteractionOut(BaseModel):
    model_config = ORM
    id: int
    person_id: int
    occurred_on: dt.date
    location: Optional[str] = None
    overnight: bool
    hours: Optional[float] = None
    note: Optional[str] = None


# ---------------------------------------------------------------- 礼物

class GiftIn(BaseModel):
    giver_person_id: int
    receiver_person_id: int
    item: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    reaction: Optional[str] = None
    return_pending: bool = False
    happened_on: Optional[dt.date] = None


class GiftOut(BaseModel):
    model_config = ORM
    id: int
    giver_person_id: int
    receiver_person_id: int
    item: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    reaction: Optional[str] = None
    return_pending: bool
    happened_on: Optional[dt.date] = None


# ---------------------------------------------------------------- 特殊日子

class SpecialDayIn(BaseModel):
    person_id: Optional[int] = None
    kind: str = "anniversary"
    title: str
    solar_date: Optional[dt.date] = None
    lunar: bool = False
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    lunar_leap: bool = False
    recurring: bool = True
    note: Optional[str] = None


class SpecialDayOut(BaseModel):
    model_config = ORM
    id: int
    person_id: Optional[int] = None
    kind: str
    title: str
    solar_date: Optional[dt.date] = None
    lunar: bool
    lunar_month: Optional[int] = None
    lunar_day: Optional[int] = None
    lunar_leap: bool
    recurring: bool
    note: Optional[str] = None


# ---------------------------------------------------------------- 待办

class TodoIn(BaseModel):
    person_id: Optional[int] = None
    kind: str = "missing_info"
    title: str
    detail: Optional[str] = None
    due_date: Optional[dt.date] = None


class TodoPatch(BaseModel):
    title: Optional[str] = None
    detail: Optional[str] = None
    due_date: Optional[dt.date] = None
    done: Optional[bool] = None
    kind: Optional[str] = None


class TodoOut(BaseModel):
    model_config = ORM
    id: int
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    kind: str
    title: str
    detail: Optional[str] = None
    due_date: Optional[dt.date] = None
    done: bool
    created_at: Optional[dt.datetime] = None


# ---------------------------------------------------------------- 汇总视图

class TodayOut(BaseModel):
    date: dt.date
    weekday: str
    lunar: str
    is_special: bool
    special_notes: List[str] = Field(default_factory=list)
    upcoming: List[Dict] = Field(default_factory=list)
    todos_open: int = 0
    persons: List[Dict] = Field(default_factory=list)


class SearchHit(BaseModel):
    id: int
    type_key: str
    event_date: dt.date
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    mode: str = "fulltext"


# ---------------------------------------------------------------- 服装（单品 / 穿搭）

class WardrobeItemIn(BaseModel):
    person_id: int
    category: str = "other"
    name: str = Field(min_length=1, max_length=128)
    color: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: str = "normal"


class WardrobeItemPatch(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    color: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: Optional[str] = None
    active: Optional[bool] = None


class WardrobeWearOut(BaseModel):
    """单品视角的一条穿着记录：哪天穿的、什么槽位、当时还穿了什么。"""

    event_id: int
    event_date: dt.date
    slot: str
    note: Optional[str] = None
    together: List[str] = Field(default_factory=list)


class WardrobeItemOut(BaseModel):
    id: int
    person_id: int
    person_name: Optional[str] = None
    category: str
    category_label: Optional[str] = None
    name: str
    color: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None
    sensitivity: str
    active: bool
    merged_into_id: Optional[int] = None
    first_worn_on: Optional[dt.date] = None
    last_worn_on: Optional[dt.date] = None
    wear_count: int = 0
    media: List[Dict] = Field(default_factory=list)


class WardrobeItemDetail(WardrobeItemOut):
    wears: List[WardrobeWearOut] = Field(default_factory=list)


class WardrobeMergeIn(BaseModel):
    into_id: int


class OutfitItemRef(BaseModel):
    """穿搭里的一件：给 item_id 复用已有单品；给 name 则「没有就新建、有就复用」。"""

    item_id: Optional[int] = None
    category: Optional[str] = None
    name: Optional[str] = None
    color: Optional[str] = None
    tags: Optional[str] = None
    slot: Optional[str] = None
    note: Optional[str] = None


class OutfitIn(BaseModel):
    person_id: int
    event_date: dt.date
    items: List[OutfitItemRef] = Field(default_factory=list)
    location: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[str] = None
    # 手改的标题/正文（记录页的「手改标题/正文」开关）：
    # 给了就用给的，没给就按单品渲染 —— 与 PATCH 的「单品是真源，手改优先」同一口径
    title: Optional[str] = None
    body: Optional[str] = None
    sensitivity: str = "normal"
    source: str = "web"
    person_ids: Optional[List[int]] = None


# ---------------------------------------------------------------- 媒体

class MediaOut(BaseModel):
    id: int
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    event_id: Optional[int] = None
    wardrobe_item_id: Optional[int] = None
    kind: str
    path: str
    source_path: Optional[str] = None
    thumb_path: Optional[str] = None
    original_name: Optional[str] = None
    mime: Optional[str] = None
    bytes: Optional[int] = None
    captured_on: Optional[dt.date] = None
    created_at: Optional[dt.datetime] = None
