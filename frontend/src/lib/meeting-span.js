// 跨日相处的日期跨度计算（只做纯函数，UI 与 payload 共用一套口径）
//
// 语义约定（与后端 routers/records.py 的 _meeting_row 一致）：
//   · endedOn 为空 或 不晚于开始日  → 单日（spans=false，落库 ended_on=NULL）
//   · endedOn 晚于开始日            → 跨日（跨了夜就必然过夜，hours 不再手填）
// ★ 日期一律按 UTC 零点算差值，避免夏令时/时区把 1 天算成 0.9583 天。

const DAY_MS = 86400000

export function parseDay(value) {
  const s = String(value || '').slice(0, 10)
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (!m) return null
  const t = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isFinite(t) ? t : null
}

export function addDays(day, n) {
  const t = parseDay(day)
  if (t == null) return ''
  return new Date(t + Number(n || 0) * DAY_MS).toISOString().slice(0, 10)
}

export function spanInfo(start, end) {
  const a = parseDay(start)
  const b = parseDay(end)
  if (a == null || b == null || b <= a) return { spans: false, days: 1, nights: 0, text: '' }
  const nights = Math.round((b - a) / DAY_MS)
  return { spans: true, days: nights + 1, nights, text: `${nights + 1} 天 ${nights} 晚` }
}

// 送后端的 ended_on：单日/非法/同日 → null（后端也只认「严格晚于开始日」）
export function normalizeEndedOn(start, end) {
  return spanInfo(start, end).spans ? String(end).slice(0, 10) : null
}

// 表单校验文案：空串 = 可提交
export function spanError(start, end) {
  if (!end) return ''
  const a = parseDay(start)
  const b = parseDay(end)
  if (b == null) return '结束日期格式不对'
  if (a == null) return '先填开始日期'
  if (b < a) return '结束日期不能早于开始日期'
  if (Math.round((b - a) / DAY_MS) > 365) return '跨度不能超过 365 天'
  return ''
}

// 列表卡片上的跨度标签：'08/20–08/22 · 3 天 2 晚'（单日返回空串，不占位置）
export function spanLabel(event) {
  const m = event && event.meeting
  if (!m || !m.ended_on) return ''
  const days = Number(m.span_days || 0)
  const nights = Number(m.span_nights || 0)
  if (nights < 1) return ''
  const short = (v) => String(v || '').slice(5).replace('-', '/')
  return `${short(event.event_date)}–${short(m.ended_on)} · ${days} 天 ${nights} 晚`
}
