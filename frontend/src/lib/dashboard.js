// 首页（今天）的纯聚合逻辑，便于单测。
//
//  - buildReminders：合并「纪念日」与「未来 N 天」，按 (人 + 类别 + 标题) 去重，
//    避免同一条事实出现两次（生日/纪念日重复提醒），同时避免把「同名的生日」和
//    「同名的纪念日」当成一条而误删。
//  - triageTodos：把待办按到期情况分成 逾期 / 今天到期 / 近期 三类，供首页给
//    「可操作的待办」而不只是一个数字。
//  - splitPeopleByAttention / needsAttention：把「需要留意的人」排到前面，其余折叠。

// 后端 insight.py 的两种来源 shape：
//   anniversaries：{title, person_id, person_name, ...}（person_id 可能为 null）
//   upcoming：     {kind, title, person_id, person_name, date, days_left, ...}
// person_id 可能缺失/为 null（全局纪念日）→ 退回 person_name；再没有就用空串。
function personKey(o) {
  if (o && o.person_id !== undefined && o.person_id !== null) return 'p' + o.person_id
  return 'n' + ((o && o.person_name) || '')
}

// 类别：anniversaries 来源没有 kind 字段，用它的隐含类别补上；upcoming 用自带的
// kind（生日 birthday / 纪念日 anniversary / 其它 sd.kind）。
function kindOf(o, fallback) {
  const k = o && o.kind
  return k ? String(k) : fallback
}

function reminderKey(o, fallbackKind) {
  const title = String((o && o.title) || '').trim()
  return personKey(o) + '::' + kindOf(o, fallbackKind) + '::' + title
}

export function buildReminders(anniversaries = [], upcoming = []) {
  const out = []
  const seen = new Set()
  for (const a of anniversaries || []) {
    const key = reminderKey(a, 'anniversary')
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      kind: 'anniversary',
      title: a.title,
      person_name: a.person_name,
      person_id: a.person_id ?? null,
      days_since: a.days_since ?? null,
      days_to_next: a.days_to_next ?? null,
      days_left: a.days_to_next ?? null,
      date: a.next_date || null,
      lunar: !!a.lunar,
    })
  }
  for (const u of upcoming || []) {
    const key = reminderKey(u, u.kind || 'upcoming')
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      kind: u.kind || 'upcoming',
      title: u.title,
      person_name: u.person_name,
      person_id: u.person_id ?? null,
      days_since: null,
      days_to_next: null,
      days_left: u.days_left ?? null,
      date: u.date || null,
      lunar: !!u.lunar,
    })
  }
  out.sort((a, b) => {
    const av = a.days_left === null || a.days_left === undefined ? 1e9 : a.days_left
    const bv = b.days_left === null || b.days_left === undefined ? 1e9 : b.days_left
    if (av !== bv) return av - bv
    return String(a.title || '').localeCompare(String(b.title || ''))
  })
  return out
}

// 需要留意的人：久未联系 / 生理期窗口内 / 有待办 / 生日临近（≤ withinDays 天）
export function needsAttention(p, withinDays = 7) {
  if (!p) return false
  if (p.cycle && p.cycle.in_window) return true
  if (p.no_contact) return true
  if ((p.open_todos || 0) > 0) return true
  const bl = p.birthday_days_left
  if (bl !== undefined && bl !== null && bl <= withinDays) return true
  return false
}

// 紧急度越小越靠前
export function attentionRank(p) {
  if (!p) return 99
  if (p.cycle && p.cycle.in_window) return 0
  if (p.no_contact) return 1
  const bl = p.birthday_days_left
  if (bl !== undefined && bl !== null && bl <= 7) return 2
  if ((p.open_todos || 0) > 0) return 3
  return 9
}

// 拆成「需要留意」与「其他人」；需要留意按紧急度排序
export function splitPeopleByAttention(persons = [], withinDays = 7) {
  const attention = []
  const others = []
  for (const p of persons || []) {
    if (needsAttention(p, withinDays)) attention.push(p)
    else others.push(p)
  }
  attention.sort((a, b) => attentionRank(a) - attentionRank(b))
  return { attention, others }
}

// ---- 待办分诊：把「未完成待办」按到期情况排成可操作的三组 ----
// today 传 'YYYY-MM-DD'（本地日）；ISO 日期字符串可直接字典序比较。
export function triageTodos(todos = [], today = '', withinDays = 7) {
  const horizon = addDays(today, withinDays)
  const overdue = []
  const due = []
  const soon = []
  const undated = []
  for (const t of todos || []) {
    if (!t || t.done) continue
    const d = t.due_date || ''
    if (!d) undated.push(t)
    else if (d < today) overdue.push(t)
    else if (d === today) due.push(t)
    else if (d <= horizon) soon.push(t)
    else undated.push(t)
  }
  const byDue = (a, b) =>
    String(a.due_date || '').localeCompare(String(b.due_date || '')) || (a.id || 0) - (b.id || 0)
  overdue.sort(byDue)
  due.sort(byDue)
  soon.sort(byDue)
  return { overdue, due, soon, undated }
}

function addDays(isoDate, days) {
  if (!isoDate) return isoDate
  const d = new Date(isoDate + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return isoDate
  d.setDate(d.getDate() + days)
  return d.toLocaleDateString('sv-SE')
}
