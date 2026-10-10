"""核心资源：配置、人、模块开关、属性、关系边。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import CommitRoute, get_session
from ..models import Attribute, Event, Interaction, Media, Person, PersonModule, PersonRelation
from ..services import media as media_svc
from ..schemas import (
    AttributeIn,
    AttributeOut,
    ModulesIn,
    PersonIn,
    PersonOut,
    PersonPatch,
    RelationIn,
)
from ..services.audit import write_audit

router = APIRouter(prefix="/api", tags=["core"], route_class=CommitRoute)


# ---------------------------------------------------------------- 配置

@router.get("/config")
def get_config():
    """把 config.toml 里的「关系类型 / 模块 / 属性分类」暴露给前端。
    前端据此渲染模块开关与属性分组 —— 这就是「通用」的落点。"""
    return {
        "app_title": settings.app_title,
        "locale": settings.locale,
        "timezone": settings.timezone,
        "relation_types": settings.relation_types,
        "modules": settings.modules,
        "attribute_categories": settings.attribute_categories,
        # 服装：单品类别（key/label/slot）与判重同义词表 —— 前端渲染与提示都读这里
        "wardrobe": {
            "categories": settings.wardrobe_categories,
            "synonyms": settings.wardrobe_synonyms,
        },
        "reminder": {
            "daily_digest_time": settings.daily_digest_time,
            "no_contact_days": settings.no_contact_days,
            "upcoming_days": settings.upcoming_days,
            "cycle_window_margin_days": settings.cycle_window_margin_days,
        },
        "event_types": [
            {"key": "text", "label": "文字", "icon": "edit"},
            # module = 对应的功能模块开关；没写 module 的类型任何时候都能记
            {"key": "outfit", "label": "服装", "icon": "dress", "module": "outfit"},
            {"key": "period", "label": "生理期", "icon": "calendar", "module": "cycle"},
            {"key": "meeting", "label": "相处", "icon": "friends", "module": "interaction"},
            {"key": "gift", "label": "礼物", "icon": "gift", "module": "gift"},
            {"key": "health", "label": "健康", "icon": "health", "module": "health"},
            {"key": "mood", "label": "情绪", "icon": "smile"},
            {"key": "milestone", "label": "里程碑", "icon": "star"},
            {"key": "contact", "label": "联系", "icon": "phone", "module": "contact"},
            {"key": "hobby", "label": "爱好", "icon": "music-o"},
            {"key": "social", "label": "社交", "icon": "friends-o"},
        ],
    }


# ---------------------------------------------------------------- 人

def _with_via_name(session: Session, person: Person) -> Person:
    """把「通过谁认识」的名字一起带出去（前端要显示人名而不是 id）。"""
    if person.via_person_id:
        via = session.get(Person, person.via_person_id)
        person.via_name = via.display_name if via else None
    else:
        person.via_name = None
    return person


@router.get("/persons", response_model=List[PersonOut])
def list_persons(include_inactive: bool = False, circle: Optional[str] = None,
                 session: Session = Depends(get_session)):
    stmt = select(Person).order_by(Person.sort_order, Person.id)
    if not include_inactive:
        stmt = stmt.where(Person.active.is_(True))
    if circle:
        stmt = stmt.where(Person.circle == circle)
    rows = list(session.scalars(stmt))
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    for p in rows:
        p.via_name = names.get(p.via_person_id) if p.via_person_id else None
    return rows


@router.post("/persons", response_model=PersonOut, status_code=201)
def create_person(payload: PersonIn, session: Session = Depends(get_session)):
    data = payload.model_dump()
    module_keys = data.pop("modules", None)
    # 她那边的人（间接认识、信息多来自转述）默认按敏感处理，除非显式指定
    if data.get("circle") == "partner" and data.get("sensitivity", "normal") == "normal":
        data["sensitivity"] = "sensitive"
    person = Person(**data)
    session.add(person)
    session.flush()
    keys = module_keys if module_keys is not None else settings.default_modules_for(person.relation_type)
    for k in keys:
        session.add(PersonModule(person_id=person.id, module_key=k, enabled=True))
    write_audit(session, "person", person.id, "create")
    session.flush()
    return _with_via_name(session, person)


@router.get("/persons/{person_id}", response_model=PersonOut)
def get_person(person_id: int, session: Session = Depends(get_session)):
    person = session.get(Person, person_id)
    if not person:
        raise HTTPException(404, "找不到这个人")
    return _with_via_name(session, person)


@router.patch("/persons/{person_id}", response_model=PersonOut)
def patch_person(person_id: int, payload: PersonPatch, session: Session = Depends(get_session)):
    person = session.get(Person, person_id)
    if not person:
        raise HTTPException(404, "找不到这个人")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(person, k, v)
    write_audit(session, "person", person_id, "update")
    session.flush()
    return _with_via_name(session, person)


@router.delete("/persons/{person_id}", status_code=204)
def delete_person(person_id: int, session: Session = Depends(get_session)):
    person = session.get(Person, person_id)
    if not person:
        raise HTTPException(404, "找不到这个人")
    if person.is_self:
        # 「我」这条记录是礼物方向、双人事件、相处记录的锚点，
        # 有数据时删掉会把它们变成孤儿；空记录允许删除（便于测试与重建）。
        used = (
            session.scalar(select(func.count()).select_from(Event).where(Event.person_id == person_id))
            or session.scalar(select(func.count()).select_from(Attribute).where(Attribute.person_id == person_id))
            or session.scalar(select(func.count()).select_from(Interaction).where(Interaction.person_id == person_id))
        )
        if used:
            raise HTTPException(400, "「我」有记录时不允许删除（请先清理或改为停用）")
    # 数据库行由外键级联删除，但磁盘文件不会 —— 必须显式清，否则留一堆孤儿图片
    rows = list(session.scalars(select(Media).where(Media.person_id == person_id)))
    for m in rows:
        media_svc.delete_files(m.path, m.thumb_path, m.source_path)
    # 该人事件上挂的图片同样处理
    for m in session.scalars(
        select(Media).where(Media.event_id.in_(select(Event.id).where(Event.person_id == person_id)))
    ):
        media_svc.delete_files(m.path, m.thumb_path, m.source_path)
    session.delete(person)
    write_audit(session, "person", person_id, "delete")
    return None


# ---------------------------------------------------------------- 模块开关

@router.get("/persons/{person_id}/modules")
def get_modules(person_id: int, session: Session = Depends(get_session)):
    rows = list(session.scalars(
        select(PersonModule).where(PersonModule.person_id == person_id)
    ))
    enabled = {r.module_key for r in rows if r.enabled}
    return {
        "enabled": sorted(enabled),
        "available": [m.get("key") for m in settings.modules],
    }


@router.put("/persons/{person_id}/modules")
def put_modules(person_id: int, payload: ModulesIn, session: Session = Depends(get_session)):
    if not session.get(Person, person_id):
        raise HTTPException(404, "找不到这个人")
    valid = {m.get("key") for m in settings.modules}
    wanted = {k for k in payload.modules if k in valid}
    rows = {r.module_key: r for r in session.scalars(
        select(PersonModule).where(PersonModule.person_id == person_id)
    )}
    for key in valid:
        on = key in wanted
        if key in rows:
            rows[key].enabled = on
        elif on:
            session.add(PersonModule(person_id=person_id, module_key=key, enabled=True))
    write_audit(session, "person_modules", person_id, "set")
    return {"enabled": sorted(wanted)}


# ---------------------------------------------------------------- 属性 KV

@router.get("/attributes", response_model=List[AttributeOut])
def list_attributes(person_id: Optional[int] = None, session: Session = Depends(get_session)):
    stmt = select(Attribute).order_by(Attribute.category, Attribute.id)
    if person_id:
        stmt = stmt.where(Attribute.person_id == person_id)
    return list(session.scalars(stmt))


@router.post("/attributes", response_model=AttributeOut, status_code=201)
def create_attribute(payload: AttributeIn, session: Session = Depends(get_session)):
    if not session.get(Person, payload.person_id):
        raise HTTPException(404, "找不到这个人")
    cat = settings.attribute_categories
    default_sens = "normal"
    for c in cat:
        if c.get("key") == payload.category:
            default_sens = c.get("sensitivity", "normal")
    attr = Attribute(**payload.model_dump())
    if payload.sensitivity == "normal":
        attr.sensitivity = default_sens
    session.add(attr)
    session.flush()
    write_audit(session, "attribute", attr.id, "create")
    return attr


@router.delete("/attributes/{attr_id}", status_code=204)
def delete_attribute(attr_id: int, session: Session = Depends(get_session)):
    attr = session.get(Attribute, attr_id)
    if not attr:
        raise HTTPException(404, "找不到该属性")
    session.delete(attr)
    write_audit(session, "attribute", attr_id, "delete")
    return None


# ---------------------------------------------------------------- 关系边

@router.get("/relations")
def list_relations(person_id: Optional[int] = None, session: Session = Depends(get_session)):
    names = {p.id: p.display_name for p in session.scalars(select(Person))}
    stmt = select(PersonRelation)
    if person_id:
        stmt = stmt.where(
            (PersonRelation.from_person_id == person_id) | (PersonRelation.to_person_id == person_id)
        )
    out = []
    for r in session.scalars(stmt.order_by(PersonRelation.id)):
        out.append({
            "id": r.id,
            "from_person_id": r.from_person_id,
            "from_name": names.get(r.from_person_id),
            "to_person_id": r.to_person_id,
            "to_name": names.get(r.to_person_id),
            "label": r.label,
            "notes": r.notes,
        })
    return out


@router.post("/relations", status_code=201)
def create_relation(payload: RelationIn, session: Session = Depends(get_session)):
    for pid in (payload.from_person_id, payload.to_person_id):
        if not session.get(Person, pid):
            raise HTTPException(404, "人物 %s 不存在" % pid)
    rel = PersonRelation(**payload.model_dump())
    session.add(rel)
    session.flush()
    write_audit(session, "person_relation", rel.id, "create")
    return {"id": rel.id}


@router.delete("/relations/{rel_id}", status_code=204)
def delete_relation(rel_id: int, session: Session = Depends(get_session)):
    rel = session.get(PersonRelation, rel_id)
    if not rel:
        raise HTTPException(404, "找不到该关系")
    session.delete(rel)
    write_audit(session, "person_relation", rel_id, "delete")
    return None
