"""幂等键测试：并发、重放、载荷不匹配、事务回滚、scope 隔离、DELETE 重放（backend lane）"""
from __future__ import annotations

import datetime as dt
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text


def test_event_idempotency_replay_same_key(client, person_factory):
    p = person_factory()
    key = f"evt-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": "idem-a"}
    r1 = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    id1 = r1.json()["id"]
    r2 = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["id"] == id1
    assert r2.headers.get("idempotent-replayed") == "true" or r2.headers.get("Idempotent-Replayed") == "true"
    all_events = client.get("/api/events", params={"person_id": p["id"]}).json()
    cnt = sum(1 for e in all_events.get("items", []) if e.get("title") == "idem-a")
    assert cnt == 1
    client.delete(f"/api/events/{id1}")


def test_event_idempotency_mismatch_409(client, person_factory):
    p = person_factory()
    key = f"evt-{uuid.uuid4().hex}"
    payload1 = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": "idem-b1"}
    payload2 = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": "idem-b2-different"}
    r1 = client.post("/api/events", json=payload1, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    r2 = client.post("/api/events", json=payload2, headers={"Idempotency-Key": key})
    assert r2.status_code == 409, r2.text
    client.delete(f"/api/events/{r1.json()['id']}")


def test_scope_isolation_same_key_different_endpoint(client, person_factory):
    """同 key 在不同 scope 必须视为冲突/不重放（scope 校验）。"""
    p = person_factory()
    # 先在 events 上占位
    key = f"scope-{uuid.uuid4().hex}"
    payload_event = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": "scope-a"}
    r1 = client.post("/api/events", json=payload_event, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    # 尝试在 wardrobe 上复用同 key，即使 hash 巧合也应 409 scope mismatch
    # 直接在 DB 层面验证 scope 已持久化
    from backend.db import SessionLocal
    s = SessionLocal()
    try:
        row = s.execute(text("SELECT scope, request_hash FROM idempotency_keys WHERE idempotency_key=:k"), {"k": key}).fetchone()
        assert row is not None
        assert row[0] == "events"
        # 尝试用同一 key 但 scope=wardrobe_items 去 claim，期望 scope 冲突
        from backend.services import idempotency as idem
        # 用同一 hash 但不同 scope 调用 try_claim，应抛 409 scope mismatch
        try:
            idem.try_claim(s, key, "wardrobe_items", row[1])
            assert False, "scope mismatch 应 409"
        except Exception as e:
            # FastAPI HTTPException
            assert getattr(e, "status_code", None) == 409
            assert "scope" in str(e.detail).lower() or "scope" in str(e).lower()
        s.rollback()
    finally:
        s.close()
    # 用 ward 端点真实请求同 key 不同 payload 也应 409（hash mismatch 或 scope mismatch）
    payload_ward = {"person_id": p["id"], "category": "top", "name": f"__scope_{uuid.uuid4().hex[:6]}"}
    r2 = client.post("/api/wardrobe/items", json=payload_ward, headers={"Idempotency-Key": key})
    assert r2.status_code == 409, r2.text
    client.delete(f"/api/events/{r1.json()['id']}")


def test_wardrobe_item_idempotency_replay(client, person_factory):
    p = person_factory()
    key = f"ward-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "category": "top", "name": f"__idem_top_{uuid.uuid4().hex[:6]}"}
    r1 = client.post("/api/wardrobe/items", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    id1 = r1.json()["id"]
    r2 = client.post("/api/wardrobe/items", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    assert r2.json()["id"] == id1
    assert r2.headers.get("idempotent-replayed") == "true" or r2.headers.get("Idempotent-Replayed") == "true"
    lst = client.get("/api/wardrobe/items", params={"person_id": p["id"]}).json()
    assert sum(1 for i in lst.get("items", []) if i["id"] == id1) == 1
    payload2 = {"person_id": p["id"], "category": "top", "name": f"__idem_top_diff_{uuid.uuid4().hex[:6]}"}
    r3 = client.post("/api/wardrobe/items", json=payload2, headers={"Idempotency-Key": key})
    assert r3.status_code == 409
    client.delete(f"/api/wardrobe/items/{id1}")


def test_outfit_idempotency_replay_and_tx_rollback(client, person_factory):
    p = person_factory()
    item = client.post("/api/wardrobe/items", json={"person_id": p["id"], "category": "top", "name": f"__idem_outfit_{uuid.uuid4().hex[:6]}"}).json()
    today = dt.date.today().isoformat()
    key = f"outfit-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "event_date": today, "items": [{"item_id": item["id"]}]}
    r1 = client.post("/api/outfits", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201, r1.text
    outfit_id = r1.json()["id"]
    r2 = client.post("/api/outfits", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    assert r2.json()["id"] == outfit_id
    # 事务回滚：坏 payload 的 key 不应阻塞后续同 key 成功请求（占位已回滚）
    bad_payload = {"person_id": p["id"], "event_date": today, "items": [{"item_id": 999999}]}
    bad_key = f"outfit-bad-{uuid.uuid4().hex}"
    r_bad = client.post("/api/outfits", json=bad_payload, headers={"Idempotency-Key": bad_key})
    assert r_bad.status_code in (400, 422, 404)
    # 同 bad_key 但换成好 payload：若占位未清理，会 409；正确行为应 201（或 409 hash mismatch 若仍保留）
    # 契约：失败事务不应永久阻塞 key；坏 key 的重试若 hash 相同应 409 payload mismatch，若不同 hash 也是 409
    # 但此处 bad_key 已失败，尝试用同 key 不同 payload 触发 hash mismatch 409，验证隔离
    r_ok_same_key_diff_payload = client.post("/api/outfits", json=payload, headers={"Idempotency-Key": bad_key})
    # 坏事务已回滚，占位已清理；同 key 不同 payload 应视为新请求成功（201），而非被旧失败阻塞
    assert r_ok_same_key_diff_payload.status_code == 201, r_ok_same_key_diff_payload.text
    new_id = r_ok_same_key_diff_payload.json()["id"]
    # 而全新 key 的好 payload 也必须成功且为不同 id（两次独立创建）
    fresh_key = f"outfit-fresh-{uuid.uuid4().hex}"
    r_ok = client.post("/api/outfits", json=payload, headers={"Idempotency-Key": fresh_key})
    assert r_ok.status_code == 201, r_ok.text
    assert r_ok.json()["id"] != new_id
    client.delete(f"/api/events/{outfit_id}")
    client.delete(f"/api/events/{new_id}")
    client.delete(f"/api/events/{r_ok.json()['id']}")
    client.delete(f"/api/wardrobe/items/{item['id']}")


def test_transaction_rollback_placeholder_cleaned(client, person_factory, db_engine):
    """坏事务的占位应被回滚，不阻塞使用同一 key 的后续正确请求（新 key）且旧 key 不残留错误阻塞。"""
    p = person_factory()
    bad_key = f"txrb-{uuid.uuid4().hex}"
    bad_payload = {"person_id": p["id"], "type_key": "text", "event_date": "not-a-date", "title": "bad"}
    r_bad = client.post("/api/events", json=bad_payload, headers={"Idempotency-Key": bad_key})
    assert r_bad.status_code in (400, 422)
    # 检查 DB 中该 key 若存在则 response_body 为空应被清理或允许复用
    # 正确实现：外层事务回滚，行不存在；或若存在则可被覆盖
    with db_engine.connect() as conn:
        row = conn.execute(text("SELECT response_body FROM idempotency_keys WHERE idempotency_key=:k"), {"k": bad_key}).fetchone()
        assert row is None
        # 要么不存在，要么 response_body 仍为空但不阻塞新 key；我们验证用新 key 能成功
    fresh_key = f"txrb-good-{uuid.uuid4().hex}"
    good = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": f"good-{uuid.uuid4().hex[:6]}"}
    r_good = client.post("/api/events", json=good, headers={"Idempotency-Key": fresh_key})
    assert r_good.status_code == 201
    client.delete(f"/api/events/{r_good.json()['id']}")


def test_concurrent_http_true_parallel(db_engine, person_factory):
    """真实并发：Barrier 同步两个独立 TestClient 同时 POST 同 key，同事务仅写一次。"""
    # person_factory 依赖 client fixture，但我们需要独立 clients，故手动建 person
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db import get_session, SessionLocal
    # 建人（默认 get_session 已是独立会话，无需覆盖）
    c0 = TestClient(app)
    c0.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
    pr = c0.post("/api/persons", json={"display_name": f"__conc_{uuid.uuid4().hex[:6]}", "relation_type": "friend"})
    assert pr.status_code == 201, pr.text
    pid = pr.json()["id"]

    key = f"conc-{uuid.uuid4().hex}"
    payload = {"person_id": pid, "type_key": "text", "event_date": dt.date.today().isoformat(), "title": f"conc-{uuid.uuid4().hex[:6]}"}

    barrier = threading.Barrier(2)
    results: list = []

    def do_post():
        c = TestClient(app)
        c.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            return None
        # 故意让两个线程尽量同时进入 try_claim 的 savepoint
        r = c.post("/api/events", json=payload, headers={"Idempotency-Key": key})
        try:
            body = r.json()
        except Exception:
            body = r.text
        return (r.status_code, body, dict(r.headers))

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(do_post)
        f2 = ex.submit(do_post)
        r1 = f1.result(timeout=10)
        r2 = f2.result(timeout=10)

    assert r1 is not None and r2 is not None
    # 两者都应成功且返回同一 id，恰好一个为回放
    assert r1[0] in (200, 201) and r2[0] in (200, 201), f"{r1} {r2}"
    id1 = r1[1]["id"] if isinstance(r1[1], dict) else None
    id2 = r2[1]["id"] if isinstance(r2[1], dict) else None
    assert id1 == id2 and id1 is not None
    #恰好一个标记为 replay
    replay_flags = []
    for r in (r1, r2):
        h = {k.lower(): v for k, v in r[2].items()}
        replay_flags.append(h.get("idempotent-replayed") == "true")
    assert replay_flags.count(True) == 1

    # 持久化校验：独立连接查询仅写一次
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM events WHERE id=:eid"), {"eid": id1}).scalar()
        assert cnt == 1
        ik_cnt = conn.execute(text("SELECT COUNT(*) FROM idempotency_keys WHERE idempotency_key=:k"), {"k": key}).scalar()
        assert ik_cnt == 1
        # 同标题事件仅一条
        t = payload["title"]
        cnt2 = conn.execute(text("SELECT COUNT(*) FROM events WHERE title=:t AND person_id=:pid"), {"t": t, "pid": pid}).scalar()
        assert cnt2 == 1

    # 清理
    c0.delete(f"/api/events/{id1}")
    # 不在此处复原，交给后续 client fixture


def test_response_loss_fresh_client_replay(client, person_factory, db_engine):
    p = person_factory()
    key = f"loss-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": "loss-test"}
    r1 = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    body1 = r1.json()
    # 用全新 TestClient/独立 DB session 重放（模拟客户端丢失响应后重试）
    from fastapi.testclient import TestClient
    from backend.main import app
    fresh = TestClient(app)
    fresh.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
    r2 = fresh.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    b2 = r2.json()
    assert b2["id"] == body1["id"]
    assert b2["title"] == body1["title"]
    assert b2["event_date"] == body1["event_date"]
    # 回放头部
    assert r2.headers.get("idempotent-replayed") == "true" or r2.headers.get("Idempotent-Replayed") == "true"
    # 持久化二次校验：独立连接仍只一条
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM events WHERE id=:eid"), {"eid": body1["id"]}).scalar()
        assert cnt == 1
    client.delete(f"/api/events/{body1['id']}")


def test_delete_then_replay_still_returns_original(client, person_factory, db_engine):
    """DELETE 后原 key 重放应仍返回原始 201 响应（幂等响应持久化），不新建。"""
    p = person_factory()
    key = f"delreplay-{uuid.uuid4().hex}"
    payload = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": f"del-{uuid.uuid4().hex[:6]}"}
    r1 = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    eid = r1.json()["id"]
    body1 = r1.json()
    # 删除
    rdel = client.delete(f"/api/events/{eid}")
    assert rdel.status_code == 204
    # 确认 GET 已无
    with db_engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM events WHERE id=:eid"), {"eid": eid}).scalar()
        assert cnt == 0
    # 重放
    r2 = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code in (200, 201)
    b2 = r2.json()
    assert b2["id"] == body1["id"]
    assert b2["title"] == body1["title"]
    # 头部标记回放
    assert r2.headers.get("idempotent-replayed") == "true" or r2.headers.get("Idempotent-Replayed") == "true"
    # 不应新建第二条
    with db_engine.connect() as conn:
        ik = conn.execute(text("SELECT COUNT(*) FROM idempotency_keys WHERE idempotency_key=:k"), {"k": key}).scalar()
        assert ik == 1


def test_no_idempotency_header_still_creates(client, person_factory):
    p = person_factory()
    payload = {"person_id": p["id"], "type_key": "text", "event_date": dt.date.today().isoformat(), "title": f"no-key-{uuid.uuid4().hex[:6]}"}
    r1 = client.post("/api/events", json=payload)
    r2 = client.post("/api/events", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    client.delete(f"/api/events/{r1.json()['id']}")
    client.delete(f"/api/events/{r2.json()['id']}")
