"""记录类资源：事件时间轴、生理期、相处、礼物、特殊日子、待办。

四类记录共用 events 表（靠 type_key 区分），并对
period / meeting 做「结构化扇出」——写事件的同时落一条明细，
免得上层要写两遍、还容易不一致。
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import CommitRoute, get_session
from ..models import (
    CycleRecord,
    Event,
    EventPerson,
    Gift,
    Interaction,
    Media,
    OutfitWear,
    Person,
    SpecialDay,
    Todo,
    WardrobeItem,
)
from ..schemas import (
    CycleIn,
    CycleOut,
    EventIn,
    EventOut,
    EventPatch,
    GiftIn,
    GiftOut,
    InteractionIn,
    InteractionOut,
    SpecialDayIn,
    SpecialDayOut,
    TodoIn,
    TodoOut,
    TodoPatch,
    event_date_str,
    event_time_str,
)
from ..services.audit import write_audit
from ..services import media as media_svc
from ..services import wardrobe as wardrobe_svc
from ..services import idempotency as idem_svc

router = APIRouter(prefix="/api", tags=["records"], route_class=CommitRoute)


def _names(session: Session) -> dict:
    return {p.id: p.display_name for p in session.scalars(select(Person))}


def _event_out(e: Event, names: dict, media: Optional[list] = None,
               items: Optional[list] = None, meeting: Optional[dict] = None) -> dict:
    return {
        "id": e.id,
        "person_id": e.person_id,
        "person_name": names.get(e.person_id),
        "type_key": e.type_key,
        # 日期仍是 'YYYY-MM-DD'（老前端照旧渲染），时刻走 event_time / event_at
        "event_date": event_date_str(e.event_date),
        "event_at": e.event_date,
        "event_time": event_time_str(e.event_date),
        "title": e.title,
        "body": e.body,
        "tags": e.tags,
        "sensitivity": e.sensitivity,
        "source": e.source,
        "created_at": e.created_at,
        "media": media or [],
        "items": items or [],
        "meeting": meeting,
    }


# ---------------------------------------------------------------- 相处跨度

# 手滑打出 2037 年这种事不该靠自觉，上限挡一下（超出直接 400）。
MEETING_MAX_SPAN_DAYS = 365


def meeting_span(day: dt.date, ended_on: Optional[dt.date]) -> tuple:
    """(相差天数, 夜数)。单日 → (1, 0)；跨日 → (n+1, n)。"""
    if ended_on is None or ended_on <= day:
        return 1, 0
    nights = (ended_on - day).days
    return nights + 1, nights


def _meeting_row(event_id: int, day: dt.date, extra: dict,
                 current: Optional[dict] = None) -> dict:
    """把事件入参里的相处字段规范化成明细行。

    规则（唯一写入口，create/patch 都走这里，别再各写一套）：
      · `ended_on` 早于开始日 → 400；跨度超上限 → 400。
      · `ended_on` 等于开始日 → 规范成 None（单日只有一种存法）。
      · 有跨度 → overnight 恒真（跨了夜就是过夜），hours 置空
        （「3 天 2 晚折成 52 小时」这种数写进去只会误导统计）。
      · 无跨度 → 沿用调用方给的 overnight / hours（老的开关语义不变）。
    """
    cur = current or {}
    ended = extra["ended_on"] if "ended_on" in extra else cur.get("ended_on")
    if ended is not None:
        if ended < day:
            raise HTTPException(400, "结束日期不能早于开始日期")
        if (ended - day).days > MEETING_MAX_SPAN_DAYS:
            raise HTTPException(400, "相处跨度不能超过 %d 天" % MEETING_MAX_SPAN_DAYS)
        if ended == day:
            ended = None
    spans = ended is not None
    overnight = True if spans else bool(
        extra["overnight"] if "overnight" in extra else cur.get("overnight")
    )
    hours = None if spans else (
        extra["hours"] if "hours" in extra else cur.get("hours")
    )
    location = extra["location"] if "location" in extra else cur.get("location")
    return {
        "event_id": event_id,
        "occurred_on": day,
        "ended_on": ended,
        "location": location,
        "overnight": overnight,
        "hours": hours,
    }


def _meeting_dict(row: Interaction) -> dict:
    days, nights = meeting_span(row.occurred_on, row.ended_on)
    return {
        "location": row.location,
        "hours": float(row.hours) if row.hours is not None else None,
        "overnight": bool(row.overnight),
        "ended_on": row.ended_on,
        "span_days": days,
        "span_nights": nights,
    }


def _meeting_map(session: Session, events: list) -> dict:
    """这一页里相处事件的结构化明细（一次查完，别 N+1）。"""
    ids = [e.id for e in events if e.type_key == "meeting"]
    if not ids:
        return {}
    return {
        row.event_id: _meeting_dict(row)
        for row in session.scalars(
            select(Interaction).where(Interaction.event_id.in_(ids))
        )
    }


def _wear_map(session: Session, events: list) -> dict:
    """这一页里穿搭事件引用的单品（一次查完，别 N+1）。"""
    ids = [e.id for e in events if e.type_key == "outfit"]
    if not ids:
        return {}
    out: dict = {}
    for row in session.execute(
        select(
            OutfitWear.event_id, OutfitWear.slot, OutfitWear.note,
            WardrobeItem.id, WardrobeItem.name, WardrobeItem.color,
            WardrobeItem.category, WardrobeItem.sensitivity,
        )
        .join(WardrobeItem, WardrobeItem.id == OutfitWear.item_id)
        .where(OutfitWear.event_id.in_(ids))
    ).all():
        out.setdefault(row[0], []).append({
            "item_id": row[3], "name": row[4], "color": row[5],
            "category": row[6], "slot": row[1], "note": row[2],
            "sensitivity": row[7],
        })
    for rows in out.values():
        rows.sort(key=lambda r: wardrobe_svc.SLOT_ORDER.index(r["slot"])
                  if r["slot"] in wardrobe_svc.SLOT_ORDER else 99)
    return out


def _media_map(session: Session, event_ids: list) -> dict:
    """一次查完这一页事件的图片，别 N+1。"""
    out: dict = {}
    if not event_ids:
        return out
    for m in session.scalars(select(Media).where(Media.event_id.in_(event_ids))):
        out.setdefault(m.event_id, []).append({
            "id": m.id,
            "kind": m.kind,
            "path": m.path,
            "thumb_path": m.thumb_path,
        })
    return out


# ---------------------------------------------------------------- 事件时间轴

@router.get("/events")
def list_events(
    person_id: Optional[int] = None,
    type_key: Optional[str] = None,
    date_from: Optional[dt.date] = None,
    date_to: Optional[dt.date] = None,
    q: Optional[str] = None,
    # date（默认）= 按事件日期倒序（时间轴的「记录」语义）；created = 按写入时间倒序
    #   （记录页「刚记的」用：记到过去某天的记录也得出现在「刚记的」里，否则像没记上）
    order: str = Query("date", pattern="^(date|created)$"),
    # day = 按日分组返回（时间轴用）。★ 被 limit 截断的那一天会补全取回，
    #   否则第 201 条起会把同一天撕成两页，日头卡片看起来像丢了记录。
    group: str = Query("flat", pattern="^(flat|day)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    conds = []
    if person_id:
        conds.append(Event.person_id == person_id)
    if type_key:
        conds.append(Event.type_key == type_key)
    if date_from:
        conds.append(Event.event_date >= date_from)
    if date_to:
        conds.append(Event.event_date < date_to + dt.timedelta(days=1))
    if q:
        like = "%%%s%%" % q
        conds.append(Event.title.like(like) | Event.body.like(like) | Event.tags.like(like))
    base = select(Event).where(*conds)

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    if order == "created":
        ordering = (desc(Event.created_at), desc(Event.id))
    else:
        # 同一天内按时刻倒序；时间部分 00:00:00（= 只记到日）自然落在当天末尾。
        # ★ 不包 DATE() 函数：包了就用不上索引，也没必要。
        ordering = (desc(Event.event_date), desc(Event.id))
    rows = list(session.scalars(base.order_by(*ordering).limit(limit).offset(offset)))

    if group == "day" and rows:
        last_day = rows[-1].event_day
        day_begin = dt.datetime.combine(last_day, dt.time())
        day_end = dt.datetime.combine(last_day + dt.timedelta(days=1), dt.time())
        tail = list(session.scalars(
            base.where(Event.event_date >= day_begin, Event.event_date < day_end)
            .order_by(*ordering)
        ))
        seen_ids = {e.id for e in rows}
        rows.extend([e for e in tail if e.id not in seen_ids])

    names = _names(session)
    mmedia = _media_map(session, [e.id for e in rows])
    mwears = _wear_map(session, rows)
    mmeets = _meeting_map(session, rows)
    items = [
        _event_out(e, names, mmedia.get(e.id), mwears.get(e.id), mmeets.get(e.id))
        for e in rows
    ]
    payload = {"total": int(total), "limit": limit, "offset": offset, "items": items}
    if group == "day":
        grouped: Dict[str, list] = {}
        for it in items:
            grouped.setdefault(it["event_date"], []).append(it)
        payload["days"] = [
            {"date": d, "count": len(v), "items": v} for d, v in grouped.items()
        ]
        # 补全后的 next_offset 直接是「已取回的行数」——分页游标仍然连续，不会跳记录
        payload["next_offset"] = offset + len(rows)
        payload["has_more"] = payload["next_offset"] < total
    return payload


@router.post("/events", response_model=EventOut, status_code=201)
def create_event(payload: EventIn, request: Request, session: Session = Depends(get_session)):
    # 幂等：可选 Idempotency-Key header
    key = idem_svc.extract_key(request)
    payload_hash = idem_svc.hash_payload(payload.model_dump(mode="json"))
    claim = None
    if key:
        # 校验 person 存在性在 claim 前，避免无效 payload 占位
        pid = payload.person_id
        if pid and not session.get(Person, pid):
            raise HTTPException(404, "人物不存在")
        res = idem_svc.try_claim(session, key, "events", payload_hash)
        if isinstance(res, JSONResponse):
            return res
        claim = res
    data = payload.model_dump()
    extra = {k: data.pop(k) for k in ("overnight", "location", "hours", "ended_on")}
    data.pop("event_time", None)   # 已合并进 event_date（见 schemas.EventAtMixin）
    person_ids = data.pop("person_ids", None)
    person_id = data.get("person_id")
    if person_id and not session.get(Person, person_id):
        raise HTTPException(404, "人物不存在")

    event = Event(**data)
    if event.sensitivity == "normal" and event.type_key in ("period", "health"):
        event.sensitivity = "sensitive"
    session.add(event)
    session.flush()

    if person_ids:
        for pid in set(person_ids):
            session.add(EventPerson(event_id=event.id, person_id=pid))

    # 结构化扇出（明细表按「日」走 —— event_day 就是 .date()，见 models.Event.event_day）
    if event.type_key == "period" and person_id:
        exists = session.scalar(
            select(CycleRecord).where(
                CycleRecord.person_id == person_id, CycleRecord.start_date == event.event_day
            )
        )
        if not exists:
            session.add(CycleRecord(person_id=person_id, start_date=event.event_day,
                                    note=event.title))
    if event.type_key == "meeting" and person_id:
        row = _meeting_row(event.id, event.event_day, extra)
        session.add(Interaction(person_id=person_id, note=event.title, **row))

    write_audit(session, "event", event.id, "create", source=event.source)
    session.flush()
    body = _event_out(event, _names(session), meeting=_meeting_map(session, [event]).get(event.id))
    if claim is not None:
        idem_svc.complete_claim(session, claim, 201, EventOut.model_validate(body).model_dump(mode="json"))
    return body


@router.patch("/events/{event_id}", response_model=EventOut)
def patch_event(event_id: int, payload: EventPatch, session: Session = Depends(get_session)):
    """编辑一条记录。

    编辑不只是改 events 那一行 —— 三处扇出必须跟着走，否则「时间轴写的」和
    「明细表里算的」会从此刻开始悄悄分叉：
      · 相处（meeting）→ interactions.occurred_on / note / 地点 / 过夜 / 时长
      · 生理期（period）→ cycle_records.start_date（唯一键冲突要报 409，不是静默失败）
      · 穿搭（outfit）→ 整体替换 outfit_wears（增删单品）并重算「首次/最近穿着」
    改日期时若不同步，统计与提醒会一直用旧日期算，而且没有任何界面能看出来。
    """
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(404, "找不到该记录")
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)
    extra = {k: data.pop(k) for k in ("location", "hours", "overnight", "ended_on") if k in data}
    data.pop("event_time", None)   # 已合并进 event_date（见 schemas.EventAtMixin）
    # ★ old_day 是「日」（date）：明细表的列都是 DATE，比较/回写都要用它
    old_day = event.event_day
    for k, v in data.items():
        setattr(event, k, v)

    # ---- 穿搭：全量替换引用的单品 ----
    if event.type_key == "outfit":
        touched = {w.item_id for w in session.scalars(
            select(OutfitWear).where(OutfitWear.event_id == event.id)
        )}
        if items is not None:
            for w in list(session.scalars(
                select(OutfitWear).where(OutfitWear.event_id == event.id)
            )):
                session.delete(w)
            session.flush()
            pairs = wardrobe_svc.resolve_refs(session, event.person_id, items,
                                              source=event.source)
            for item, slot, item_note in pairs:
                session.add(OutfitWear(event_id=event.id, item_id=item.id,
                                       slot=slot, note=item_note))
            session.flush()
            touched |= {i.id for i, _, _ in pairs}
            # 单品是真源：没手改标题/正文时就按单品重算（手改过的以手改文本为准）
            if "title" not in data:
                event.title = wardrobe_svc.render_title(pairs)
            if "body" not in data:
                event.body = wardrobe_svc.render_body(pairs)
        # ★ 必须先 flush 再重算：SessionLocal 是 autoflush=False，
        #   否则 refresh 里的 min/max(event_date) 读到的还是改之前的旧日期
        session.flush()
        wardrobe_svc.refresh_worn_dates(session, list(touched))

    # ---- 相处：明细必须跟着事件走 ----
    if event.type_key == "meeting":
        rows = list(session.scalars(select(Interaction).where(Interaction.event_id == event.id)))
        if not rows:  # 老数据：明细可能没挂 event_id，按「人 + 日期」兜底找
            rows = list(session.scalars(select(Interaction).where(
                Interaction.event_id.is_(None),
                Interaction.person_id == event.person_id,
                Interaction.occurred_on == old_day,
            )))
        for row in rows:
            # ★ 改日期后跨度必须重新校验：把 8/20–8/22 的开始日挪到 8/25 会变成负跨度，
            #   静默写进去就会得到一条「结束早于开始」的明细，谁也不会发现。
            merged = _meeting_row(event.id, event.event_day, extra, current={
                "ended_on": row.ended_on, "location": row.location,
                "overnight": row.overnight, "hours": row.hours,
            })
            row.person_id = event.person_id
            row.note = event.title
            row.event_id = event.id
            row.occurred_on = merged["occurred_on"]
            row.ended_on = merged["ended_on"]
            row.location = merged["location"]
            row.overnight = merged["overnight"]
            row.hours = merged["hours"]

    # ---- 生理期：cycle_records 的唯一键是 (person_id, start_date) ----
    if event.type_key == "period" and event.event_day != old_day:
        clash = session.scalar(select(CycleRecord).where(
            CycleRecord.person_id == event.person_id,
            CycleRecord.start_date == event.event_day,
        ))
        if clash:
            raise HTTPException(409, "目标日期已经有一条生理期记录，不能重复")
        for row in session.scalars(select(CycleRecord).where(
            CycleRecord.person_id == event.person_id,
            CycleRecord.start_date == old_day,
        )):
            row.start_date = event.event_day

    write_audit(session, "event", event_id, "update")
    session.flush()
    names = _names(session)
    return _event_out(event, names, _media_map(session, [event.id]).get(event.id),
                      _wear_map(session, [event]).get(event.id),
                      _meeting_map(session, [event]).get(event.id))


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(404, "找不到该记录")
    # 扇出对称：写事件时落了明细，删事件时要把明细一起带走，
    # 否则 cycle_records / interactions 会留下孤儿行
    if event.type_key == "period":
        for row in session.scalars(
            select(CycleRecord).where(
                CycleRecord.person_id == event.person_id,
                CycleRecord.start_date == event.event_day,
            )
        ):
            session.delete(row)
    if event.type_key == "meeting":
        for row in session.scalars(select(Interaction).where(Interaction.event_id == event.id)):
            session.delete(row)
        for row in session.scalars(select(Interaction).where(
            Interaction.event_id.is_(None),
            Interaction.person_id == event.person_id,
            Interaction.occurred_on == event.event_day,
        )):
            session.delete(row)
    # 穿搭：先取受影响的单品（删完就查不到了），删掉引用后重算「首次/最近穿着」
    touched: list = []
    if event.type_key == "outfit":
        touched = [w.item_id for w in session.scalars(
            select(OutfitWear).where(OutfitWear.event_id == event.id)
        )]
        for w in session.scalars(select(OutfitWear).where(OutfitWear.event_id == event.id)):
            session.delete(w)
    # 图片：数据库行会被外键级联删掉，但**磁盘文件不会** —— 不显式清就留孤儿
    # （磁盘只增不减；与删人 / DELETE /api/media 同源处理）。
    # ★ 文件名 = 内容哈希 → 同一份文件可能被别的行共用（同一张图既挂事件又挂单品），
    #   所以要先看还有没有别的行引用它，否则会把别人的图一起删掉（真出过事故）。
    rows = list(session.scalars(select(Media).where(Media.event_id == event.id)))
    if rows:
        keep = set()
        for o in session.scalars(select(Media).where(~Media.id.in_([m.id for m in rows]))):
            for v in (o.path, o.thumb_path, o.source_path):
                if v:
                    keep.add(v)
        for m in rows:
            media_svc.delete_files(*[p for p in (m.path, m.thumb_path, m.source_path)
                                     if p and p not in keep])
    session.delete(event)
    write_audit(session, "event", event_id, "delete")
    if touched:
        session.flush()
        wardrobe_svc.refresh_worn_dates(session, touched)
    return None


# ---------------------------------------------------------------- 生理期

@router.get("/cycle", response_model=List[CycleOut])
def list_cycle(person_id: Optional[int] = None, session: Session = Depends(get_session)):
    stmt = select(CycleRecord).order_by(desc(CycleRecord.start_date))
    if person_id:
        stmt = stmt.where(CycleRecord.person_id == person_id)
    return list(session.scalars(stmt))


@router.post("/cycle", response_model=CycleOut, status_code=201)
def create_cycle(payload: CycleIn, session: Session = Depends(get_session)):
    if not session.get(Person, payload.person_id):
        raise HTTPException(404, "找不到这个人")
    existing = session.scalar(
        select(CycleRecord).where(
            CycleRecord.person_id == payload.person_id,
            CycleRecord.start_date == payload.start_date,
        )
    )
    if existing:
        raise HTTPException(409, "这一天的记录已存在")
    row = CycleRecord(**payload.model_dump())
    session.add(row)
    session.flush()
    write_audit(session, "cycle_record", row.id, "create")
    return row


@router.delete("/cycle/{record_id}", status_code=204)
def delete_cycle(record_id: int, session: Session = Depends(get_session)):
    row = session.get(CycleRecord, record_id)
    if not row:
        raise HTTPException(404, "找不到该记录")
    session.delete(row)
    write_audit(session, "cycle_record", record_id, "delete")
    return None


# ---------------------------------------------------------------- 相处 / 过夜

@router.get("/interactions", response_model=List[InteractionOut])
def list_interactions(person_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500),
                     session: Session = Depends(get_session)):
    stmt = select(Interaction).order_by(desc(Interaction.occurred_on), desc(Interaction.id))
    if person_id:
        stmt = stmt.where(Interaction.person_id == person_id)
    return list(session.scalars(stmt.limit(limit)))


@router.post("/interactions", response_model=InteractionOut, status_code=201)
def create_interaction(payload: InteractionIn, session: Session = Depends(get_session)):
    if not session.get(Person, payload.person_id):
        raise HTTPException(404, "找不到这个人")
    # 直写明细的口子也要走同一套跨度规范化（跨日 → 过夜、hours 置空、同日归一）
    norm = _meeting_row(0, payload.occurred_on, {
        "ended_on": payload.ended_on, "location": payload.location,
        "overnight": payload.overnight, "hours": payload.hours,
    })
    norm.pop("event_id", None)
    row = Interaction(person_id=payload.person_id, note=payload.note, **norm)
    session.add(row)
    session.flush()
    write_audit(session, "interaction", row.id, "create")
    return row


@router.delete("/interactions/{row_id}", status_code=204)
def delete_interaction(row_id: int, session: Session = Depends(get_session)):
    row = session.get(Interaction, row_id)
    if not row:
        raise HTTPException(404, "找不到该记录")
    session.delete(row)
    write_audit(session, "interaction", row_id, "delete")
    return None


# ---------------------------------------------------------------- 礼物

@router.get("/gifts", response_model=List[GiftOut])
def list_gifts(person_id: Optional[int] = None, session: Session = Depends(get_session)):
    stmt = select(Gift).order_by(desc(Gift.happened_on), desc(Gift.id))
    if person_id:
        stmt = stmt.where(
            (Gift.giver_person_id == person_id) | (Gift.receiver_person_id == person_id)
        )
    return list(session.scalars(stmt))


@router.post("/gifts", response_model=GiftOut, status_code=201)
def create_gift(payload: GiftIn, session: Session = Depends(get_session)):
    for pid in (payload.giver_person_id, payload.receiver_person_id):
        if not session.get(Person, pid):
            raise HTTPException(404, "人物 %s 不存在" % pid)
    row = Gift(**payload.model_dump())
    session.add(row)
    session.flush()
    write_audit(session, "gift", row.id, "create")
    return row


@router.delete("/gifts/{row_id}", status_code=204)
def delete_gift(row_id: int, session: Session = Depends(get_session)):
    row = session.get(Gift, row_id)
    if not row:
        raise HTTPException(404, "找不到该记录")
    session.delete(row)
    write_audit(session, "gift", row_id, "delete")
    return None


# ---------------------------------------------------------------- 特殊日子

@router.get("/special-days", response_model=List[SpecialDayOut])
def list_special_days(person_id: Optional[int] = None, session: Session = Depends(get_session)):
    stmt = select(SpecialDay).order_by(SpecialDay.id)
    if person_id:
        stmt = stmt.where(
            (SpecialDay.person_id == person_id) | (SpecialDay.person_id.is_(None))
        )
    return list(session.scalars(stmt))


@router.post("/special-days", response_model=SpecialDayOut, status_code=201)
def create_special_day(payload: SpecialDayIn, session: Session = Depends(get_session)):
    if payload.lunar and not (payload.lunar_month and payload.lunar_day):
        raise HTTPException(400, "农历日子需要 lunar_month 与 lunar_day")
    row = SpecialDay(**payload.model_dump())
    session.add(row)
    session.flush()
    write_audit(session, "special_day", row.id, "create")
    return row


@router.delete("/special-days/{row_id}", status_code=204)
def delete_special_day(row_id: int, session: Session = Depends(get_session)):
    row = session.get(SpecialDay, row_id)
    if not row:
        raise HTTPException(404, "找不到该记录")
    session.delete(row)
    write_audit(session, "special_day", row_id, "delete")
    return None


# ---------------------------------------------------------------- 待办

@router.get("/todos", response_model=List[TodoOut])
def list_todos(person_id: Optional[int] = None, include_done: bool = False,
               session: Session = Depends(get_session)):
    stmt = select(Todo).order_by(Todo.done, Todo.due_date, desc(Todo.id))
    if person_id:
        stmt = stmt.where(Todo.person_id == person_id)
    if not include_done:
        stmt = stmt.where(Todo.done.is_(False))
    names = _names(session)
    return [
        TodoOut(
            id=t.id, person_id=t.person_id, person_name=names.get(t.person_id),
            kind=t.kind, title=t.title, detail=t.detail, due_date=t.due_date,
            done=bool(t.done), created_at=t.created_at,
        )
        for t in session.scalars(stmt)
    ]


@router.post("/todos", response_model=TodoOut, status_code=201)
def create_todo(payload: TodoIn, session: Session = Depends(get_session)):
    row = Todo(**payload.model_dump())
    session.add(row)
    session.flush()
    write_audit(session, "todo", row.id, "create")
    return TodoOut(
        id=row.id, person_id=row.person_id, person_name=None, kind=row.kind,
        title=row.title, detail=row.detail, due_date=row.due_date, done=False,
        created_at=row.created_at,
    )


@router.patch("/todos/{row_id}", response_model=TodoOut)
def patch_todo(row_id: int, payload: TodoPatch, session: Session = Depends(get_session)):
    row = session.get(Todo, row_id)
    if not row:
        raise HTTPException(404, "找不到该待办")
    data = payload.model_dump(exclude_unset=True)
    if data.get("done") is True and not row.done:
        # 非弃用写法（datetime.utcnow 在 3.12+ 已弃用，且返回 naive）
        row.done_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    for k, v in data.items():
        setattr(row, k, v)
    write_audit(session, "todo", row_id, "update")
    session.flush()
    names = _names(session)
    return TodoOut(
        id=row.id, person_id=row.person_id, person_name=names.get(row.person_id),
        kind=row.kind, title=row.title, detail=row.detail, due_date=row.due_date,
        done=bool(row.done), created_at=row.created_at,
    )


@router.delete("/todos/{row_id}", status_code=204)
def delete_todo(row_id: int, session: Session = Depends(get_session)):
    row = session.get(Todo, row_id)
    if not row:
        raise HTTPException(404, "找不到该待办")
    session.delete(row)
    write_audit(session, "todo", row_id, "delete")
    return None
