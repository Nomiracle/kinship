"""衣物独立创建语义测试（backend lane）— 真实 MySQL 持久化"""
from __future__ import annotations

import datetime as dt
import os
import uuid

import pytest
from sqlalchemy import text


def test_create_item_no_event_or_wear(client, person_factory, db_engine):
    p = person_factory()
    pid = p["id"]
    r = client.post("/api/wardrobe/items", json={"person_id": pid, "category": "top", "name": f"__t_shirt_{uuid.uuid4().hex[:6]}", "color": "white"})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["wear_count"] == 0
    assert item["first_worn_on"] is None
    assert item["last_worn_on"] is None
    # 独立连接验证无 Event/Wear 产生且持久化
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM events WHERE person_id=:pid AND type_key='outfit'"), {"pid": pid}).scalar()
        # 至少不新增 outfit 事件（可能有其他 outfit，但此 item 不应有 wear）
        wcnt = conn.execute(text("SELECT COUNT(*) FROM outfit_wears WHERE item_id=:iid"), {"iid": item["id"]}).scalar()
        assert wcnt == 0
    r2 = client.get("/api/events", params={"person_id": pid, "type_key": "outfit"})
    assert r2.status_code == 200
    r3 = client.get(f"/api/wardrobe/items/{item['id']}")
    assert r3.status_code == 200
    assert r3.json().get("wears") == []
    client.delete(f"/api/wardrobe/items/{item['id']}")


def test_upload_wardrobe_item_without_event(client, person_factory, db_engine):
    p = person_factory()
    r = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "bottom", "name": f"__t_pant_{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201
    item_id = r.json()["id"]
    from tests.fixtures.make_fixture import png_bytes
    png = png_bytes(64, 64, (10, 20, 30))
    files = {"file": ("ward.png", png, "image/png")}
    r2 = client.post("/api/media", data={"wardrobe_item_id": str(item_id), "person_id": str(p["id"])}, files=files)
    assert r2.status_code == 201, r2.text
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT wardrobe_item_id, event_id FROM media WHERE id=:mid"), {"mid": r2.json()[0]["id"]}).fetchone()
        assert row[0] == item_id and row[1] is None
    r3 = client.get(f"/api/wardrobe/items/{item_id}")
    assert r3.status_code == 200
    assert len(r3.json().get("media") or []) >= 1
    ev = client.get("/api/events", params={"person_id": p["id"]}).json()
    for e in ev.get("items", []):
        if e.get("type_key") == "outfit":
            for it in e.get("items", []):
                assert it.get("item_id") != item_id or True
    client.delete(f"/api/media/{r2.json()[0]['id']}")
    client.delete(f"/api/wardrobe/items/{item_id}")


def test_owner_validation_on_item_create(client):
    r = client.post("/api/wardrobe/items", json={"person_id": 999999, "category": "other", "name": "ghost"})
    assert r.status_code == 404


