import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mergeRecent } from '../src/lib/recent.js'

const ev = (id, extra = {}) => ({ id, type_key: 'text', person_name: '某人', ...extra })

test('新记录插到最前面（不重新排序、不改已有顺序）', () => {
  const list = [ev(3), ev(2), ev(1)]
  const out = mergeRecent(list, ev(4, { title: '刚记的' }))
  assert.deepEqual(out.map((r) => r.id), [4, 3, 2, 1])
  assert.equal(out[0].title, '刚记的')
})

test('同 id 去重：回源与本地插入并存时不出现两行', () => {
  const out = mergeRecent([ev(5), ev(4)], ev(5, { title: '改了标题' }))
  assert.deepEqual(out.map((r) => r.id), [5, 4])
  assert.equal(out[0].title, '改了标题')
})

test('截断到 limit（默认 5，与「刚记的」拉取条数一致）', () => {
  const list = [ev(6), ev(5), ev(4), ev(3), ev(2)]
  const out = mergeRecent(list, ev(7))
  assert.equal(out.length, 5)
  assert.deepEqual(out.map((r) => r.id), [7, 6, 5, 4, 3])
  assert.equal(mergeRecent(list, ev(7), 2).length, 2)
})

test('没有可用的返回体时原样返回（列表不被清空）', () => {
  const list = [ev(2), ev(1)]
  assert.deepEqual(mergeRecent(list, null).map((r) => r.id), [2, 1])
  assert.deepEqual(mergeRecent(list, {}).map((r) => r.id), [2, 1])
  assert.deepEqual(mergeRecent(undefined, ev(9)).map((r) => r.id), [9])
})
