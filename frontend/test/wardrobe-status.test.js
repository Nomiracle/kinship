import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  ON_HAND_STATUSES,
  STATUS_LABELS,
  STATUS_OPTIONS,
  buildStatusPatch,
  filterByStatusScope,
  formatAdded,
  isOnHand,
  replaceCandidates,
  requiresReason,
  statusLabel,
  validateStatusChange,
} from '../src/lib/status.js'

test('状态值域与后端一一对应（7 个，标签齐全）', () => {
  assert.deepEqual(
    STATUS_OPTIONS.map((o) => o.key),
    ['in_use', 'idle', 'sold', 'gifted', 'lost', 'damaged', 'discarded']
  )
  assert.equal(STATUS_LABELS.sold, '已卖出')
  assert.deepEqual(ON_HAND_STATUSES, ['in_use', 'idle'])
})

test('statusLabel：优先服务端 status_label，其次本地映射', () => {
  assert.equal(statusLabel({ status: 'sold' }), '已卖出')
  assert.equal(statusLabel({ status: 'lost', status_label: '丢了（自定义）' }), '丢了（自定义）')
  assert.equal(statusLabel(null), '')
})

test('isOnHand：在役/闲置算在手；已离手与已合并都不算', () => {
  assert.equal(isOnHand({ status: 'in_use' }), true)
  assert.equal(isOnHand({ status: 'idle' }), true)
  assert.equal(isOnHand({ status: 'sold' }), false)
  assert.equal(isOnHand({ status: 'in_use', merged_into_id: 7 }), false)
})

test('filterByStatusScope：hand / in_use / idle / offhand / all', () => {
  const items = [
    { id: 1, status: 'in_use' },
    { id: 2, status: 'idle' },
    { id: 3, status: 'sold' },
  ]
  assert.deepEqual(filterByStatusScope(items, 'hand').map((i) => i.id), [1, 2])
  assert.deepEqual(filterByStatusScope(items, 'in_use').map((i) => i.id), [1])
  assert.deepEqual(filterByStatusScope(items, 'idle').map((i) => i.id), [2])
  assert.deepEqual(filterByStatusScope(items, 'offhand').map((i) => i.id), [3])
  assert.deepEqual(filterByStatusScope(items, 'all').map((i) => i.id), [1, 2, 3])
  // 未知 scope 不应把列表清空（默认当 all 更安全）
  assert.deepEqual(filterByStatusScope(items, '').map((i) => i.id), [1, 2, 3])
})

test('requiresReason：只有离手状态必填原因', () => {
  assert.equal(requiresReason('sold'), true)
  assert.equal(requiresReason('gifted'), true)
  assert.equal(requiresReason('in_use'), false)
  assert.equal(requiresReason('idle'), false)
})

test('validateStatusChange：离手不写原因要拦；在手可空', () => {
  assert.match(validateStatusChange({ status: 'sold', reason: '  ' }), /需要写一句原因/)
  assert.equal(validateStatusChange({ status: 'sold', reason: '闲鱼卖了' }), '')
  assert.equal(validateStatusChange({ status: 'in_use', reason: '' }), '')
  assert.match(validateStatusChange({ status: 'nope' }), /未知状态/)
  assert.match(validateStatusChange({ status: 'sold', reason: 'x'.repeat(256) }), /255/)
})

test('buildStatusPatch：空原因/空日期不传（不会把已有原因清空）', () => {
  assert.deepEqual(buildStatusPatch({ status: 'sold', reason: '  ', date: '' }), { status: 'sold' })
  assert.deepEqual(
    buildStatusPatch({ status: 'sold', reason: ' 换新 ', date: '2026-10-26' }),
    { status: 'sold', status_reason: '换新', status_changed_on: '2026-10-26' }
  )
})

test('formatAdded：优先 added_at（本地墙钟），没有再退回 added_on', () => {
  assert.equal(formatAdded({ added_at: '2026-10-19 18:44' }), '2026-10-19 18:44')
  assert.equal(formatAdded({ added_on: '2026-10-19' }), '2026-10-19')
  assert.equal(formatAdded({}), '')
})

test('replaceCandidates：同人不含自己、排除已合并', () => {
  const items = [
    { id: 1, person_id: 9 },
    { id: 2, person_id: 9, merged_into_id: 1 },
    { id: 3, person_id: 8 },
  ]
  assert.deepEqual(replaceCandidates(items, 1).map((i) => i.id), [3])
})
