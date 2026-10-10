import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildReminders,
  splitPeopleByAttention,
  needsAttention,
  triageTodos,
} from '../src/lib/dashboard.js'

test('纪念日与未来日子合并，并按 (人 + 标题) 去重', () => {
  const ann = [
    {
      id: 1,
      title: '在一起',
      person_id: 2,
      person_name: '阿明',
      days_since: 100,
      days_to_next: 5,
      next_date: '2026-10-15',
    },
  ]
  const up = [
    { kind: 'birthday', title: '阿明生日', person_id: 2, person_name: '阿明', days_left: 3, date: '2026-10-13' },
    { kind: 'anniversary', title: '在一起', person_id: 2, person_name: '阿明', days_left: 5, date: '2026-10-15' }, // 与纪念日重复 → 去掉
  ]
  const out = buildReminders(ann, up)
  assert.equal(out.length, 2)
  assert.deepEqual(out.map((r) => r.title), ['阿明生日', '在一起']) // 按 days_left 升序
  assert.equal(out[1].kind, 'anniversary')
  assert.equal(out[1].days_since, 100)
})

test('去重按人区分：不同人同标题不去重', () => {
  const out = buildReminders([], [
    { title: '生日', person_id: 1, person_name: 'A', days_left: 1 },
    { title: '生日', person_id: 2, person_name: 'B', days_left: 2 },
  ])
  assert.equal(out.length, 2)
})

test('未来日子之间也会去重（同一事实只出一条）', () => {
  const out = buildReminders([], [
    { kind: 'birthday', title: '阿明生日', person_id: 2, days_left: 1, date: '2026-10-11' },
    { kind: 'birthday', title: '阿明生日', person_id: 2, days_left: 1, date: '2026-10-11' },
  ])
  assert.equal(out.length, 1)
})

test('空输入返回空数组', () => {
  assert.deepEqual(buildReminders(), [])
  assert.deepEqual(buildReminders(null, null), [])
})

test('同名的「生日」与「纪念日」不再被误判成重复（key 带类别）', () => {
  // 后端真实 shape：anniversaries 没有 kind（隐含 anniversary），upcoming 自带 kind
  const ann = [{ title: '阿明生日', person_id: 2, person_name: '阿明', days_to_next: 4 }]
  const up = [
    { kind: 'birthday', title: '阿明生日', person_id: 2, person_name: '阿明', days_left: 2, date: '2026-10-12' },
  ]
  const out = buildReminders(ann, up)
  assert.equal(out.length, 2) // 一条是纪念日、一条是生日，不能合并掉
})

test('缺 person_id 的全局日子退回 person_name 去重', () => {
  const ann = [{ title: '结婚纪念日', person_id: null, person_name: null, days_to_next: 3 }]
  const up = [
    { kind: 'anniversary', title: '结婚纪念日', person_id: null, person_name: null, days_left: 3 },
  ]
  assert.equal(buildReminders(ann, up).length, 1)
})

test('person_id 字段整体缺失时也能按名字去重', () => {
  const ann = [{ title: '在一起', person_name: '阿明', days_to_next: 5 }]
  const up = [{ kind: 'anniversary', title: '在一起', person_name: '阿明', days_left: 5 }]
  assert.equal(buildReminders(ann, up).length, 1)
})

test('triageTodos：逾期 / 今天到期 / 近期 / 无期，且排除已完成', () => {
  const todos = [
    { id: 1, title: 'A', due_date: '2026-10-08' },
    { id: 2, title: 'B', due_date: '2026-10-10' },
    { id: 3, title: 'C', due_date: '2026-10-12' },
    { id: 4, title: 'D', due_date: '2026-11-01' }, // 超出 7 天窗口
    { id: 5, title: 'E', due_date: null },
    { id: 6, title: 'F', due_date: '2026-10-09', done: true }, // 已完成 → 排除
  ]
  const { overdue, due, soon, undated } = triageTodos(todos, '2026-10-10')
  assert.deepEqual(overdue.map((t) => t.id), [1])
  assert.deepEqual(due.map((t) => t.id), [2])
  assert.deepEqual(soon.map((t) => t.id), [3])
  assert.deepEqual(undated.map((t) => t.id), [4, 5])
})

test('triageTodos 空输入不崩', () => {
  const b = triageTodos(undefined, '2026-10-10')
  assert.deepEqual(b.overdue, [])
  assert.deepEqual(b.due, [])
})

test('需要留意：久未联系 / 生理期窗口 / 有代办 / 生日临近', () => {
  assert.equal(needsAttention({ no_contact: true }), true)
  assert.equal(needsAttention({ cycle: { in_window: true } }), true)
  assert.equal(needsAttention({ open_todos: 2 }), true)
  assert.equal(needsAttention({ birthday_days_left: 3 }), true)
  assert.equal(needsAttention({ birthday_days_left: 30 }), false)
  assert.equal(needsAttention({}), false)
  assert.equal(needsAttention(null), false)
})

test('需要留意的人排前面，其余折叠；按紧急度排序', () => {
  const persons = [
    { id: 1, display_name: '闲人' },
    { id: 2, display_name: '生日近', birthday_days_left: 2 },
    { id: 3, display_name: '窗口', cycle: { in_window: true } },
    { id: 4, display_name: '久未联系', no_contact: true },
  ]
  const { attention, others } = splitPeopleByAttention(persons)
  assert.deepEqual(attention.map((p) => p.id), [3, 4, 2]) // 窗口(0) < 久未联系(1) < 生日(2)
  assert.deepEqual(others.map((p) => p.id), [1])
})
