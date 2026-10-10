import { test } from 'node:test'
import assert from 'node:assert/strict'
import { birthdayLine, birthdaySoon, md } from '../src/lib/birthday.js'

// 背景：首页人物行曾只显示「约 24 天后」（生理期预测），而同一个人的生日在 28 天后 ——
// 只有天数没有日期就会被误读。这几条断言把「必须给明确写法」钉住。

test('公历生日：日期 + 还有几天 + 满几岁', () => {
  const p = {
    birthday_text: '1972-10-01',
    birthday_lunar: false,
    birthday_next: '2027-10-01',
    birthday_days_left: 356,
    age_next: 55,
  }
  assert.equal(birthdayLine(p), '生日 1972-10-01 · 356 天后 · 满 55 岁')
})

test('农历生日：补上今年对应的公历日期（否则不知道是哪天）', () => {
  const p = {
    birthday_text: '农历九月廿九',
    birthday_lunar: true,
    birthday_next: '2026-11-07',
    birthday_days_left: 28,
    age_next: 27,
  }
  assert.equal(birthdayLine(p), '生日 农历九月廿九（11-07） · 28 天后 · 满 27 岁')
})

test('就是今天：说「就是今天」而不是「0 天后」', () => {
  const p = {
    birthday_text: '1990-01-01',
    birthday_lunar: false,
    birthday_next: '2027-01-01',
    birthday_days_left: 0,
    age_next: 37,
  }
  assert.equal(birthdayLine(p), '生日 1990-01-01 · 就是今天 · 满 37 岁')
})

test('没有生日：返回空串（调用方据此不渲染这一行）', () => {
  assert.equal(birthdayLine({}), '')
  assert.equal(birthdayLine(null), '')
  assert.equal(birthdayLine({ birthday: '1990-01-01' }), '') // 后端没给派生字段就不硬编
})

test('withAge:false 时不提年龄（列表里更紧凑）', () => {
  const p = {
    birthday_text: '2007-03-22',
    birthday_lunar: false,
    birthday_next: '2027-03-22',
    birthday_days_left: 163,
    age_next: 20,
  }
  assert.equal(birthdayLine(p, { withAge: false }), '生日 2007-03-22 · 163 天后')
})

test('生日临近判定：30 天内为真，未知/更远为假', () => {
  assert.equal(birthdaySoon({ birthday_days_left: 28 }), true)
  assert.equal(birthdaySoon({ birthday_days_left: 30 }), true)
  assert.equal(birthdaySoon({ birthday_days_left: 31 }), false)
  assert.equal(birthdaySoon({ birthday_days_left: null }), false)
  assert.equal(birthdaySoon({}), false)
})

test('md() 取月日，空值不炸', () => {
  assert.equal(md('2026-11-07'), '11-07')
  assert.equal(md(null), '')
})
