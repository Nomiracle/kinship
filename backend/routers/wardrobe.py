"""服装：单品档案 + 穿搭记录（去重的落点）。

两层：
  · 单品 wardrobe_items —— 一件实际存在的衣物/配饰，全局唯一（去重靠唯一键 + 合并）
  · 穿搭 events(type_key='outfit') + outfit_wears —— 一次穿着引用了哪几件

★ 穿着次数/最近穿着一律实时聚合，不冗余存计数。
★ 删除单品的顺序：先看有没有穿着记录（有就 409，提示合并或停用），再清磁盘文件。
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import CommitRoute, get_session
from ..models import Event, EventPerson, Media, OutfitWear, Person, WardrobeItem
from ..schemas import (
    OutfitIn,
    WardrobeItemIn,
    WardrobeItemPatch,
    WardrobeMergeIn,
)
from ..services import media as media_svc
from ..services import wardrobe as wardrobe_svc
from ..services.audit import write_audit

router = APIRouter(prefix="/api", tags=["wardrobe"], route_class=CommitRoute)


def _names(session: Session) -> Dict[int, str]:
    return {p.id: p.display_name for p in session.scalars(select(Person))}


def _media_map(session: Session, item_ids: List[int]) -> Dict[int, List[dict]]:
    out: Dict[int, List[dict]] = {}
    if not item_ids:
        return out
    for m in session.scalars(select(Media).where(Media.wardrobe_item_id.in_(item_ids))):
        out.setdefault(m.wardrobe_item_id, []).append({
            "id": m.id, "kind": m.kind, "path": m.path, "thumb_path": m.thumb_path,
        })
    return out


def _item_out(item: WardrobeItem, names: dict, count: int = 0,
              media: Optional[list] = None) -> dict:
    return {
        "id": item.id,
        "person_id": item.person_id,
        "person_name": names.get(item.person_id),
        "category": item.category,
        "category_label": settings.wardrobe_category_label(item.category),
        "name": item.name,
        "color": item.color,
        "tags": item.tags,
        "notes": item.notes,
        "sensitivity": item.sensitivity,
        "active": bool(item.active),
        "merged_into_id": item.merged_into_id,
        "first_worn_on": item.first_worn_on,
        "last_worn_on": item.last_worn_on,
        "wear_count": int(count),
        "media": media or [],
    }


def _wear_rows(session: Session, item_id: int) -> List[dict]:
    """单品的穿着历史（含「当时还穿了什么」+ 那次穿搭的照片）。"""
    wears = list(session.scalars(
        select(OutfitWear).where(OutfitWear.item_id == item_id)
    ))
    if not wears:
        return []
    event_ids = [w.event_id for w in wears]
    events = {e.id: e for e in session.scalars(select(Event).where(Event.id.in_(event_ids)))}
    together: Dict[int, List[str]] = {}
    for row in session.execute(
        select(OutfitWear.event_id, WardrobeItem.name, WardrobeItem.id)
        .join(WardrobeItem, WardrobeItem.id == OutfitWear.item_id)
        .where(OutfitWear.event_id.in_(event_ids))
    ).all():
        if row[2] != item_id:
            together.setdefault(row[0], []).append(row[1])
    # 照片挂在「事件」上（一张全身照只存一份，多单品共享），单品视图里带出来即可
    photos: Dict[int, List[dict]] = {}
    for m in session.scalars(
        select(Media).where(Media.event_id.in_(event_ids)).order_by(Media.id)
    ):
        photos.setdefault(m.event_id, []).append({
            "id": m.id, "kind": m.kind, "path": m.path, "thumb_path": m.thumb_path,
        })
    out = []
    for w in wears:
        e = events.get(w.event_id)
        out.append({
            "event_id": w.event_id,
            "event_date": e.event_date if e else None,
            "slot": w.slot,
            "note": w.note,
            "together": together.get(w.event_id, []),
            "media": photos.get(w.event_id, []),
        })
    out.sort(key=lambda x: (x["event_date"] is None, x["event_date"] or dt.date.min), reverse=True)
    return out


def _outfit_out(session: Session, event: Event, names: Optional[dict] = None) -> dict:
    names = names or _names(session)
    rows = session.execute(
        select(OutfitWear, WardrobeItem)
        .join(WardrobeItem, WardrobeItem.id == OutfitWear.item_id)
        .where(OutfitWear.event_id == event.id)
    ).all()
    pairs = [(item, wear.slot, wear.note) for wear, item in rows]
    pairs.sort(key=lambda p: wardrobe_svc.SLOT_ORDER.index(p[1])
               if p[1] in wardrobe_svc.SLOT_ORDER else 99)
    return {
        "id": event.id,
        "person_id": event.person_id,
        "person_name": names.get(event.person_id),
        "type_key": event.type_key,
        "event_date": event.event_date,
        "title": event.title,
        "body": event.body,
        "tags": event.tags,
        "sensitivity": event.sensitivity,
        "source": event.source,
        "created_at": event.created_at,
        "items": [
            {
                "item_id": item.id,
                "name": item.name,
                "color": item.color,
                "category": item.category,
                "category_label": settings.wardrobe_category_label(item.category),
                "slot": slot,
                "sensitivity": item.sensitivity,
                "note": note,
            }
            for item, slot, note in pairs
        ],
    }


# ---------------------------------------------------------------- 单品

@router.get("/wardrobe/items")
def list_items(
    person_id: Optional[int] = None,
    category: Optional[str] = None,
    q: Optional[str] = None,
    include_inactive: bool = False,
    include_merged: bool = False,
    limit: int = Query(500, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    stmt = select(WardrobeItem).order_by(WardrobeItem.category, WardrobeItem.name)
    if person_id:
        stmt = stmt.where(WardrobeItem.person_id == person_id)
    if category:
        stmt = stmt.where(WardrobeItem.category == category)
    if not include_merged:
        stmt = stmt.where(WardrobeItem.merged_into_id.is_(None))
    if not include_inactive:
        stmt = stmt.where(WardrobeItem.active.is_(True))
    if q:
        like = "%%%s%%" % q
        stmt = stmt.where(
            WardrobeItem.name.like(like) | WardrobeItem.tags.like(like)
            | WardrobeItem.notes.like(like) | WardrobeItem.color.like(like)
        )
    rows = list(session.scalars(stmt.limit(limit)))
    names = _names(session)
    counts = wardrobe_svc.wear_counts(session, [r.id for r in rows])
    mmedia = _media_map(session, [r.id for r in rows])
    return {
        "total": len(rows),
        "items": [_item_out(r, names, counts.get(r.id, 0), mmedia.get(r.id)) for r in rows],
    }


@router.get("/wardrobe/duplicates")
def list_duplicates(person_id: Optional[int] = None,
                    session: Session = Depends(get_session)):
    """重复候选（确定 / 疑似）。只出候选，合并要人点。"""
    groups = wardrobe_svc.duplicate_candidates(session, person_id)
    return {"groups": groups, "high": sum(1 for g in groups if g["confidence"] == "high")}


@router.get("/wardrobe/items/{item_id}")
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "找不到该单品")
    names = _names(session)
    counts = wardrobe_svc.wear_counts(session, [item.id])
    data = _item_out(item, names, counts.get(item.id, 0),
                     _media_map(session, [item.id]).get(item.id))
    data["wears"] = _wear_rows(session, item.id)
    if item.merged_into_id:
        data["merged_into"] = _item_out(
            session.get(WardrobeItem, item.merged_into_id), names
        ) if session.get(WardrobeItem, item.merged_into_id) else None
    return data


@router.post("/wardrobe/items", status_code=201)
def create_item(payload: WardrobeItemIn, session: Session = Depends(get_session)):
    if not session.get(Person, payload.person_id):
        raise HTTPException(404, "找不到这个人")
    color_key = wardrobe_svc.canonical_key(payload.color)
    name_key = wardrobe_svc.canonical_key(payload.name)
    # 防回潮：同人+同类别+同名+同色已经存在时明确报冲突，让前端问「复用吗」
    for row in session.scalars(select(WardrobeItem).where(
        WardrobeItem.person_id == payload.person_id,
        WardrobeItem.category == payload.category,
        WardrobeItem.active.is_(True),
    )):
        if (wardrobe_svc.canonical_key(row.name), wardrobe_svc.canonical_key(row.color)) == (name_key, color_key):
            raise HTTPException(409, detail={
                "message": "已有同名同色单品，请复用或改名", "existing_id": row.id,
            })
    item = WardrobeItem(
        person_id=payload.person_id,
        category=payload.category,
        name=payload.name.strip(),
        color=payload.color,
        color_key=color_key,
        tags=payload.tags,
        notes=payload.notes,
        sensitivity=payload.sensitivity,
    )
    session.add(item)
    session.flush()
    write_audit(session, "wardrobe_item", item.id, "create")
    return _item_out(item, _names(session))


@router.patch("/wardrobe/items/{item_id}")
def patch_item(item_id: int, payload: WardrobeItemPatch,
               session: Session = Depends(get_session)):
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "找不到该单品")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data or "color" in data or "category" in data:
        name = data.get("name", item.name)
        color = data.get("color", item.color)
        category = data.get("category", item.category)
        name_key = wardrobe_svc.canonical_key(name)
        color_key = wardrobe_svc.canonical_key(color)
        for row in session.scalars(select(WardrobeItem).where(
            WardrobeItem.person_id == item.person_id,
            WardrobeItem.id != item.id,
            WardrobeItem.active.is_(True),
            WardrobeItem.merged_into_id.is_(None),
        )):
            if (row.category == category
                    and (wardrobe_svc.canonical_key(row.name), wardrobe_svc.canonical_key(row.color)) == (name_key, color_key)):
                raise HTTPException(409, detail={
                    "message": "改名后会与已有单品重复，建议合并", "existing_id": row.id,
                })
        data["color_key"] = color_key
    for k, v in data.items():
        setattr(item, k, v)
    write_audit(session, "wardrobe_item", item_id, "update")
    session.flush()
    counts = wardrobe_svc.wear_counts(session, [item.id])
    return _item_out(item, _names(session), counts.get(item.id, 0))


@router.delete("/wardrobe/items/{item_id}", status_code=204)
def delete_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "找不到该单品")
    used = session.scalar(
        select(func.count(OutfitWear.id)).where(OutfitWear.item_id == item_id)
    ) or 0
    if used:
        raise HTTPException(409, "这件有 %d 条穿着记录：改用「合并」或先停用，不要直接删" % used)
    # 删行不等于删文件（媒体不受外键级联约束）；且同内容文件可能被别处引用
    rows = list(session.scalars(select(Media).where(Media.wardrobe_item_id == item_id)))
    referenced = set()
    for o in session.scalars(select(Media).where(Media.wardrobe_item_id != item_id)):
        for v in (o.path, o.thumb_path, o.source_path):
            if v:
                referenced.add(v)
    for m in rows:
        media_svc.delete_files(*[p for p in (m.path, m.thumb_path, m.source_path)
                                 if p and p not in referenced])
        session.delete(m)
    session.delete(item)
    write_audit(session, "wardrobe_item", item_id, "delete")
    return None


@router.post("/wardrobe/items/{item_id}/merge")
def merge_item(item_id: int, payload: WardrobeMergeIn,
               session: Session = Depends(get_session)):
    """去重主操作：把 src 并进 dst —— 穿着记录改挂、信息合并、src 软删（可回滚）。"""
    src = session.get(WardrobeItem, item_id)
    dst = session.get(WardrobeItem, payload.into_id)
    if not src or not dst:
        raise HTTPException(404, "找不到要合并的单品")
    if src.id == dst.id:
        raise HTTPException(400, "不能合并到自己")
    if src.person_id != dst.person_id:
        raise HTTPException(400, "两件不属于同一个人")
    if not src.active or src.merged_into_id:
        raise HTTPException(400, "这条已经是作废/已合并状态")
    if dst.merged_into_id:
        raise HTTPException(400, "目标是已合并的单品，请选择它合并到的那条")

    existing = {w.event_id for w in session.scalars(
        select(OutfitWear).where(OutfitWear.item_id == dst.id)
    )}
    moved = dropped = 0
    for w in list(session.scalars(select(OutfitWear).where(OutfitWear.item_id == src.id))):
        if w.event_id in existing:
            # 同一天两件被并成一件 → 只保留一条穿着记录，否则唯一键冲突
            session.delete(w)
            dropped += 1
        else:
            w.item_id = dst.id
            existing.add(w.event_id)
            moved += 1

    # 信息不许丢：标签并集、备注追加
    if src.tags:
        parts = [p.strip() for p in (dst.tags or "").split(",") if p.strip()]
        for t in [x.strip() for x in src.tags.split(",") if x.strip()]:
            if t not in parts:
                parts.append(t)
        dst.tags = ",".join(parts) or None
    if src.notes and src.notes not in (dst.notes or ""):
        dst.notes = (dst.notes + "\n" + src.notes) if dst.notes else src.notes
    if dst.color is None and src.color:
        dst.color, dst.color_key = src.color, src.color_key

    src.active = False
    src.merged_into_id = dst.id
    session.flush()
    wardrobe_svc.refresh_worn_dates(session, [dst.id, src.id])
    write_audit(session, "wardrobe_item", src.id, "merge")
    counts = wardrobe_svc.wear_counts(session, [dst.id])
    out = _item_out(dst, _names(session), counts.get(dst.id, 0))
    out.update({"moved_wears": moved, "dropped_duplicate_wears": dropped,
                "merged_item_id": src.id})
    return out


@router.post("/wardrobe/items/{item_id}/unmerge", status_code=200)
def unmerge_item(item_id: int, session: Session = Depends(get_session)):
    """回滚一次合并（只恢复「这条被并到哪」的标记，穿着记录不拆回去）。"""
    item = session.get(WardrobeItem, item_id)
    if not item:
        raise HTTPException(404, "找不到该单品")
    if not item.merged_into_id:
        raise HTTPException(400, "这条没有被合并过")
    item.merged_into_id = None
    item.active = True
    write_audit(session, "wardrobe_item", item_id, "unmerge")
    return _item_out(item, _names(session),
                     wardrobe_svc.wear_counts(session, [item.id]).get(item.id, 0))


# ---------------------------------------------------------------- 穿搭

@router.get("/outfits/{event_id}")
def get_outfit(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event or event.type_key != "outfit":
        raise HTTPException(404, "找不到这条穿搭记录")
    return _outfit_out(session, event)


@router.post("/outfits", status_code=201)
def create_outfit(payload: OutfitIn, session: Session = Depends(get_session)):
    """记一次穿搭：1 条事件 + N 个单品引用。

    单品写 name（而不是 item_id）时按唯一键**先查后建** —— 同一件被反复记录
    只会复用已有的那条，这是「重复」从源头消失的地方。
    """
    if not session.get(Person, payload.person_id):
        raise HTTPException(404, "找不到这个人")

    # 单品解析（复用 / 内联新建）统一在 services.wardrobe.resolve_refs 里，
    # 编辑接口走同一段逻辑，保证「同一件只会得到同一条单品」
    pairs = wardrobe_svc.resolve_refs(
        session, payload.person_id,
        [r.model_dump() for r in payload.items], source=payload.source,
    )

    note = payload.note
    if payload.location:
        note = ("地点：%s" % payload.location) + ("；" + note if note else "")
    body = wardrobe_svc.render_body(pairs, note=note)

    # 单品是真源：没手改就按单品渲染标题/正文；手改了以手改文本为准
    # （与 PATCH /api/events 的「手改优先」同一口径 —— 记录页的「手改标题/正文」走这里）
    event = Event(
        person_id=payload.person_id,
        type_key="outfit",
        event_date=payload.event_date,
        title=payload.title or wardrobe_svc.render_title(pairs),
        body=payload.body or body,
        tags=payload.tags,
        sensitivity=payload.sensitivity,
        source=payload.source,
    )
    session.add(event)
    session.flush()

    if payload.person_ids:
        for pid in set(payload.person_ids):
            if pid != payload.person_id and session.get(Person, pid):
                session.add(EventPerson(event_id=event.id, person_id=pid))

    for item, slot, item_note in pairs:
        session.add(OutfitWear(event_id=event.id, item_id=item.id, slot=slot, note=item_note))
    session.flush()
    wardrobe_svc.refresh_worn_dates(session, [i.id for i, _, _ in pairs])
    write_audit(session, "event", event.id, "create", source=payload.source)
    return _outfit_out(session, event)


@router.delete("/outfits/{event_id}/items/{item_id}", status_code=204)
def remove_wear(event_id: int, item_id: int, session: Session = Depends(get_session)):
    """把某件从这次穿搭里去掉（记录仍在，只是不再引用它）。"""
    row = session.scalar(select(OutfitWear).where(
        OutfitWear.event_id == event_id, OutfitWear.item_id == item_id
    ))
    if not row:
        raise HTTPException(404, "这次穿搭里没有这件")
    session.delete(row)
    session.flush()
    wardrobe_svc.refresh_worn_dates(session, [item_id])
    return None
