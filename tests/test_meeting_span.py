"""相处记录的时间跨度：开始日 + 可选结束日（像「周五去、周日回」记成一条）。

守的性质：
  · 跨日 → 明细 ended_on 落库、overnight 派生为真、hours 置空（多日折小时没有意义）
  · 同日/回退到单日 → ended_on 归一成 NULL（同一种语义只有一种存法）
  · 改开始日把跨度改成负数 → 400，不能静默写坏明细
  · 删事件 → 明细一起带走，不留孤儿
"""


def _day(offset):
    import datetime as dt
    return (dt.date(2026, 8, 20) + dt.timedelta(days=offset)).isoformat()


def _rows(client, person_id, note_prefix):
    rows = client.get("/api/interactions", params={"person_id": person_id}).json()
    return [r for r in rows if (r.get("note") or "").startswith(note_prefix)]


def test_meeting_span_create_derives_overnight_and_drops_hours(client, person_factory):
    person = person_factory()
    created = client.post("/api/events", json={
        "person_id": person["id"], "type_key": "meeting",
        "event_date": _day(0), "ended_on": _day(2),
        "title": "span-create", "location": "某地",
        # 跨日时手填的 hours 必须被丢弃，否则统计会拿到一个假的小时数
        "hours": 3, "overnight": False,
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["meeting"]["ended_on"] == _day(2)
    assert body["meeting"]["span_days"] == 3
    assert body["meeting"]["span_nights"] == 2
    assert body["meeting"]["overnight"] is True
    assert body["meeting"]["hours"] is None

    rows = _rows(client, person["id"], "span-create")
    assert len(rows) == 1
    assert rows[0]["occurred_on"] == _day(0)
    assert rows[0]["ended_on"] == _day(2)
    assert rows[0]["overnight"] is True
    assert rows[0]["hours"] is None


def test_meeting_span_same_day_normalizes_to_single_day(client, person_factory):
    person = person_factory()
    body = client.post("/api/events", json={
        "person_id": person["id"], "type_key": "meeting",
        "event_date": _day(1), "ended_on": _day(1),
        "title": "span-same", "hours": 2.5, "overnight": True,
    }).json()
    assert body["meeting"]["ended_on"] is None
    assert body["meeting"]["span_days"] == 1
    assert body["meeting"]["overnight"] is True
    assert body["meeting"]["hours"] == 2.5
    rows = _rows(client, person["id"], "span-same")
    assert len(rows) == 1 and rows[0]["ended_on"] is None


def test_meeting_span_patch_syncs_and_rejects_negative_span(client, person_factory):
    person = person_factory()
    event_id = client.post("/api/events", json={
        "person_id": person["id"], "type_key": "meeting",
        "event_date": _day(0), "ended_on": _day(2), "title": "span-patch",
    }).json()["id"]

    # 收窄成单日：ended_on 归一成 NULL，过夜回到手控
    narrowed = client.patch(f"/api/events/{event_id}", json={
        "ended_on": None, "overnight": False, "hours": 4,
    })
    assert narrowed.status_code == 200, narrowed.text
    assert narrowed.json()["meeting"]["ended_on"] is None
    assert narrowed.json()["meeting"]["hours"] == 4

    # 重新跨日，再改开始日把跨度改成负数 → 必须 400，不能静默写坏明细
    assert client.patch(f"/api/events/{event_id}", json={"ended_on": _day(2)}).status_code == 200
    bad = client.patch(f"/api/events/{event_id}", json={"event_date": _day(5)})
    assert bad.status_code == 400, bad.text
    rows = _rows(client, person["id"], "span-patch")
    assert len(rows) == 1
    assert rows[0]["occurred_on"] == _day(0), "被拒绝的修改不能半写入"
    assert rows[0]["ended_on"] == _day(2)

    # 改开始日但同步改结束日：跨度跟着平移
    moved = client.patch(f"/api/events/{event_id}", json={
        "event_date": _day(5), "ended_on": _day(7),
    })
    assert moved.status_code == 200, moved.text
    rows = _rows(client, person["id"], "span-patch")
    assert rows[0]["occurred_on"] == _day(5) and rows[0]["ended_on"] == _day(7)

    # 删事件 → 明细无孤儿
    assert client.delete(f"/api/events/{event_id}").status_code == 204
    assert _rows(client, person["id"], "span-patch") == []


def test_meeting_span_limit_and_listing_meeting_block(client, person_factory):
    person = person_factory()
    too_long = client.post("/api/events", json={
        "person_id": person["id"], "type_key": "meeting",
        "event_date": _day(0), "ended_on": _day(400), "title": "span-long",
    })
    assert too_long.status_code == 400, too_long.text

    event_id = client.post("/api/events", json={
        "person_id": person["id"], "type_key": "meeting",
        "event_date": _day(0), "ended_on": _day(1), "title": "span-list",
    }).json()["id"]
    listed = client.get("/api/events", params={"person_id": person["id"]}).json()["items"]
    row = next(i for i in listed if i["id"] == event_id)
    assert row["meeting"]["ended_on"] == _day(1)
    assert row["meeting"]["span_nights"] == 1

    # 非相处事件不该带 meeting 块
    plain = client.post("/api/events", json={
        "person_id": person["id"], "event_date": _day(0), "title": "span-plain",
    }).json()
    assert plain["meeting"] is None
