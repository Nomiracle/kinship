import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  scopeQuery,
  resolveScopedPerson,
  normalizePersonId,
  routeScopePersonId,
} from '../src/lib/scope.js'

test('「全部」不生成任何 query（显式 null，无 person 键）', () => {
  for (const v of [null, undefined, '', 0, 'all', 'abc', NaN, -3]) {
    const q = scopeQuery(v)
    assert.deepEqual(q, {}, `scopeQuery(${String(v)}) 应为空对象`)
    assert.ok(!('person' in q))
  }
})

test('具体人生成 ?person=<id>', () => {
  assert.deepEqual(scopeQuery(5), { person: 5 })
  assert.deepEqual(scopeQuery('7'), { person: 7 })
})

test('下游页 ?person 优先，其次全局；两者都不写回全局', () => {
  assert.equal(resolveScopedPerson('9', 3), 9) // URL 覆盖全局
  assert.equal(resolveScopedPerson(null, 3), 3) // 无覆盖 → 跟随全局
  assert.equal(resolveScopedPerson('', null), null)
  assert.equal(resolveScopedPerson(undefined, undefined), null)
  assert.equal(resolveScopedPerson(0, '12'), 12)
})

test('normalizePersonId 只接受正整数', () => {
  assert.equal(normalizePersonId('5'), 5)
  assert.equal(normalizePersonId(5), 5)
  assert.equal(normalizePersonId(-1), null)
  assert.equal(normalizePersonId(0), null)
  assert.equal(normalizePersonId(NaN), null)
  assert.equal(normalizePersonId(null), null)
})

test('normalizePersonId 拒绝小数（名称是正整数，就得拦小数）', () => {
  assert.equal(normalizePersonId(2.5), null)
  assert.equal(normalizePersonId('1.5'), null)
  assert.equal(normalizePersonId('3.0'), 3) // '3.0' → 整数 3，可接受
  assert.equal(normalizePersonId(Infinity), null)
  assert.equal(normalizePersonId(Number.MAX_SAFE_INTEGER + 1), null) // 超出安全整数范围
  // 小数不生成任何 query
  assert.deepEqual(scopeQuery(2.5), {})
})

test('routeScopePersonId：个人详情用路由参数，下游页用 ?person，其余 null', () => {
  assert.equal(routeScopePersonId({ name: 'person', params: { id: '9' } }), 9)
  assert.equal(routeScopePersonId({ name: 'person', params: { id: '9' }, query: { person: '3' } }), 9)
  assert.equal(routeScopePersonId({ name: 'timeline', query: { person: '7' } }), 7)
  assert.equal(routeScopePersonId({ name: 'timeline', query: { person: '2.5' } }), null)
  assert.equal(routeScopePersonId({ name: 'timeline', query: {} }), null)
  assert.equal(routeScopePersonId({ name: 'dashboard', meta: {} }), null)
  assert.equal(routeScopePersonId(null), null)
})
