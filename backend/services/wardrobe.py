"""服装单品：归一化、去重候选、穿着统计与穿搭排版。

设计要点（为什么这么写）：

1. **归一化键 != 显示名**。显示名保留原文（「灰色卫衣（有油渍）」），
   归一化键去掉括号补充/空白/emoji 并折叠同义词（小白鞋 = 白色鞋），只用于判重。
2. **自动判定只出候选，不自动合并**。实测「宝蓝色毛衣」与「浅蓝色毛衣」是两件，
   字符串相似度会把它们并成一件 —— 所以只有「同名同类同色」算确定重复，
   其余最多算疑似，必须人工确认。
3. **穿着次数一律聚合**（outfit_wears），不冗余存计数：双份事实必然漂移。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Event, OutfitWear, Person, WardrobeItem

# 穿搭排版顺序（上 → 下 → 外套/裙装 → 鞋 → 配饰）
SLOT_ORDER = ("top", "bottom", "outer", "dress", "shoes", "accessory", "bag", "other")
SLOT_LABELS = {
    "top": "上身",
    "bottom": "下身",
    "outer": "外套",
    "dress": "裙装",
    "shoes": "鞋",
    "accessory": "配饰",
    "bag": "包",
    "other": "其他",
}

_BRACKETS = re.compile(r"[（(][^）)]*[）)]")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]+")
_NOISE = re.compile(r"[\s\*·・、,，.。!！?？~～|/\\\-—_+=]+")


def normalize(text: Optional[str]) -> str:
    """机械归一化：去括号补充 → 去 emoji/标点/空白 → 全角转半角 → 小写。

    不做同义词替换（那一步在 canonical_key 里），避免相互递归。
    """
    if not text:
        return ""
    s = str(text)
    s = _BRACKETS.sub("", s)
    s = _EMOJI.sub("", s)
    s = unicodedata.normalize("NFKC", s)
    s = _NOISE.sub("", s)
    return s.strip().lower()


def canonical_key(text: Optional[str]) -> str:
    """判重键 = 归一化 + 同义词折叠（配置 wardrobe_synonyms，每组第一个是规范写法）。"""
    key = normalize(text)
    if not key:
        return ""
    for group in settings.wardrobe_synonyms:
        members = [normalize(str(w)) for w in (group or []) if str(w).strip()]
        if not members:
            continue
        canon = members[0]
        for m in members:
            if m and m != canon and m in key:
                key = key.replace(m, canon)
    return key


def item_key(name: Optional[str], color: Optional[str]) -> Tuple[str, str]:
    return canonical_key(name), canonical_key(color)


def find_item(session: Session, person_id: int, category: str, name: str,
              color: Optional[str] = None, include_inactive: bool = False) -> Optional[WardrobeItem]:
    """按唯一键（人 + 类别 + 名 + 色）找已有单品 —— 记录页新建前先查，防重复建。"""
    name_key, color_key = item_key(name, color)
    stmt = select(WardrobeItem).where(
        WardrobeItem.person_id == person_id,
        WardrobeItem.category == category,
    )
    if not include_inactive:
        stmt = stmt.where(WardrobeItem.active.is_(True), WardrobeItem.merged_into_id.is_(None))
    for row in session.scalars(stmt):
        if item_key(row.name, row.color) == (name_key, color_key):
            return row
    return None


def resolve_merged(session: Session, item: WardrobeItem) -> WardrobeItem:
    """如果拿到的是一条已被合并的单品，跟到最终目标（链条不会超过一层，仍做防护）。"""
    seen = set()
    cur = item
    while cur is not None and cur.merged_into_id and cur.id not in seen:
        seen.add(cur.id)
        nxt = session.get(WardrobeItem, cur.merged_into_id)
        if nxt is None:
            break
        cur = nxt
    return cur


def resolve_refs(session: Session, person_id: int, refs: Sequence[Any],
                 source: str = "web") -> List[Tuple[WardrobeItem, str, Optional[str]]]:
    """穿搭引用 → [(单品, 槽位, 备注)]，同一件只留一条。

    两种写法：`{"item_id": 12}` 复用已有单品；`{"category","name","color"}` **先查后建**
    （同人 + 同类别 + 同名 + 同色 已存在就复用，不新建）。后者就是「同一件衣服只会得到
    同一条单品」的落点，POST /api/outfits 与 PATCH /api/events 共用这段逻辑。

    参数不合法时抛 ValueError（main.py 里有统一的 400 处理）。
    """
    from ..models import Person  # 局部导入，避免循环引用

    if not session.get(Person, person_id):
        raise ValueError("找不到这个人")
    pairs: List[Tuple[WardrobeItem, str, Optional[str]]] = []
    seen = set()
    for ref in refs:
        data = ref if isinstance(ref, dict) else dict(ref)
        item_id = data.get("item_id")
        note = data.get("note")
        if item_id:
            item = session.get(WardrobeItem, item_id)
            if item is None:
                raise ValueError("找不到单品 %s" % item_id)
            if item.person_id != person_id:
                raise ValueError("单品「%s」不属于这个人" % item.name)
            item = resolve_merged(session, item)
        else:
            name = (data.get("name") or "").strip()
            if not name:
                raise ValueError("新建单品需要 name")
            category = data.get("category") or "other"
            item = find_item(session, person_id, category, name, data.get("color"))
            if item is None:
                item = WardrobeItem(
                    person_id=person_id, category=category, name=name,
                    color=data.get("color"),
                    color_key=canonical_key(data.get("color")),
                    tags=data.get("tags"), sensitivity="normal",
                )
                session.add(item)
                session.flush()
                from .audit import write_audit
                write_audit(session, "wardrobe_item", item.id, "create", source=source)
        if item.id in seen:
            continue
        seen.add(item.id)
        slot = data.get("slot") or settings.wardrobe_slot(item.category)
        pairs.append((item, slot, note))
    return pairs


# ---------------------------------------------------------------- 排版

def render_title(pairs: Sequence[Tuple[WardrobeItem, str, Optional[str]]]) -> Optional[str]:
    """标题 = 单品名按槽位顺序拼接（上身 → 下身 → 鞋/配饰），和历史记录写法一致。"""
    ordered = sorted(pairs, key=lambda p: SLOT_ORDER.index(p[1]) if p[1] in SLOT_ORDER else 99)
    names = [p[0].name for p in ordered if p[0] and p[0].name]
    return " + ".join(names) if names else None


def render_body(pairs: Sequence[Tuple[WardrobeItem, str, Optional[str]]],
                note: Optional[str] = None) -> Optional[str]:
    """按槽位分行渲染（和历史记录里的「上身/下身/鞋配饰」格式保持一致）。"""
    ordered = sorted(pairs, key=lambda p: SLOT_ORDER.index(p[1]) if p[1] in SLOT_ORDER else 99)
    lines: List[str] = []
    for slot in SLOT_ORDER:
        names = [p[0].name for p in ordered if p[1] == slot and p[0]]
        if names:
            lines.append("%s：%s" % (SLOT_LABELS.get(slot, slot), "、".join(names)))
    details = ["%s（%s）" % (p[0].name, p[2]) for p in ordered if p[0] and p[2]]
    if note:
        details.append(str(note))
    if details:
        lines.append("备注：" + "；".join(details))
    return "\n".join(lines) if lines else None


# ---------------------------------------------------------------- 统计

def wear_counts(session: Session, item_ids: Sequence[int]) -> Dict[int, int]:
    ids = [i for i in set(item_ids) if i]
    if not ids:
        return {}
    rows = session.execute(
        select(OutfitWear.item_id, func.count(OutfitWear.id))
        .where(OutfitWear.item_id.in_(ids))
        .group_by(OutfitWear.item_id)
    ).all()
    return {r[0]: int(r[1]) for r in rows}


def refresh_worn_dates(session: Session, item_ids: Sequence[int]) -> None:
    """重算 first/last_worn_on 缓存（合并、删除穿搭、改日期后都要调）。"""
    ids = [i for i in set(item_ids) if i]
    if not ids:
        return
    rows = session.execute(
        select(OutfitWear.item_id, func.min(Event.event_date), func.max(Event.event_date))
        .join(Event, Event.id == OutfitWear.event_id)
        .where(OutfitWear.item_id.in_(ids))
        .group_by(OutfitWear.item_id)
    ).all()
    stats = {r[0]: (r[1], r[2]) for r in rows}
    for iid in ids:
        item = session.get(WardrobeItem, iid)
        if item is None:
            continue
        first, last = stats.get(iid, (None, None))
        item.first_worn_on, item.last_worn_on = first, last


# ---------------------------------------------------------------- 去重候选

def _brief(item: WardrobeItem, counts: Dict[int, int]) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "color": item.color,
        "category": item.category,
        "tags": item.tags,
        "wear_count": counts.get(item.id, 0),
        "first_worn_on": item.first_worn_on,
        "last_worn_on": item.last_worn_on,
    }


def duplicate_candidates(session: Session, person_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """重复候选，只出「确定」与「疑似」两组：

      确定（high） 同人 + 同类别 + 判重键完全相同（例：黑裤 09-28 / 10-07）
      疑似（medium）同人 + 同类别 + 一个名字包含另一个（例：白色鞋 ↔ 带小点的小白鞋）

    仅名字相似（宝蓝 / 浅蓝）**刻意不输出**：它们是两件，列出来只是噪音。
    """
    stmt = select(WardrobeItem).where(
        WardrobeItem.active.is_(True), WardrobeItem.merged_into_id.is_(None)
    )
    if person_id:
        stmt = stmt.where(WardrobeItem.person_id == person_id)
    items = list(session.scalars(stmt))
    if not items:
        return []
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    counts = wear_counts(session, [i.id for i in items])

    buckets: Dict[Tuple[int, str], List[WardrobeItem]] = {}
    for it in items:
        buckets.setdefault((it.person_id, it.category), []).append(it)

    groups: List[Dict[str, Any]] = []
    for (pid, category), rows in buckets.items():
        if len(rows) < 2:
            continue
        by_key: Dict[str, List[WardrobeItem]] = {}
        for r in rows:
            by_key.setdefault(canonical_key(r.name), []).append(r)
        used = set()
        for key, same in by_key.items():
            if len(same) < 2 or not key:
                continue
            used.update(id(r) for r in same)
            groups.append({
                "confidence": "high",
                "reason": "同名同类别",
                "person_id": pid,
                "person_name": names.get(pid),
                "category": category,
                "items": [_brief(r, counts) for r in same],
            })
        # 疑似：判重键不同但互为子串（同类别内）
        for i, a in enumerate(rows):
            if id(a) in used:
                continue
            ka = canonical_key(a.name)
            if not ka:
                continue
            near = [b for b in rows[i + 1:] if id(b) not in used and canonical_key(b.name)
                    and (canonical_key(b.name) in ka or ka in canonical_key(b.name))]
            if not near:
                continue
            used.add(id(a))
            used.update(id(b) for b in near)
            groups.append({
                "confidence": "medium",
                "reason": "名称互相包含（疑似同一件）",
                "person_id": pid,
                "person_name": names.get(pid),
                "category": category,
                "items": [_brief(a, counts)] + [_brief(b, counts) for b in near],
            })

    groups.sort(key=lambda g: ({"high": 0, "medium": 1}[g["confidence"]], g["person_id"] or 0))
    return groups
