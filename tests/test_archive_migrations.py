"""迁移与 Schema 增量验证 — 真实 MySQL + 真实 Alembic。

严格要求：
- 禁止 SQLite 回退，方言必须是 MySQL/MariaDB
- 禁止手动 stamp 或 metadata.create_all；必须用 alembic downgrade/upgrade 执行真实迁移
- 验证新增表 idempotency_keys 为增量且可逆，不触碰已有 IDs/relations/dates
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import inspect, text


def test_mysql_dialect_is_mysql(db_engine):
    assert "mysql" in db_engine.url.drivername
    assert "sqlite" not in db_engine.url.drivername
    # 额外检查版本
    with db_engine.connect() as conn:
        ver = conn.execute(text("SELECT VERSION()")).scalar()
        assert ver is not None
        # MySQL 8.x 或 MariaDB 11.x
        assert "8." in ver or "11." in ver or "MariaDB" in ver


def test_idempotency_table_exists_mysql(db_engine):
    insp = inspect(db_engine)
    tables = insp.get_table_names()
    assert "idempotency_keys" in tables
    cols = {c["name"] for c in insp.get_columns("idempotency_keys")}
    assert {"idempotency_key", "request_hash", "response_status", "response_body", "scope"} <= cols
    # 唯一约束在 idempotency_key 上
    uniq = insp.get_unique_constraints("idempotency_keys")
    indexes = insp.get_indexes("idempotency_keys")
    names = [u.get("name") for u in uniq] + [i.get("name") for i in indexes]
    # 至少有一个约束/索引包含 idempotency_key
    assert any("idempotency" in (n or "") for n in names)
    # 检查类型为 MySQL 兼容
    col_types = {c["name"]: str(c["type"]) for c in insp.get_columns("idempotency_keys")}
    # idempotency_key 应为 VARCHAR
    assert "VARCHAR" in col_types["idempotency_key"].upper()


def test_alembic_heads_up_to_date_real(db_engine):
    with db_engine.connect() as conn:
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert rev == "f1a2b3c4d5e6"


def test_real_migration_additive_preserves_data(db_engine):
    """真实增量迁移验证：old head -> seed -> upgrade -> downgrade -> upgrade。

    步骤：
    1. downgrade 到 b2f7c0a91d34（idempotency 之前的 head）
    2. 验证 idempotency_keys 不存在
    3. 插入原始表数据（persons/events/wardrobe）并记录 IDs/dates
    4. upgrade 到 head，验证数据原样保留且新表出现
    5. downgrade 回 b2f7c0a91d34，验证新表消失但原始数据仍保留
    6. upgrade 回 head 供后续测试
    """
    from pathlib import Path
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    from backend.config import settings
    from backend.db import SessionLocal

    repo_root = Path(__file__).resolve().parents[1]
    ini = repo_root / "alembic.ini"
    acfg = AlembicConfig(str(ini))
    acfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

    # 确保从 head 开始
    alembic_command.upgrade(acfg, "head")

    # 1. downgrade 到前一版本
    alembic_command.downgrade(acfg, "b2f7c0a91d34")
    insp = inspect(db_engine)
    assert "idempotency_keys" not in insp.get_table_names()
    # 旧表仍在
    for t in ["persons", "events", "wardrobe_items", "outfit_wears", "media", "audit_log"]:
        assert t in insp.get_table_names(), f"{t} 应在 downgrade 后仍存在"

    # 2. 插入原始数据
    from backend.models import Person, Event, WardrobeItem, OutfitWear, EventPerson, Media

    pid1 = pid2 = eid = wid = None
    today = dt.date.today()
    now = dt.datetime.now()
    s = SessionLocal()
    try:
        p1 = Person(display_name=f"__mig_a_{uuid.uuid4().hex[:6]}", relation_type="friend")
        p2 = Person(display_name=f"__mig_b_{uuid.uuid4().hex[:6]}", relation_type="partner", gender="female")
        s.add_all([p1, p2])
        s.flush()
        pid1, pid2 = p1.id, p2.id
        # event with date
        ev = Event(person_id=pid1, type_key="outfit", event_date=now, title="mig-event", body="body", sensitivity="normal", source="web")
        s.add(ev)
        s.flush()
        eid = ev.id
        wi = WardrobeItem(person_id=pid1, category="top", name=f"__mig_item_{uuid.uuid4().hex[:6]}", color="blue", color_key="blue")
        s.add(wi)
        s.flush()
        wid = wi.id
        s.add_all([
            OutfitWear(event_id=eid,item_id=wid,slot="top"),
            EventPerson(event_id=eid,person_id=pid2),
            Media(person_id=pid1,event_id=eid,wardrobe_item_id=wid,kind="image",path="synthetic/migration.png",bytes=10,captured_on=today),
        ])
        s.commit()
    finally:
        s.close()

    # 记录 downgrade 后的原始数据快照
    with db_engine.connect() as conn:
        persons_before = list(conn.execute(text("SELECT id, display_name, relation_type FROM persons WHERE id IN (:a, :b)").bindparams(a=pid1, b=pid2)))
        events_before = list(conn.execute(text("SELECT id, title, type_key FROM events WHERE id=:eid").bindparams(eid=eid)))
        wardrobe_before = list(conn.execute(text("SELECT id, name, category FROM wardrobe_items WHERE id=:wid").bindparams(wid=wid)))
        cnt_persons_before = conn.execute(text("SELECT COUNT(*) FROM persons")).scalar()
        cnt_events_before = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
        cnt_wardrobe_before = conn.execute(text("SELECT COUNT(*) FROM wardrobe_items")).scalar()
        before_relations = {table: list(conn.execute(text(f"SELECT * FROM {table} ORDER BY 1, 2"))) for table in ("events","wardrobe_items","outfit_wears","event_persons","media")}

    assert len(persons_before) == 2
    assert len(events_before) == 1 and events_before[0][1] == "mig-event"
    assert len(wardrobe_before) == 1

    # 3. upgrade 到 head
    alembic_command.upgrade(acfg, "head")
    insp2 = inspect(db_engine)
    assert "idempotency_keys" in insp2.get_table_names()
    # 验证原始数据未被改动
    with db_engine.connect() as conn:
        persons_after = list(conn.execute(text("SELECT id, display_name, relation_type FROM persons WHERE id IN (:a, :b)").bindparams(a=pid1, b=pid2)))
        events_after = list(conn.execute(text("SELECT id, title, type_key FROM events WHERE id=:eid").bindparams(eid=eid)))
        wardrobe_after = list(conn.execute(text("SELECT id, name, category FROM wardrobe_items WHERE id=:wid").bindparams(wid=wid)))
        assert persons_before == persons_after
        assert events_before == events_after
        assert wardrobe_before == wardrobe_after
        assert conn.execute(text("SELECT COUNT(*) FROM persons")).scalar() == cnt_persons_before
        assert conn.execute(text("SELECT COUNT(*) FROM events")).scalar() == cnt_events_before
        assert conn.execute(text("SELECT COUNT(*) FROM wardrobe_items")).scalar() == cnt_wardrobe_before
        for table, rows in before_relations.items():
            assert list(conn.execute(text(f"SELECT * FROM {table} ORDER BY 1, 2"))) == rows, table
        # 新表可用
        cols = {c["name"] for c in insp2.get_columns("idempotency_keys")}
        assert {"idempotency_key", "request_hash", "scope"} <= cols
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev == "f1a2b3c4d5e6"

    # 4. 验证新表可写入
    s2 = SessionLocal()
    try:
        from backend.models import IdempotencyKey
        ik = IdempotencyKey(idempotency_key=f"__mig_test_{uuid.uuid4().hex}", scope="events", request_hash="abc", response_status=201, response_body="{}")
        s2.add(ik)
        s2.flush()
        s2.rollback()
    finally:
        s2.close()

    # 5. downgrade 再验证可逆且不丢原始数据
    alembic_command.downgrade(acfg, "b2f7c0a91d34")
    insp3 = inspect(db_engine)
    assert "idempotency_keys" not in insp3.get_table_names()
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM persons WHERE id IN (:a, :b)").bindparams(a=pid1, b=pid2)).scalar() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM events WHERE id=:eid").bindparams(eid=eid)).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM wardrobe_items WHERE id=:wid").bindparams(wid=wid)).scalar() == 1
        for table, rows in before_relations.items():
            assert list(conn.execute(text(f"SELECT * FROM {table} ORDER BY 1, 2"))) == rows, table
        # audit 等仍在
        assert "audit_log" in inspect(db_engine).get_table_names()

    # 6. 升回 head 供后续测试
    alembic_command.upgrade(acfg, "head")
    assert "idempotency_keys" in inspect(db_engine).get_table_names()

    # 清理种子数据（通过 Session 删除，验证外键级联不误删）
    s3 = SessionLocal()
    try:
        from backend.models import Person, Event, WardrobeItem
        for model, mid in [(Event, eid), (WardrobeItem, wid), (Person, pid1), (Person, pid2)]:
            obj = s3.get(model, mid)
            if obj:
                s3.delete(obj)
                s3.flush()
        s3.commit()
    finally:
        s3.close()

    # 最终确认回到 head
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "f1a2b3c4d5e6"
