"""跨模块的聚合逻辑：今天卡片、临近日子、周期预测、统计。

不变量：所有「今天/还有几天」的计算都以传入的 today 为准（默认本机时区当天），
绝不缓存在模块级变量里 —— 跨日长会话复用旧日期是会真实出错的。
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Attribute,
    CycleRecord,
    Event,
    Gift,
    Interaction,
    Person,
    PersonModule,
    SpecialDay,
    Todo,
)
from . import lunar

WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def weekday_cn(d: dt.date) -> str:
    return WEEKDAYS[d.weekday()]


# ---------------------------------------------------------------- 日期推算

def next_occurrence(
    *, lunar_flag: bool, month: Optional[int], day: Optional[int],
    is_leap: bool, solar_date: Optional[dt.date], recurring: bool, today: dt.date,
) -> Optional[dt.date]:
    """下一次发生的公历日期（含今天）。"""
    if lunar_flag and month and day:
        d, _y = lunar.next_lunar_occurrence(month, day, today, is_leap)
        return d
    if solar_date is None:
        return None
    if not recurring:
        return solar_date if solar_date >= today else None
    for year in (today.year, today.year + 1):
        try:
            cand = solar_date.replace(year=year)
        except ValueError:  # 2-29
            cand = solar_date.replace(year=year, day=28)
        if cand >= today:
            return cand
    return None


def _days_left(d: dt.date, today: dt.date) -> int:
    return (d - today).days


# ---------------------------------------------------------------- 生日 / 纪念日

def person_birthday_next(p: Person, today: dt.date) -> Optional[dt.date]:
    if p.birthday_lunar and p.lunar_month and p.lunar_day:
        d, _y = lunar.next_lunar_occurrence(p.lunar_month, p.lunar_day, today, p.lunar_leap)
        return d
    if p.birthday:
        return next_occurrence(
            lunar_flag=False, month=None, day=None, is_leap=False,
            solar_date=p.birthday, recurring=True, today=today,
        )
    return None


def age_on(p: Person, d: dt.date) -> Optional[int]:
    if not p.birthday:
        return None
    return d.year - p.birthday.year - ((d.month, d.day) < (p.birthday.month, p.birthday.day))


def anniversaries(session: Session, today: dt.date,
                  person_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """纪念日：「在一起多少天」与「距下一次还有多少天」。

    「纪念日距今天数」两种读法都给：days_since（自开始日起已过天数，
    开始日在未来时为负）与 days_to_next（距下一次周年/下次发生）。
    只有农历没有公历锚点的纪念日算不出 days_since，返回 None。
    """
    stmt = select(SpecialDay).where(SpecialDay.kind == "anniversary")
    if person_id:
        stmt = stmt.where(SpecialDay.person_id == person_id)
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    out: List[Dict[str, Any]] = []
    for sd in session.scalars(stmt):
        base = sd.solar_date
        nxt = next_occurrence(
            lunar_flag=sd.lunar, month=sd.lunar_month, day=sd.lunar_day,
            is_leap=sd.lunar_leap, solar_date=sd.solar_date,
            recurring=sd.recurring, today=today,
        )
        out.append({
            "id": sd.id,
            "title": sd.title,
            "person_id": sd.person_id,
            "person_name": names.get(sd.person_id),
            "since_date": base.isoformat() if base else None,
            "days_since": (today - base).days if base else None,
            "next_date": nxt.isoformat() if nxt else None,
            "days_to_next": (nxt - today).days if nxt else None,
            "recurring": bool(sd.recurring),
            "lunar": bool(sd.lunar),
            "note": sd.note,
        })
    out.sort(key=lambda a: (a["days_to_next"] is None, a["days_to_next"] or 0))
    return out


# ---------------------------------------------------------------- 今天卡片

def today_card(session: Session, today: Optional[dt.date] = None,
               person_id: Optional[int] = None) -> Dict[str, Any]:
    today = today or dt.date.today()

    persons_stmt = select(Person).where(Person.active.is_(True))
    if person_id:
        persons_stmt = persons_stmt.where(Person.id == person_id)
    persons = list(session.scalars(persons_stmt.order_by(Person.sort_order, Person.id)))

    # --- 今天是什么日子 ---
    notes: List[str] = []
    for p in persons:
        bd = person_birthday_next(p, today)
        if bd == today:
            age = age_on(p, today)
            notes.append(
                "%s 生日%s" % (p.display_name, "，满 %d 岁" % age if age else "")
            )

    sd_stmt = select(SpecialDay)
    if person_id:
        sd_stmt = sd_stmt.where(SpecialDay.person_id == person_id)
    for sd in session.scalars(sd_stmt):
        nxt = next_occurrence(
            lunar_flag=sd.lunar, month=sd.lunar_month, day=sd.lunar_day,
            is_leap=sd.lunar_leap, solar_date=sd.solar_date,
            recurring=sd.recurring, today=today,
        )
        if nxt == today:
            notes.append(sd.title)

    # --- 未来 N 天 ---
    up = upcoming(session, days=settings.upcoming_days, today=today, person_id=person_id)

    # --- 待办 ---
    todo_stmt = select(func.count(Todo.id)).where(Todo.done.is_(False))
    if person_id:
        todo_stmt = todo_stmt.where(Todo.person_id == person_id)
    todos_open = session.scalar(todo_stmt) or 0

    # --- 每人概览 ---
    out_persons: List[Dict[str, Any]] = []
    for p in persons:
        module_keys = {
            m.module_key for m in session.scalars(
                select(PersonModule).where(
                    PersonModule.person_id == p.id, PersonModule.enabled.is_(True)
                )
            )
        }
        last_seen = session.scalar(
            select(func.max(Interaction.occurred_on)).where(Interaction.person_id == p.id)
        )
        entry: Dict[str, Any] = {
            "id": p.id,
            "display_name": p.display_name,
            "relation_type": p.relation_type,
            "is_self": bool(p.is_self),
            "modules": sorted(module_keys),
            "last_seen": last_seen.isoformat() if last_seen else None,
            "days_since_last_seen": (today - last_seen).days if last_seen else None,
            "no_contact": bool(
                last_seen is None or (today - last_seen).days >= settings.no_contact_days
            ),
            "open_todos": session.scalar(
                select(func.count(Todo.id)).where(Todo.person_id == p.id, Todo.done.is_(False))
            ) or 0,
        }
        bd = person_birthday_next(p, today)
        if bd:
            entry["birthday_next"] = bd.isoformat()
            entry["birthday_days_left"] = _days_left(bd, today)
        if "cycle" in module_keys:
            entry["cycle"] = cycle_stats(session, p.id, today=today)
        out_persons.append(entry)

    return {
        "date": today,
        "weekday": weekday_cn(today),
        "lunar": lunar.format_lunar(today),
        "is_special": bool(notes),
        "special_notes": notes,
        "upcoming": up,
        "anniversaries": anniversaries(session, today, person_id),
        "todos_open": int(todos_open),
        "persons": out_persons,
    }


# ---------------------------------------------------------------- 临近日子

def upcoming(session: Session, days: int = 10, today: Optional[dt.date] = None,
             person_id: Optional[int] = None) -> List[Dict[str, Any]]:
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=days)
    items: List[Dict[str, Any]] = []

    p_stmt = select(Person).where(Person.active.is_(True))
    if person_id:
        p_stmt = p_stmt.where(Person.id == person_id)
    for p in session.scalars(p_stmt):
        bd = person_birthday_next(p, today)
        if bd and bd <= horizon:
            items.append({
                "kind": "birthday",
                "title": "%s生日" % p.display_name,
                "person_id": p.id,
                "person_name": p.display_name,
                "date": bd,
                "days_left": _days_left(bd, today),
                "lunar": bool(p.birthday_lunar),
                "age": age_on(p, bd),
            })

    sd_stmt = select(SpecialDay)
    if person_id:
        sd_stmt = sd_stmt.where(SpecialDay.person_id == person_id)
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    for sd in session.scalars(sd_stmt):
        nxt = next_occurrence(
            lunar_flag=sd.lunar, month=sd.lunar_month, day=sd.lunar_day,
            is_leap=sd.lunar_leap, solar_date=sd.solar_date,
            recurring=sd.recurring, today=today,
        )
        if nxt and nxt <= horizon:
            items.append({
                "kind": sd.kind,
                "title": sd.title,
                "person_id": sd.person_id,
                "person_name": names.get(sd.person_id) if sd.person_id else None,
                "date": nxt,
                "days_left": _days_left(nxt, today),
                "lunar": bool(sd.lunar),
                "age": None,
            })

    items.sort(key=lambda x: (x["days_left"], x["title"]))
    return items


# ---------------------------------------------------------------- 生理期

def cycle_stats(session: Session, person_id: int, today: Optional[dt.date] = None) -> Dict[str, Any]:
    today = today or dt.date.today()
    rows = list(session.scalars(
        select(CycleRecord)
        .where(CycleRecord.person_id == person_id)
        .order_by(CycleRecord.start_date)
    ))
    if not rows:
        return {"count": 0, "last_start": None, "avg_cycle_days": None,
                "predicted_next": None, "window": None, "days_since_last": None,
                "next_in_days": None, "records": []}

    starts = [r.start_date for r in rows]
    gaps = [(b - a).days for a, b in zip(starts, starts[1:])]
    recent = gaps[-6:] if len(gaps) >= 6 else gaps
    avg = round(sum(recent) / len(recent), 1) if recent else None
    last = starts[-1]
    predicted = None
    window = None
    if avg:
        predicted = last + dt.timedelta(days=round(avg))
        m = settings.cycle_window_margin_days
        window = [predicted - dt.timedelta(days=m), predicted + dt.timedelta(days=m)]

    return {
        "count": len(rows),
        "last_start": last,
        "avg_cycle_days": avg,
        "predicted_next": predicted,
        "window": window,
        "days_since_last": (today - last).days,
        "next_in_days": (predicted - today).days if predicted else None,
        "in_window": bool(window and window[0] <= today <= window[1]) if window else False,
        "note": "仅作关怀提醒，误差约 ±3 天；不可用于避孕或任何医学判断",
        "records": [
            {"id": r.id, "start_date": r.start_date, "end_date": r.end_date,
             "symptoms": r.symptoms, "note": r.note}
            for r in reversed(rows)
        ],
    }


# ---------------------------------------------------------------- 总览统计

def overview(session: Session, today: Optional[dt.date] = None) -> Dict[str, Any]:
    today = today or dt.date.today()
    by_type = {
        key: int(cnt)
        for key, cnt in session.execute(
            select(Event.type_key, func.count(Event.id)).group_by(Event.type_key)
        )
    }
    per_person = []
    for p in session.scalars(select(Person).order_by(Person.sort_order, Person.id)):
        last_seen = session.scalar(
            select(func.max(Interaction.occurred_on)).where(Interaction.person_id == p.id)
        )
        per_person.append({
            "id": p.id,
            "display_name": p.display_name,
            "relation_type": p.relation_type,
            "is_self": bool(p.is_self),
            "events": int(session.scalar(
                select(func.count(Event.id)).where(Event.person_id == p.id)
            ) or 0),
            "attributes": int(session.scalar(
                select(func.count(Attribute.id)).where(Attribute.person_id == p.id)
            ) or 0),
            "interactions": int(session.scalar(
                select(func.count(Interaction.id)).where(Interaction.person_id == p.id)
            ) or 0),
            "overnights": int(session.scalar(
                select(func.count(Interaction.id)).where(
                    Interaction.person_id == p.id, Interaction.overnight.is_(True)
                )
            ) or 0),
            "gifts_given": int(session.scalar(
                select(func.count(Gift.id)).where(Gift.giver_person_id == p.id)
            ) or 0),
            "gifts_received": int(session.scalar(
                select(func.count(Gift.id)).where(Gift.receiver_person_id == p.id)
            ) or 0),
            "last_seen": last_seen.isoformat() if last_seen else None,
        })
    return {
        "date": today,
        "persons": per_person,
        "events_by_type": by_type,
        "events_total": int(sum(by_type.values())),
        "todos_open": int(session.scalar(
            select(func.count(Todo.id)).where(Todo.done.is_(False))
        ) or 0),
        "upcoming": upcoming(session, days=settings.upcoming_days, today=today),
    }
