import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  availableEventTypes,
  reconcileEventType,
  moduleState,
  anyOutfitEnabled,
} from '../src/lib/modules.js'

// 与 /api/config 的 event_types 结构一致（module 为空表示任何时候都能记）
const TYPES = [
  { key: 'text' },
  { key: 'mood' },
  { key: 'milestone' },
  { key: 'hobby' },
  { key: 'social' },
  { key: 'outfit', module: 'outfit' },
  { key: 'period', module: 'cycle' },
  { key: 'meeting', module: 'interaction' },
  { key: 'gift', module: 'gift' },
  { key: 'health', module: 'health' },
  { key: 'contact', module: 'contact' },
]

test('没绑 module 的类型在任何模块组合下都可用', () => {
  const keys = availableEventTypes(TYPES, []).map((t) => t.key)
  for (const k of ['text', 'mood', 'milestone', 'hobby', 'social']) {
    assert.ok(keys.includes(k), `${k} 应始终可用`)
  }
})

test('绑 module 的类型严格跟随开关（模块门控无回归）', () => {
  const keys = availableEventTypes(TYPES, ['cycle', 'outfit']).map((t) => t.key)
  assert.ok(keys.includes('period'))
  assert.ok(keys.includes('outfit'))
  assert.ok(!keys.includes('meeting'))
  assert.ok(!keys.includes('gift'))
  assert.ok(!keys.includes('health'))
  assert.ok(!keys.includes('contact'))
})

test('切人后失效类型回退到 text，有效则保留', () => {
  const none = availableEventTypes(TYPES, [])
  assert.equal(reconcileEventType('period', none), 'text')
  assert.equal(reconcileEventType('text', none), 'text')
  const withCycle = availableEventTypes(TYPES, ['cycle'])
  assert.equal(reconcileEventType('period', withCycle), 'period')
})

test('空/缺失配置不崩', () => {
  assert.deepEqual(availableEventTypes(undefined, undefined), [])
  assert.deepEqual(availableEventTypes([], undefined), [])
})

test('moduleState 三态：已启用 true / 未启用 false / 未知 null', () => {
  assert.equal(moduleState(['outfit', 'cycle'], 'outfit'), true)
  assert.equal(moduleState(['cycle'], 'outfit'), false)
  assert.equal(moduleState(undefined, 'outfit'), null) // 加载中/失败
  assert.equal(moduleState(null, 'outfit'), null)
})

test('衣橱入口门控：全部 scope 下任意一人开了服装就显示', () => {
  assert.equal(anyOutfitEnabled([false, true, false]), true)
  assert.equal(anyOutfitEnabled([false, false]), false)
  assert.equal(anyOutfitEnabled([]), false)
  assert.equal(anyOutfitEnabled(undefined), false)
})

test('衣橱入口门控：加载中/失败（未知）不隐藏，legacy 路由仍可达', () => {
  assert.equal(anyOutfitEnabled([null]), true)
  assert.equal(anyOutfitEnabled([false, null]), true)
  assert.equal(anyOutfitEnabled([undefined]), true)
})
