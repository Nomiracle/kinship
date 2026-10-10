import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  TABS,
  GROUP_SEGMENTS,
  activeTabKey,
  segmentsForRoute,
  activeSegmentKey,
} from '../src/lib/nav.js'

test('底部恰好 4 个主 tab，顺序为 今天 / 时间轴 / 人物 / 待办', () => {
  assert.deepEqual(TABS.map((t) => t.key), ['today', 'timeline', 'people', 'todos'])
  assert.deepEqual(TABS.map((t) => t.label), ['今天', '时间轴', '人物', '待办'])
  assert.deepEqual(TABS.map((t) => t.to), ['/', '/timeline', '/people', '/todos'])
})

test('每个主 tab 都带图标名（图标 + 文字标签，非纯文字）', () => {
  for (const t of TABS) {
    assert.equal(typeof t.icon, 'string', `${t.key} 应有 icon`)
    assert.ok(t.icon.length > 0, `${t.key} 的 icon 不能为空`)
  }
})

test('子页继承父 tab（父导航高亮准确）', () => {
  assert.equal(activeTabKey({ name: 'person', meta: { tab: 'people' } }), 'people')
  assert.equal(activeTabKey({ name: 'cycle', meta: {} }), null)
  assert.equal(activeTabKey({ name: 'gallery', meta: { tab: 'timeline' } }), 'timeline')
  assert.equal(activeTabKey({ name: 'wardrobe', meta: { tab: 'timeline' } }), 'timeline')
  // 删除/新增页不属于任何 tab
  assert.equal(activeTabKey({ name: 'settings', meta: {} }), null)
  assert.equal(activeTabKey({ name: 'new', meta: {} }), null)
})

test('时间轴分组含 记录 / 相册 / 衣橱，且复用既有路由', () => {
  const segs = segmentsForRoute({ meta: { group: 'timeline' } })
  assert.deepEqual(segs.map((s) => s.to), ['/timeline', '/gallery', '/wardrobe'])
  assert.deepEqual(segs.map((s) => s.key), ['records', 'gallery', 'wardrobe'])
  assert.equal(segmentsForRoute({ meta: {} }), null)
  assert.equal(segmentsForRoute({}), null)
})

test('人物分组含 人物 / 关系，关系链接既有 /relations', () => {
  const segs = segmentsForRoute({ meta: { group: 'people' } })
  assert.deepEqual(segs.map((s) => s.to), ['/people', '/relations'])
})

test('二级分段高亮映射准确', () => {
  assert.equal(activeSegmentKey({ name: 'timeline' }), 'records')
  assert.equal(activeSegmentKey({ name: 'gallery' }), 'gallery')
  assert.equal(activeSegmentKey({ name: 'wardrobe' }), 'wardrobe')
  assert.equal(activeSegmentKey({ name: 'people' }), 'people')
  assert.equal(activeSegmentKey({ name: 'relations' }), 'relations')
  assert.equal(activeSegmentKey({ name: 'search' }), null)
})

test('GROUP_SEGMENTS 只包含既有 URL（无新增页面）', () => {
  const allowed = new Set(['/timeline', '/gallery', '/wardrobe', '/people', '/relations'])
  for (const segs of Object.values(GROUP_SEGMENTS)) {
    for (const s of segs) assert.ok(allowed.has(s.to), `未知分段路由 ${s.to}`)
  }
})
