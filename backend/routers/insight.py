"""聚合与检索：今天卡片、临近日子、搜索、统计。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..db import CommitRoute, get_session
from ..models import Event, Person
from ..schemas import event_date_str, event_time_str
from ..services import insight

router = APIRouter(prefix="/api", tags=["insight"], route_class=CommitRoute)


@router.get("/today")
def today(person_id: Optional[int] = None, date: Optional[dt.date] = None,
          session: Session = Depends(get_session)):
    return insight.today_card(session, today=date, person_id=person_id)


@router.get("/upcoming")
def upcoming(days: int = Query(10, ge=1, le=90), person_id: Optional[int] = None,
             session: Session = Depends(get_session)):
    return insight.upcoming(session, days=days, person_id=person_id)


@router.get("/stats/overview")
def stats_overview(session: Session = Depends(get_session)):
    return insight.overview(session)


@router.get("/cycle/prediction")
def cycle_prediction(person_id: int, session: Session = Depends(get_session)):
    if not session.get(Person, person_id):
        raise ValueError("找不到这个人")
    return insight.cycle_stats(session, person_id)


@router.get("/search")
def search(q: str = Query(min_length=1), person_id: Optional[int] = None,
           limit: int = Query(50, ge=1, le=200), session: Session = Depends(get_session)):
    """中文检索。

    MySQL 的 ngram 分词器 token 长度固定为 2（ngram_token_size），
    因此**单字查询用 FULLTEXT 必然 0 命中** —— 短查询一律回退 LIKE。
    这不是绕过，而是这套索引的固有限制，写在这里免得后人以为是 bug。
    """
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    use_fulltext = len(q.strip()) > settings.like_fallback_max_chars
    rows = []
    mode = "like"
    params: Dict[str, Any] = {}

    if use_fulltext:
        sql = (
            "SELECT id, type_key, event_date, person_id, title, "
            "LEFT(COALESCE(body, ''), 120) AS snippet "
            "FROM events WHERE MATCH(title, body) AGAINST (:q IN NATURAL LANGUAGE MODE) "
        )
        params = {"q": q.strip()}
        if person_id:
            sql += "AND person_id = :pid "
            params["pid"] = person_id
        sql += "ORDER BY event_date DESC LIMIT :lim"
        params["lim"] = limit
        try:
            res = session.execute(text(sql), params).all()
            rows = list(res)
            mode = "fulltext"
        except Exception:
            rows = []

    if not rows:
        like = "%%%s%%" % q.strip()
        stmt = select(Event).where(
            Event.title.like(like) | Event.body.like(like) | Event.tags.like(like)
        )
        if person_id:
            stmt = stmt.where(Event.person_id == person_id)
        evs = list(session.scalars(
            stmt.order_by(desc(Event.event_date), desc(Event.id)).limit(limit)
        ))
        return {
            "q": q, "mode": "like" if not use_fulltext else "fulltext-empty→like",
            "items": [{
                "id": e.id, "type_key": e.type_key,
                "event_date": event_date_str(e.event_date),
                "event_time": event_time_str(e.event_date),
                "person_id": e.person_id, "person_name": names.get(e.person_id),
                "title": e.title, "snippet": (e.body or "")[:120],
            } for e in evs],
        }

    return {
        "q": q, "mode": mode,
        "items": [{
            "id": r[0], "type_key": r[1],
            "event_date": event_date_str(r[2]), "event_time": event_time_str(r[2]),
            "person_id": r[3],
            "person_name": names.get(r[3]), "title": r[4], "snippet": r[5],
        } for r in rows],
    }
