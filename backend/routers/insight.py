"""聚合与检索：今天卡片、临近日子、搜索、统计。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

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
    """中文检索：一律 LIKE。

    ★ 为什么不用全文索引：这套服务曾在 MySQL 上用 ngram 分词建过 FULLTEXT 索引，
      但 **MariaDB 没有 ngram parser**（`Function 'ngram' is not defined`）——
      同一份代码换数据库就会给出不同结果，连迁移都跑不过。
      档案量级在千条以内，LIKE 全表扫描是微秒级，所以索引与 MATCH 分支一起删掉，
      检索行为在 MySQL / MariaDB 上完全一致。
      真到十万量级再引入独立检索（Mroonga / 外部索引），别再依赖数据库方言。
    """
    like = "%%%s%%" % q.strip()
    stmt = select(Event).where(
        Event.title.like(like) | Event.body.like(like) | Event.tags.like(like)
    )
    if person_id:
        stmt = stmt.where(Event.person_id == person_id)
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    evs = list(session.scalars(
        stmt.order_by(desc(Event.event_date), desc(Event.id)).limit(limit)
    ))
    return {
        "q": q, "mode": "like",
        "items": [{
            "id": e.id, "type_key": e.type_key,
            "event_date": event_date_str(e.event_date),
            "event_time": event_time_str(e.event_date),
            "person_id": e.person_id, "person_name": names.get(e.person_id),
            "title": e.title, "snippet": (e.body or "")[:120],
        } for e in evs],
    }
