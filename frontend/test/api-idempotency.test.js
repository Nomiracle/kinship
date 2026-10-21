import { test } from 'node:test'
import assert from 'node:assert/strict'
import { api } from '../src/api.js'

test('创建记录/穿搭/单品和上传均携带稳定幂等键，媒体 URL 不含口令', async () => {
  const previous = { fetch: globalThis.fetch, localStorage: globalThis.localStorage }
  globalThis.localStorage = { getItem: () => 'synthetic-only' }
  const calls = []
  globalThis.fetch = async (path, opts) => {
    calls.push({ path, ...opts })
    return { ok: true, status: 201, text: async () => '{"id":123}' }
  }
  try {
    await api.createEvent({ person_id: 1 }, 'event-key')
    await api.createOutfit({ person_id: 1 }, 'outfit-key')
    await api.createWardrobeItem({ person_id: 1 }, 'item-key')
    await api.uploadMedia(new Blob(['synthetic'], { type: 'image/png' }), { wardrobe_item_id: 2, idempotency_key: 'photo-key' })
    assert.deepEqual(calls.map(c => c.headers['Idempotency-Key']), ['event-key', 'outfit-key', 'item-key', 'photo-key'])
    assert.equal(calls[3].body.get('wardrobe_item_id'), '2')
    assert.equal(calls[3].body.has('event_id'), false)
    assert.equal(calls[3].headers['Content-Type'], undefined)
    assert.equal(api.mediaUrl({ path: 'test.png' }), '/media/test.png')
  } finally { Object.assign(globalThis, previous) }
})
