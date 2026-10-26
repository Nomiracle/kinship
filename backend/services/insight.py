"""跨模块的聚合逻辑：今天卡片、临近日子、周期预测、统计。

不变量：所有「今天/还有几天」的计算都以传入的 today 为准（默认本机时区当天），
绝不缓存在模块级变量里 —— 跨日长会话复用旧日期是会真实出错的。
"""
from __future__ import annotations

import datetime as dt
import statistics
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


def birthday_text(p: Person) -> Optional[str]:
    """生日的「明确写法」：公历给日期，农历给「农历九月廿九」（农历生日本身没有年份）。

    为什么需要：页面只显示「还有 N 天」时，用户会把别的倒计时（生理期预测等）
    误读成生日。任何展示生日的地方都应该同时给出这个明确写法。
    """
    if p.birthday_lunar and p.lunar_month and p.lunar_day:
        return "农历%s%s" % (
            lunar.lunar_month_name(p.lunar_month, p.lunar_leap),
            lunar.lunar_day_name(p.lunar_day),
        )
    if p.birthday:
        return p.birthday.isoformat()
    return None


def birthday_fields(p: Person, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """生日的派生字段（明确写法 / 下次日期 / 还有几天 / 满几岁）。

    ★ 统一落点：列表页、个人页、今天卡片都从这里取 —— 不再各算一份
      （前端算不了农历，各算一份必然分叉）。
    为什么不挂在 ORM 模型上：派生字段不落库，塞进模型会让「改性别/改生日后
    没重算」这种坑重新出现；这里是纯函数，每次请求现算。
    """
    today = today or dt.date.today()
    nxt = person_birthday_next(p, today)
    return {
        "birthday_text": birthday_text(p),
        # 前端要靠它决定是否补「今年对应的公历日期」：农历生日光有「九月廿九」
        # 还是不知道是哪天，公历生日本身就是日期、不用补
        "birthday_lunar": bool(p.birthday_lunar),
        "birthday_next": nxt,
        "birthday_days_left": _days_left(nxt, today) if nxt else None,
        "age_next": age_on(p, nxt) if nxt else None,
    }


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
            select(func.max(func.coalesce(Interaction.ended_on, Interaction.occurred_on)))
            .where(Interaction.person_id == p.id)
        )
        entry: Dict[str, Any] = {
            "id": p.id,
            "display_name": p.display_name,
            "relation_type": p.relation_type,
            "gender": p.gender,
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
        # 生日的明确写法 + 倒计时（没有生日时各字段为 None）—— 只有天数没有日期
        # 就会被误读成别的倒计时，所以这里一次给全
        entry.update(birthday_fields(p, today))
        if "cycle" in module_keys and settings.gender_allows_module(p.gender, "cycle"):
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
                "birthday_text": birthday_text(p),
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

FERTILITY_NOTE = (
    "易孕期 / 相对安全期是按平均周期推算的生活参考，不是医学结论："
    "周期受作息、压力、疾病影响，误差可达数天；所谓「安全期避孕」的典型年失败率约 20%。"
    "请勿据此避孕或做任何医学决定。"
)


def _fertility(last: dt.date, predicted: dt.date, rows: List[CycleRecord],
               gaps: List[int], today: dt.date) -> Dict[str, Any]:
    """排卵日 / 易孕窗口 / 相对安全期（纯推算，务必与 FERTILITY_NOTE 一起展示）。

    模型：下次经期首日 − 14 天 ≈ 排卵日（黄体期近似常数）；易孕窗口取
    排卵前 5 天 ~ 排卵后 1 天（精子可存活数天、卵子约 24 小时）。
    因此「相对安全期」= 经期结束 ~ 窗口前、窗口后 ~ 下次经期前 —— 注意它**不保证安全**。
    """
    ovulation = predicted - dt.timedelta(days=14)
    fertile = (ovulation - dt.timedelta(days=5), ovulation + dt.timedelta(days=1))

    lens = [(r.end_date - r.start_date).days + 1 for r in rows
            if r.end_date and r.end_date >= r.start_date]
    period_len = int(round(sum(lens) / len(lens))) if lens else 5

    safe: List[Dict[str, Any]] = []
    s1, e1 = last + dt.timedelta(days=period_len), fertile[0] - dt.timedelta(days=1)
    if e1 >= s1:
        safe.append({"label": "经期结束后 → 易孕窗口前", "start": s1, "end": e1})
    s2, e2 = fertile[1] + dt.timedelta(days=1), predicted - dt.timedelta(days=1)
    if e2 >= s2:
        safe.append({"label": "排卵后 → 下次经期前", "start": s2, "end": e2})

    # 规律性：近 6 次间隔的标准差。数据不足时明确说「参考价值低」，别装作很准。
    window_gaps = gaps[-6:]
    sd = round(statistics.pstdev(window_gaps), 1) if len(window_gaps) >= 2 else None
    if sd is None or len(rows) < 3:
        level, level_text = "unknown", "数据不足（少于 3 次记录），参考价值低"
    elif sd <= 3:
        level, level_text = "regular", "较规律（近几次波动 ≤3 天）"
    elif sd <= 7:
        level, level_text = "fair", "一般（近几次波动约 %.1f 天）" % sd
    else:
        level, level_text = "irregular", "不规律（近几次波动约 %.1f 天），参考价值低" % sd

    # 今天处在哪个阶段（历史日期不判断）
    phase = None
    if today >= last:
        if today <= last + dt.timedelta(days=period_len - 1):
            phase = "经期"
        elif today == ovulation:
            phase = "排卵日"
        elif fertile[0] <= today <= fertile[1]:
            phase = "易孕窗口"
        elif today < fertile[0]:
            phase = "相对安全期（易孕窗口前）"
        elif today <= predicted:
            phase = "相对安全期（排卵后）"

    return {
        "ovulation": ovulation,
        "fertile_window": [fertile[0], fertile[1]],
        "safe_windows": safe,
        "period_length_days": period_len,
        "regularity": {"level": level, "text": level_text, "std_dev_days": sd},
        "phase_today": phase,
    }


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
                "next_in_days": None, "in_window": False, "fertility": None,
                "records": []}

    starts = [r.start_date for r in rows]
    gaps = [(b - a).days for a, b in zip(starts, starts[1:])]
    recent = gaps[-6:] if len(gaps) >= 6 else gaps
    avg = round(sum(recent) / len(recent), 1) if recent else None
    last = starts[-1]
    predicted = None
    window = None
    fertility = None
    if avg:
        predicted = last + dt.timedelta(days=round(avg))
        m = settings.cycle_window_margin_days
        window = [predicted - dt.timedelta(days=m), predicted + dt.timedelta(days=m)]
        if settings.show_fertility_window:
            fertility = _fertility(last, predicted, rows, gaps, today)

    return {
        "count": len(rows),
        "last_start": last,
        "avg_cycle_days": avg,
        "predicted_next": predicted,
        "window": window,
        "days_since_last": (today - last).days,
        "next_in_days": (predicted - today).days if predicted else None,
        "in_window": bool(window and window[0] <= today <= window[1]) if window else False,
        "fertility": fertility,
        "fertility_note": FERTILITY_NOTE if fertility else None,
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
            select(func.max(func.coalesce(Interaction.ended_on, Interaction.occurred_on)))
            .where(Interaction.person_id == p.id)
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