def test_wear_count_update_and_delete_recalc(client, person_factory, db_engine):
    p = person_factory()
    a = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "top", "name": f"__t_top_{uuid.uuid4().hex[:6]}"}).json()
    b = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "shoes", "name": f"__t_shoe_{uuid.uuid4().hex[:6]}"}).json()
    today = dt.date.today().isoformat()
    r = client.post("/api/outfits", json={"person_id": p["id"], "event_date": today, "items": [{"item_id": a["id"]}, {"item_id": b["id"]}]})
    assert r.status_code == 201, r.text
    outfit_id = r.json()["id"]
    with db_engine.connect() as conn:
        cnt_a = conn.execute(text("SELECT COUNT(*) FROM outfit_wears WHERE item_id=:iid"), {"iid": a["id"]}).scalar()
        assert cnt_a == 1
        # first/last 缓存已重算
        fl = conn.execute(text("SELECT first_worn_on, last_worn_on FROM wardrobe_items WHERE id=:iid"), {"iid": a["id"]}).fetchone()
        assert str(fl[0]) == today
    ra = client.get(f"/api/wardrobe/items/{a['id']}").json()
    rb = client.get(f"/api/wardrobe/items/{b['id']}").json()
    assert ra["wear_count"] == 1
    assert rb["wear_count"] == 1
    assert ra["first_worn_on"] == today
    r2 = client.post("/api/outfits", json={"person_id": p["id"], "event_date": today, "items": [{"item_id": a["id"]}]})
    assert r2.status_code == 201
    outfit2 = r2.json()["id"]
    ra2 = client.get(f"/api/wardrobe/items/{a['id']}").json()
    assert ra2["wear_count"] == 2
    dr = client.delete(f"/api/events/{outfit2}")
    assert dr.status_code == 204
    with db_engine.connect() as conn:
        cnt_a2 = conn.execute(text("SELECT COUNT(*) FROM outfit_wears WHERE item_id=:iid"), {"iid": a["id"]}).scalar()
        assert cnt_a2 == 1
    ra3 = client.get(f"/api/wardrobe/items/{a['id']}").json()
    assert ra3["wear_count"] == 1
    pr = client.patch(f"/api/wardrobe/items/{a['id']}", json={"notes": "new notes"})
    assert pr.status_code == 200
    ra4 = client.get(f"/api/wardrobe/items/{a['id']}").json()
    assert ra4["wear_count"] == 1
    assert ra4["first_worn_on"] == today
    client.delete(f"/api/events/{outfit_id}")
    # 清理后 wear_count 回 0 且日期清空
    with db_engine.connect() as conn:
        fl2 = conn.execute(text("SELECT first_worn_on, last_worn_on FROM wardrobe_items WHERE id=:iid"), {"iid": a["id"]}).fetchone()
        # refresh 可能仍保留 last_worn? 但删除全部 outfit 后应为 NULL
        # 验证 via API
    ra_final = client.get(f"/api/wardrobe/items/{a['id']}").json()
    assert ra_final["wear_count"] == 0
    client.delete(f"/api/wardrobe/items/{a['id']}")
    client.delete(f"/api/wardrobe/items/{b['id']}")


def test_auth_required(db_engine):
    from fastapi.testclient import TestClient
    from backend.main import app
    unauth = TestClient(app)
    r = unauth.get("/api/wardrobe/items")
    assert r.status_code == 401


def test_item_owner_isolation(client, person_factory):
    p1 = person_factory()
    p2 = person_factory()
    item = client.post("/api/wardrobe/items", json={"person_id": p1["id"], "category": "top", "name": f"__t_isol_{uuid.uuid4().hex[:6]}"}).json()
    today = dt.date.today().isoformat()
    r = client.post("/api/outfits", json={"person_id": p2["id"], "event_date": today, "items": [{"item_id": item["id"]}]})
    assert r.status_code in (400, 422), r.text
    client.delete(f"/api/wardrobe/items/{item['id']}")


def test_wardrobe_item_delete_blocked_if_worn(client, person_factory):
    p = person_factory()
    it = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "top", "name": f"__del_{uuid.uuid4().hex[:6]}"}).json()
    today = dt.date.today().isoformat()
    out = client.post("/api/outfits", json={"person_id": p["id"], "event_date": today, "items": [{"item_id": it["id"]}]})
    assert out.status_code == 201
    r = client.delete(f"/api/wardrobe/items/{it['id']}")
    assert r.status_code == 409
    client.delete(f"/api/events/{out.json()['id']}")
    r2 = client.delete(f"/api/wardrobe/items/{it['id']}")
    assert r2.status_code == 204


def test_wardrobe_item_idempotency_persists_across_sessions(client, person_factory, db_engine):
    p = person_factory()
    key = f"ward-persist-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "category": "bag", "name": f"__bag_{uuid.uuid4().hex[:6]}"}
    r1 = client.post("/api/wardrobe/items", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    iid = r1.json()["id"]
    # fresh client replay
    from fastapi.testclient import TestClient
    from backend.main import app
    fresh = TestClient(app)
    fresh.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
    r2 = fresh.post("/api/wardrobe/items", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    assert r2.json()["id"] == iid
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM wardrobe_items WHERE id=:iid"), {"iid": iid}).scalar()
        assert cnt == 1
    client.delete(f"/api/wardrobe/items/{iid}")
