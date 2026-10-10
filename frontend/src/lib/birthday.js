// 生日的显示口径（★ 统一在这儿，别各页面自己拼）
//
// 为什么要有这个文件：页面上只显示「还有 N 天」时，用户会把别的倒计时
// （生理期预测的「约 24 天后」等）误读成生日。所以任何展示生日的地方都必须
// **先给明确写法**（公历日期 / 农历月日），再给倒计时 + 满几岁。
//
// 数据来自后端 PersonOut.birthday_text / birthday_next / birthday_days_left / age_next
// （今天卡片、人物列表、个人页都带这几个字段；前端算不了农历）。

export function md(iso) {
  // '2026-11-07' → '11-07'
  return iso ? String(iso).slice(5) : ''
}

/** 生日的完整一行：'生日 农历九月廿九（11-07）· 28 天后 · 满 27 岁'；没生日返回 '' */
export function birthdayLine(p, opts = {}) {
  if (!p || !p.birthday_text) return ''
  const withAge = opts.withAge !== false
  const text = p.birthday_lunar ? `${p.birthday_text}（${md(p.birthday_next)}）` : p.birthday_text
  const d = p.birthday_days_left
  const when = d === 0 ? '就是今天' : d === null || d === undefined ? '' : `${d} 天后`
  const age = withAge && p.age_next ? `满 ${p.age_next} 岁` : ''
  return `生日 ${text}${when ? ' · ' + when : ''}${age ? ' · ' + age : ''}`
}

/** 生日临近（默认 30 天内）—— 列表里用来高亮 */
export function birthdaySoon(p, withinDays = 30) {
  const d = p && p.birthday_days_left
  return d !== null && d !== undefined && d <= withinDays
}
