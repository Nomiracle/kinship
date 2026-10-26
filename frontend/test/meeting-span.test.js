import { test } from 'node:test'
import assert from 'node:assert/strict'
import { addDays, normalizeEndedOn, spanError, spanInfo, spanLabel } from '../src/lib/meeting-span.js'

test('addDays: crosses month/year without timezone drift', () => {
  assert.equal(addDays('2026-08-31', 1), '2026-09-01')
  assert.equal(addDays('2026-12-31', 1), '2027-01-01')
  assert.equal(addDays('2026-03-01', -1), '2026-02-28')
  assert.equal(addDays('', 1), '')
  assert.equal(addDays('not-a-date', 1), '')
})

test('spanInfo: single day has no span, multi-day gives days+1 and nights', () => {
  assert.deepEqual(spanInfo('2026-08-20', ''), { spans: false, days: 1, nights: 0, text: '' })
  assert.deepEqual(spanInfo('2026-08-20', '2026-08-20'), { spans: false, days: 1, nights: 0, text: '' })
  const oneNight = spanInfo('2026-08-20', '2026-08-21')
  assert.equal(oneNight.spans, true)
  assert.equal(oneNight.days, 2)
  assert.equal(oneNight.nights, 1)
  assert.equal(oneNight.text, '2 天 1 晚')
  const weekend = spanInfo('2026-08-21', '2026-08-23')
  assert.equal(weekend.days, 3)
  assert.equal(weekend.nights, 2)
})

test('spanInfo: backwards range is not a span (never a negative duration)', () => {
  assert.equal(spanInfo('2026-08-20', '2026-08-19').spans, false)
})

test('normalizeEndedOn: only a strictly later day is sent to the API', () => {
  assert.equal(normalizeEndedOn('2026-08-20', ''), null)
  assert.equal(normalizeEndedOn('2026-08-20', '2026-08-20'), null)
  assert.equal(normalizeEndedOn('2026-08-20', '2026-08-19'), null)
  assert.equal(normalizeEndedOn('2026-08-20', '2026-08-22'), '2026-08-22')
})

test('spanError: messages block submission instead of silently fixing input', () => {
  assert.equal(spanError('2026-08-20', ''), '')
  assert.equal(spanError('2026-08-20', '2026-08-22'), '')
  assert.match(spanError('2026-08-20', '2026-08-19'), /不能早于/)
  assert.match(spanError('2026-08-20', '2027-09-01'), /365/)
  assert.match(spanError('', '2026-08-20'), /开始日期/)
})

test('spanLabel: card label only for real spans, single day stays quiet', () => {
  const spanned = { event_date: '2026-08-20', meeting: { ended_on: '2026-08-22', span_days: 3, span_nights: 2 } }
  assert.equal(spanLabel(spanned), '08/20–08/22 · 3 天 2 晚')
  assert.equal(spanLabel({ event_date: '2026-08-20', meeting: null }), '')
  assert.equal(spanLabel({ event_date: '2026-08-20', meeting: { ended_on: null, span_days: 1, span_nights: 0 } }), '')
  assert.equal(spanLabel(null), '')
})
