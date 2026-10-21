import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.fixtures.make_fixture import png_bytes


def test_media_cross_owner_rejected(client, person_factory, db_engine):
    a, b = person_factory(), person_factory()
    item = client.post('/api/wardrobe/items', json={'person_id':a['id'],'category':'top','name':'owner-test'}).json()
    event = client.post('/api/events', json={'person_id':a['id'],'event_date':'2026-10-21'}).json()
    for target in [{'wardrobe_item_id':item['id']},{'event_id':event['id']}]:
        result = client.post('/api/media', data={'person_id':b['id'],**target}, files={'file':('synthetic.png',png_bytes(16,16,(1,2,3)),'image/png')})
        assert result.status_code == 409
    with db_engine.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM media WHERE person_id=:id'),{'id':b['id']}).scalar() == 0


def test_concurrent_different_keys_same_item_conflicts_not_500(client, person_factory, auth_headers):
    from backend.main import app
    p = person_factory()
    payload = {'person_id':p['id'],'name':'concurrent-single','category':'top'}
    barrier = threading.Barrier(2)
    def create(_):
        with TestClient(app) as c:
            barrier.wait(timeout=10)
            r = c.post('/api/wardrobe/items',json=payload,headers={**auth_headers,'Idempotency-Key':uuid.uuid4().hex})
            return r.status_code,r.json()
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(create,range(2)))
    assert sorted(s for s,_ in results) == [201,409]
    assert next(body for s,body in results if s==409)['detail']['existing_id'] == next(body for s,body in results if s==201)['id']
