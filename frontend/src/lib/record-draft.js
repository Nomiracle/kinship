export function cloneDraft(data) {
  return JSON.parse(JSON.stringify(data ?? null))
}

export function snapshotDraft(state) {
  const payload = {
    personId: state.personId ?? null,
    type: state.type ?? null,
    eventDate: state.eventDate ?? '',
    eventTime: state.eventTime ?? '',
    title: state.title ?? '',
    body: state.body ?? '',
    tags: state.tags ?? '',
    location: state.location ?? '',
    hours: state.hours ?? '',
    overnight: !!state.overnight,
    manualText: !!state.manualText,
    note: state.note ?? '',
    sensitivity: state.sensitivity ?? 'normal',
    extraIds: [...(state.extraIds || [])].sort((a, b) => a - b),
    picked: (state.picked || [])
      .map((p) => ({
        item_id: p.item_id ?? null,
        category: p.category ?? null,
        name: p.name ?? null,
        color: p.color ?? null,
      }))
      .sort((a, b) => String(a.item_id || a.name).localeCompare(String(b.item_id || b.name))),
    fileNames: (state.fileTasks || state.fileList || [])
      .map((f) => {
        const file = f.file || f
        return (file && file.name) || String(f.name || f) || ''
      })
      .sort(),
  }
  return JSON.stringify(payload)
}

export function isDirty(state, snapshot) {
  if (!snapshot) return true
  return snapshotDraft(state) !== snapshot
}

export function hasUnsavedContent(state) {
  return !!(
    state.title ||
    state.body ||
    state.note ||
    state.tags ||
    state.location ||
    (state.picked && state.picked.length) ||
    (state.fileTasks && state.fileTasks.length) ||
    (state.fileList && state.fileList.length) ||
    state.manualText
  )
}

function normalizeEventTime(v) {
  const t = String(v || '').trim()
  if (!t) return ''
  return t.slice(0, 8)
}

export function createInitialState({ initial, initialType, preselect } = {}) {
  const src = initial || {}
  const isUnifiedEdit = !!src.id

  let personId = null
  if (src.person_id != null && src.person_id !== '') personId = Number(src.person_id)

  let type = src.type_key || src.type || initialType || 'text'
  if (!type) type = 'text'

  let eventDate = ''
  let eventTime = ''
  if (src.event_date) {
    const d = typeof src.event_date === 'string' ? src.event_date.slice(0, 10) : ''
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) eventDate = d
    else if (src.event_date) {
      const iso = String(src.event_date)
      eventDate = iso.slice(0, 10)
    }
    if (src.event_time) eventTime = normalizeEventTime(src.event_time)
    else if (typeof src.event_date === 'string' && src.event_date.includes('T')) {
      eventTime = normalizeEventTime(src.event_date.split('T')[1] || '')
    }
  }
  if (src.eventDate) eventDate = String(src.eventDate).slice(0, 10)
  if (src.eventTime != null) eventTime = normalizeEventTime(src.eventTime)
  if (eventTime === '00:00:00') eventTime = ''

  let picked = []
  const rawItems = src.items || src.outfit_items || src.outfitItems || []
  if (Array.isArray(rawItems) && rawItems.length) {
    picked = rawItems.map((it) => ({
      item_id: it.item_id || it.id || null,
      category: it.category || null,
      name: it.name || null,
      color: it.color || null,
      media: it.media || [],
    }))
  } else if (Array.isArray(src.picked)) {
    picked = [...src.picked]
  }

  const pre = (preselect || []).filter(Boolean).map((n) => Number(n)).filter((n) => n > 0)
  for (const id of pre) {
    if (!picked.some((p) => p.item_id === id)) picked.push({ item_id: id })
  }

  const extraIds = Array.isArray(src.person_ids)
    ? src.person_ids.filter((id) => Number(id) !== Number(personId)).map(Number)
    : Array.isArray(src.extraIds)
      ? [...src.extraIds]
      : []

  // preserve explicit fields for edit: outfit_items, person_ids, manual_text, note/location/sensitivity
  const sensitivity = src.sensitivity || 'normal'
  const location = src.location || ''
  const note = src.note || ''
  // Existing schema has no persisted auto/manual flag. Preserve legacy text on
  // edit rather than silently regenerate it; users may opt back into auto text.
  const manualText = src.manual_text === undefined && src.manualText === undefined
    ? !!(isUnifiedEdit && type === 'outfit' && (src.title || src.body))
    : !!src.manual_text || !!src.manualText

  // hours/overnight are only for meeting type but preserve if present
  const hours = src.hours != null && src.hours !== '' ? String(src.hours) : ''
  const overnight = !!src.overnight

  return {
    personId,
    type,
    eventDate,
    eventTime,
    title: src.title || '',
    body: src.body || '',
    tags: src.tags || '',
    location,
    hours,
    overnight,
    note,
    manualText,
    extraIds,
    picked,
    fileList: [],
    fileTasks: [],
    sensitivity,
    meetingLoaded: !!src.meetingLoaded,
    _isUnifiedEdit: isUnifiedEdit,
  }
}

const sessionStore = new Map()
function copySession(state) {
  // Session memory may retain File objects, never JSON-serialize them to {}.
  return { ...cloneDraft({...state,fileTasks:[],fileList:[]}), fileTasks:(state.fileTasks||[]).map(t=>({...t,file:t.file})), fileList:[...(state.fileList||[])] }
}
export function saveSessionDraft(key, state) {
  if (!key) return
  sessionStore.set(key, copySession(state))
}
export function loadSessionDraft(key) {
  if (!key) return null
  const v = sessionStore.get(key)
  return v ? copySession(v) : null
}
export function clearSessionDraft(key) {
  if (!key) return
  sessionStore.delete(key)
}
export function shouldWarnOnLeave(state, snapshot) {
  return isDirty(state, snapshot)
}
