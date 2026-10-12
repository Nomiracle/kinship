// 事件时刻（精确到秒）与「按日分组」的纯逻辑 —— 时间轴 / 个人页 / 记录页共用。
//
// ★ 后端约定（见 backend/schemas.py）：
//   event_date = 'YYYY-MM-DD'（日期部分），event_time = 'HH:MM:SS' 或 null。
//   event_time 为 null 表示「只记到日」—— 界面不显示时间，也不假装是凌晨 00:00。
//   列表顺序由后端排好（日期倒序；同一天内有时刻的在前、无时刻的落当天末尾）。

export const WEEK_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export function dayOf(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

// 这条记录有没有「时刻」（null / 空串 / 00:00:00 都不算）
export function hasTime(e) {
  return !!timeOf(e)
}

export function timeOf(e) {
  const t = e && e.event_time
  if (!t) return ''
  const s = String(t)
  return s === '00:00:00' ? '' : s
}

// 列表里显示的时刻：'14:03'（秒在编辑面板里才看得到）
export function fmtTime(e) {
  return timeOf(e).slice(0, 5)
}

// '2026-10-12' 或 '2026-10-12 14:03'
export function fmtWhen(e) {
  if (!e) return ''
  const d = dayOf(e.event_date)
  const t = fmtTime(e)
  return t ? `${d} ${t}` : d
}

export function weekdayOf(dateStr) {
  const d = dayOf(dateStr)
  if (!d) return ''
  const dt = new Date(d + 'T00:00:00')
  return Number.isNaN(dt.getTime()) ? '' : WEEK_CN[dt.getDay()]
}

// 本地日期串 'YYYY-MM-DD'（不用 toISOString：那是 UTC，跨零点会差一天）
export function todayStr(now = new Date()) {
  return now.toLocaleDateString('sv-SE')
}

// 本地时刻 'HH:MM:SS'
export function nowLocalTime(now = new Date()) {
  const p = (n) => String(n).padStart(2, '0')
  return `${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`
}

// → <input type="datetime-local" step="1"> 的值；没有时刻就只给日期
export function toLocalInput(dateStr, timeStr) {
  const d = dayOf(dateStr)
  if (!d) return ''
  const t = String(timeStr || '').trim()
  return t ? `${d}T${t.slice(0, 8)}` : d
}

// ← 拆开 datetime-local 的值：{ date, time }（time 空 = 只记到日）
export function splitLocal(value) {
  const s = String(value || '').trim()
  if (!s) return { date: '', time: '' }
  const [date, rest] = s.split('T')
  return { date: dayOf(date), time: (rest || '').slice(0, 8) }
}

// 提交给后端的 event_time：空 → null；'14:03' → '14:03:00'
export function normalizeTime(timeStr) {
  const t = String(timeStr === undefined || timeStr === null ? '' : timeStr).trim()
  if (!t) return null
  const parts = t.split(':')
  if (parts.length < 2) return null
  while (parts.length < 3) parts.push('00')
  return parts.slice(0, 3).map((p) => String(p).padStart(2, '0')).join(':')
}

/**
 * 按日分组（顺序沿用后端给的顺序，不再重排）。
 * 返回 [{ date, weekday, count, items, type_keys: [...] }]
 */
export function groupByDay(items) {
  const days = []
  const seen = new Map()
  for (const e of items || []) {
    const key = dayOf(e.event_date)
    let day = seen.get(key)
    if (!day) {
      day = { date: key, weekday: weekdayOf(key), count: 0, items: [], type_keys: [] }
      seen.set(key, day)
      days.push(day)
    }
    day.items.push(e)
    day.count += 1
    if (e.type_key && !day.type_keys.includes(e.type_key)) day.type_keys.push(e.type_key)
  }
  return days
}

// 日头摘要：「穿搭 1 · 文字 2」（labelOf 负责把 type_key 翻成人话）
export function typeSummary(day, labelOf = (k) => k) {
  const counts = new Map()
  for (const e of day && day.items ? day.items : []) {
    counts.set(e.type_key, (counts.get(e.type_key) || 0) + 1)
  }
  return [...counts.entries()].map(([k, n]) => `${labelOf(k)} ${n}`).join(' · ')
}

// 日头缩略图：那天的前几张小图（折叠时也能一眼看出发生了什么）
export function dayThumbs(day, limit = 2) {
  const out = []
  for (const e of day && day.items ? day.items : []) {
    for (const m of e.media || []) {
      if (m && m.kind !== 'video') out.push(m)
      if (out.length >= limit) return out
    }
  }
  return out
}

// 折叠时的摘要行：第一条的标题（或正文开头）
export function dayHeadline(day) {
  const first = day && day.items && day.items[0]
  if (!first) return ''
  return first.title || (first.body || '').slice(0, 20) || ''
}
