import uuid


def test_event_response_replay_matches_exact_body(client, person_factory):
    person = person_factory()
    key = uuid.uuid4().hex
    payload = {"person_id": person["id"], "event_date": "2026-10-21", "title": "exact-replay"}
    first = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    second = client.post("/api/events", json=payload, headers={"Idempotency-Key": key})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()


def test_date_filter_includes_last_day_time(client, person_factory):
    person = person_factory()
    for day, time in [("2026-10-21", "23:59:59"), ("2026-10-22", "00:00:01")]:
        response = client.post("/api/events", json={"person_id": person["id"], "event_date": day, "event_time": time, "title": "filter"})
        assert response.status_code == 201
    result = client.get("/api/events", params={"person_id": person["id"], "date_to": "2026-10-21"}).json()
    assert result["total"] == 1
    assert result["items"][0]["event_time"] == "23:59:59"


def test_outfit_edit_items_auto_text_and_no_history_loss(client, person_factory):
    person = person_factory()
    one = client.post("/api/wardrobe/items", json={"person_id": person["id"], "name": "one", "category": "top"}).json()
    two = client.post("/api/wardrobe/items", json={"person_id": person["id"], "name": "two", "category": "top"}).json()
    outfit = client.post("/api/outfits", json={"person_id": person["id"], "event_date": "2026-10-21", "items": [{"item_id": one["id"]}]}).json()
    updated = client.patch(f'/api/events/{outfit["id"]}', json={"items": [{"item_id": two["id"]}]}).json()
    assert "two" in updated["title"]
    assert client.get(f'/api/wardrobe/items/{one["id"]}').json()["wear_count"] == 0
    assert client.get(f'/api/wardrobe/items/{two["id"]}').json()["wear_count"] == 1
