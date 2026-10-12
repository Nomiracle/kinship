import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  dayHeadline,
  dayOf,
  dayThumbs,
  fmtTime,
  fmtWhen,
  groupByDay,
  hasTime,
  normalizeTime,
  nowLocalTime,
  splitLocal,
  timeOf,
  toLocalInput,
  typeSummary,
  weekdayOf,
} from '../src/lib/event-day.js'

// ------------------------------------------------------------ 时刻：00:00 不是时刻

test('timeOf/hasTime：null 与 00:00:00 都算「只记到日」', () => {
  assert.equal(timeOf({ event_time: null }), '')
  assert.equal(timeOf({ event_time: '' }), '')
  assert.equal(timeOf({ event_time: '00:00:00' }), '', '00:00:00 是「没有时刻」，不是凌晨 0 点')
  assert.equal(timeOf({ event_time: '14:03:21' }), '14:03:21')
  assert.equal(hasTime({ event_time: '00:00:00' }), false)
  assert.equal(hasTime({ event_time: '07:00:00' }), true)
  assert.equal(hasTime(undefined), false)
})

test('fmtTime 只到分；fmtWhen 有时刻才带时间', () => {
  assert.equal(fmtTime({ event_time: '14:03:21' }), '14:03')
  assert.equal(fmtTime({ event_time: null }), '')
  assert.equal(fmtWhen({ event_date: '2026-10-12', event_time: '14:03:21' }), '2026-10-12 14:03')
  assert.equal(fmtWhen({ event_date: '2026-10-12', event_time: null }), '2026-10-12')
  assert.equal(fmtWhen({ event_at: '2026-10-12T14:03:21' }), '', 'event_at 不是本模块的口径')
})

test('dayOf 兼容日期串与 ISO 时刻串', () => {
  assert.equal(dayOf('2026-10-12'), '2026-10-12')
  assert.equal(dayOf('2026-10-12T14:03:21'), '2026-10-12')
  assert.equal(dayOf(''), '')
  assert.equal(dayOf(null), '')
})

test('weekdayOf：2026-10-12 是周一', () => {
  assert.equal(weekdayOf('2026-10-12'), '周一')
  assert.equal(weekdayOf('2026-10-11'), '周日')
  assert.equal(weekdayOf(''), '')
  assert.equal(weekdayOf('不是日期'), '')
})

// ------------------------------------------------------------ datetime-local 来回转换

test('toLocalInput / splitLocal 往返：没有时刻就只给日期', () => {
  assert.equal(toLocalInput('2026-10-12', '14:03:21'), '2026-10-12T14:03:21')
  assert.equal(toLocalInput('2026-10-12', ''), '2026-10-12')
  assert.deepEqual(splitLocal('2026-10-12T14:03:21'), { date: '2026-10-12', time: '14:03:21' })
  assert.deepEqual(splitLocal('2026-10-12'), { date: '2026-10-12', time: '' })
  assert.deepEqual(splitLocal(''), { date: '', time: '' })
  // 秒段截断到 8 位（datetime-local 可能带毫秒）
  assert.deepEqual(splitLocal('2026-10-12T14:03:21.123'), { date: '2026-10-12', time: '14:03:21' })
})

test('normalizeTime：空 → null（= 只记到日）；补秒', () => {
  assert.equal(normalizeTime(''), null)
  assert.equal(normalizeTime(null), null)
  assert.equal(normalizeTime(undefined), null)
  assert.equal(normalizeTime('14:03'), '14:03:00')
  assert.equal(normalizeTime('14:03:07'), '14:03:07')
  assert.equal(normalizeTime('9:05'), '09:05:00')
  assert.equal(normalizeTime('乱写'), null)
})

test('nowLocalTime 形如 HH:MM:SS', () => {
  assert.match(nowLocalTime(new Date(2026, 9, 12, 8, 5, 7)), /^08:05:07$/)
  assert.match(nowLocalTime(), /^\d{2}:\d{2}:\d{2}$/)
})

// ------------------------------------------------------------ 按日分组

const ev = (id, day, time, type_key = 'text', extra = {}) => ({
  id,
  event_date: day,
  event_time: time,
  type_key,
  title: 'T' + id,
  ...extra,
})

test('groupByDay：保持后端顺序，一天一组，统计条数与类型', () => {
  const days = groupByDay([
    ev(1, '2026-10-12', '14:03:21'),
    ev(2, '2026-10-12', null, 'outfit'),
    ev(3, '2026-10-08', '09:15:00', 'text'),
  ])
  assert.deepEqual(days.map((d) => d.date), ['2026-10-12', '2026-10-08'])
  assert.deepEqual(days.map((d) => d.count), [2, 1])
  assert.deepEqual(days[0].type_keys, ['text', 'outfit'])
  assert.equal(days[0].weekday, '周一')
  assert.deepEqual(days[0].items.map((i) => i.id), [1, 2], '组内顺序沿用后端给的顺序')
  assert.deepEqual(groupByDay(undefined), [])
})

test('typeSummary：按 labelOf 翻译，未知类型退化成 key', () => {
  const days = groupByDay([
    ev(1, '2026-10-12', '14:03:21', 'text'),
    ev(2, '2026-10-12', null, 'text'),
    ev(3, '2026-10-12', null, 'outfit'),
  ])
  const labels = { text: '文字', outfit: '服装' }
  assert.equal(typeSummary(days[0], (k) => labels[k] || k), '文字 2 · 服装 1')
  assert.equal(typeSummary({ items: [{ type_key: 'mood' }] }), 'mood 1')
  assert.equal(typeSummary(null), '')
})

test('dayThumbs：只收图片、最多 limit 张；dayHeadline 取第一条标题', () => {
  const day = groupByDay([
    ev(1, '2026-10-12', '14:03:21', 'text', {
      media: [{ id: 1, kind: 'video', path: 'v.mp4' }, { id: 2, kind: 'image', path: 'a.jpg' }],
    }),
    ev(2, '2026-10-12', null, 'text', { media: [{ id: 3, kind: 'image', path: 'b.jpg' }] }),
  ])[0]
  assert.deepEqual(dayThumbs(day).map((m) => m.id), [2, 3])
  assert.deepEqual(dayThumbs(day, 1).map((m) => m.id), [2])
  assert.equal(dayHeadline(day), 'T1')
  assert.equal(dayHeadline({ items: [{ body: '正文开头很长很长' }] }), '正文开头很长很长')
  assert.equal(dayHeadline({ items: [{ body: '正文开头'.repeat(10) }] }).length, 20, '截到 20 字')
})
