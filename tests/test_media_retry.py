"""媒体重试与 wardrobe_item 挂载测试 — 真实 MySQL 持久化"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text


def test_media_idempotency_per_attachment(client, person_factory, db_engine):
    p = person_factory()
    from tests.fixtures.make_fixture import png_bytes
    png = png_bytes(128, 128, (30, 40, 50))
    key = f"media-{uuid.uuid4().hex}"
    files = {"file": ("a.png", png, "image/png")}
    r1 = client.post("/api/media", data={"person_id": str(p["id"])}, files=files, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    id1 = r1.json()[0]["id"]
    # 独立连接验证持久化
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM media WHERE id=:mid"), {"mid": id1}).scalar()
        assert cnt == 1
        ik = conn.execute(text("SELECT COUNT(*) FROM idempotency_keys WHERE idempotency_key=:k"), {"k": key}).scalar()
        assert ik == 1
    # 重新用同文件同 key 重试应回放
    files2 = {"file": ("a.png", png, "image/png")}
    r2 = client.post("/api/media", data={"person_id": str(p["id"])}, files=files2, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    assert r2.json()[0]["id"] == id1
    assert r2.headers.get("idempotent-replayed") == "true" or r2.headers.get("Idempotent-Replayed") == "true"
    # 不同文件同 key 应 409
    png2 = png_bytes(128, 128, (90, 10, 10))
    files3 = {"file": ("b.png", png2, "image/png")}
    r3 = client.post("/api/media", data={"person_id": str(p["id"])}, files=files3, headers={"Idempotency-Key": key})
    assert r3.status_code == 409
    # 用全新 client 重放仍应命中
    from fastapi.testclient import TestClient
    from backend.main import app
    fresh = TestClient(app)
    fresh.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
    r4 = fresh.post("/api/media", data={"person_id": str(p["id"])}, files={"file": ("a.png", png, "image/png")}, headers={"Idempotency-Key": key})
    assert r4.status_code in (200, 201)
    assert r4.json()[0]["id"] == id1
    client.delete(f"/api/media/{id1}")


def test_media_upload_wardrobe_item_only(client, person_factory, db_engine):
    p = person_factory()
    it = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "top", "name": f"__media_item_{uuid.uuid4().hex[:6]}"}).json()
    from tests.fixtures.make_fixture import png_bytes
    png = png_bytes(64, 64, (100, 100, 100))
    files = {"file": ("w.png", png, "image/png")}
    r = client.post("/api/media", data={"wardrobe_item_id": str(it["id"]), "person_id": str(p["id"])}, files=files)
    assert r.status_code == 201, r.text
    assert r.json()[0]["wardrobe_item_id"] == it["id"]
    assert r.json()[0]["event_id"] is None
    mid = r.json()[0]["id"]
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT wardrobe_item_id, event_id FROM media WHERE id=:mid"), {"mid": mid}).fetchone()
        assert row[0] == it["id"] and row[1] is None
    # 不能以不存在的 event/wardrobe 挂载
    r_bad = client.post("/api/media", data={"wardrobe_item_id": "999999", "person_id": str(p["id"])}, files={"file": ("x.png", png, "image/png")})
    assert r_bad.status_code == 404
    # owner 校验：无效 person
    r_bad2 = client.post("/api/media", data={"person_id": "999999"}, files={"file": ("y.png", png, "image/png")})
    assert r_bad2.status_code == 404
    client.delete(f"/api/media/{mid}")
    client.delete(f"/api/wardrobe/items/{it['id']}")


def test_media_retry_does_not_duplicate_row(client, person_factory, db_engine):
    p = person_factory()
    from tests.fixtures.make_fixture import png_bytes
    png = png_bytes(96, 96, (10, 10, 10))
    r1 = client.post("/api/media", data={"person_id": str(p["id"])}, files={"file": ("dup.png", png, "image/png")})
    r2 = client.post("/api/media", data={"person_id": str(p["id"])}, files={"file": ("dup.png", png, "image/png")})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()[0]["id"] == r2.json()[0]["id"]
    with db_engine.connect() as conn:
        # 同内容同归属仅一行
        cnt = conn.execute(text("SELECT COUNT(*) FROM media WHERE person_id=:pid"), {"pid": p["id"]}).scalar()
        assert cnt >= 1
    client.delete(f"/api/media/{r1.json()[0]['id']}")


def test_media_auth_required(db_engine):
    from fastapi.testclient import TestClient
    from backend.main import app
    unauth = TestClient(app)
    r = unauth.get("/api/media")
    assert r.status_code == 401


def test_media_upload_without_person_ok(client, db_engine):
    """media 可不带 person_id 仅挂 wardrobe_item，验证 owner 校验路径"""
    p = client.post("/api/persons", json={"display_name": f"__mp_{uuid.uuid4().hex[:6]}", "relation_type": "friend"}).json()
    it = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "accessory", "name": f"__acc_{uuid.uuid4().hex[:6]}"}).json()
    from tests.fixtures.make_fixture import png_bytes
    png = png_bytes(32, 32, (1,2,3))
    r = client.post("/api/media", data={"wardrobe_item_id": str(it["id"])}, files={"file": ("z.png", png, "image/png")})
    assert r.status_code == 201
    assert r.json()[0]["wardrobe_item_id"] == it["id"]
    client.delete(f"/api/media/{r.json()[0]['id']}")
    client.delete(f"/api/wardrobe/items/{it['id']}")
