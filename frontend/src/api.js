// 统一的后端调用封装：口令放 localStorage，401 时清掉并提示重新输入。
const TOKEN_KEY = 'kinship_token'
const COOKIE_KEY = 'kinship_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(v) {
  if (v) {
    localStorage.setItem(TOKEN_KEY, v)
    // 同时下发 Cookie：<img>/<video> 没法带自定义请求头，而把口令写进 URL
    // 会让它漏进浏览器历史、Referer，以及 nginx / Cloudflare 的访问日志
    const secure = location.protocol === 'https:' ? '; Secure' : ''
    document.cookie =
      COOKIE_KEY + '=' + encodeURIComponent(v) + '; path=/; max-age=31536000; SameSite=Lax' + secure
  } else {
    localStorage.removeItem(TOKEN_KEY)
    document.cookie = COOKIE_KEY + '=; path=/; max-age=0'
  }
}

async function request(method, path, body, idempotencyKey) {
  const headers = {}
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  const token = getToken()
  if (token) headers['X-Archive-Token'] = token
  // FormData 交给浏览器自己设 Content-Type（含 boundary），手写会坏掉上传
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  const payload = body === undefined ? undefined : isForm ? body : JSON.stringify(body)
  const res = await fetch(path, { method, headers, body: payload })
  if (res.status === 401) {
    setToken('')
    const err = new Error('口令无效或已失效，请重新输入')
    err.status = 401
    throw err
  }
  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    // detail 可能是字符串，也可能是对象（如 409 冲突带 existing_id）——
    // 对象时优先取 message，同时把整个 detail 挂到 err 上给页面用
    const detail = data && data.detail
    const msg = (detail && detail.message) || detail || '请求失败 ' + res.status
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.status = res.status
    err.detail = detail
    throw err
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  patch: (p, b) => request('PATCH', p, b),
  put: (p, b) => request('PUT', p, b),
  del: (p) => request('DELETE', p),

  // 便捷封装
  health: () => request('GET', '/api/health'),
  config: () => request('GET', '/api/config'),
  persons: (includeInactive) =>
    request('GET', '/api/persons' + (includeInactive ? '?include_inactive=true' : '')),
  createPerson: (p) => request('POST', '/api/persons', p),
  person: (id) => request('GET', `/api/persons/${id}`),
  patchPerson: (id, p) => request('PATCH', `/api/persons/${id}`, p),
  deletePerson: (id) => request('DELETE', `/api/persons/${id}`),
  modules: (id) => request('GET', `/api/persons/${id}/modules`),
  putModules: (id, modules) => request('PUT', `/api/persons/${id}/modules`, { modules }),

  // ---- 关系边（人与人之间，比如「她的闺蜜」「她的姐姐」）----
  relations: (personId) =>
    request('GET', '/api/relations' + (personId ? `?person_id=${personId}` : '')),
  createRelation: (r) => request('POST', '/api/relations', r),
  deleteRelation: (id) => request('DELETE', `/api/relations/${id}`),

  attributes: (personId) => request('GET', `/api/attributes?person_id=${personId}`),
  createAttribute: (a) => request('POST', '/api/attributes', a),
  deleteAttribute: (id) => request('DELETE', `/api/attributes/${id}`),

  events: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    )
    return request('GET', '/api/events?' + q.toString())
  },
  createEvent: (e, key) => request('POST', '/api/events', e, key),
  patchEvent: (id, e) => request('PATCH', `/api/events/${id}`, e),
  deleteEvent: (id) => request('DELETE', `/api/events/${id}`),

  cycle: (personId) => request('GET', `/api/cycle?person_id=${personId}`),
  createCycle: (c) => request('POST', '/api/cycle', c),
  deleteCycle: (id) => request('DELETE', `/api/cycle/${id}`),
  cyclePrediction: (personId) => request('GET', `/api/cycle/prediction?person_id=${personId}`),

  interactions: (personId) => request('GET', `/api/interactions?person_id=${personId}`),
  createInteraction: (i) => request('POST', '/api/interactions', i),
  deleteInteraction: (id) => request('DELETE', `/api/interactions/${id}`),

  gifts: (personId) => request('GET', `/api/gifts?person_id=${personId}`),
  createGift: (g) => request('POST', '/api/gifts', g),
  deleteGift: (id) => request('DELETE', `/api/gifts/${id}`),

  specialDays: (personId) =>
    request('GET', '/api/special-days' + (personId ? `?person_id=${personId}` : '')),
  createSpecialDay: (s) => request('POST', '/api/special-days', s),
  deleteSpecialDay: (id) => request('DELETE', `/api/special-days/${id}`),

  todos: (personId, includeDone) => {
    const q = new URLSearchParams()
    if (personId) q.set('person_id', personId)
    if (includeDone) q.set('include_done', 'true')
    return request('GET', '/api/todos?' + q.toString())
  },
  createTodo: (t) => request('POST', '/api/todos', t),
  patchTodo: (id, t) => request('PATCH', `/api/todos/${id}`, t),
  deleteTodo: (id) => request('DELETE', `/api/todos/${id}`),

  today: (personId) =>
    request('GET', '/api/today' + (personId ? `?person_id=${personId}` : '')),
  upcoming: (days = 10) => request('GET', `/api/upcoming?days=${days}`),
  overview: () => request('GET', '/api/stats/overview'),
  search: (q, personId) =>
    request(
      'GET',
      `/api/search?q=${encodeURIComponent(q)}` + (personId ? `&person_id=${personId}` : '')
    ),

  // ---- 服装：单品档案 + 穿搭（去重的落点）----
  wardrobeItems: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    )
    return request('GET', '/api/wardrobe/items?' + q.toString())
  },
  createWardrobeItem: (item, key) => request('POST', '/api/wardrobe/items', item, key),
  wardrobeItem: (id) => request('GET', `/api/wardrobe/items/${id}`),
  patchWardrobeItem: (id, patch) => request('PATCH', `/api/wardrobe/items/${id}`, patch),
  deleteWardrobeItem: (id) => request('DELETE', `/api/wardrobe/items/${id}`),
  mergeWardrobeItem: (id, intoId) =>
    request('POST', `/api/wardrobe/items/${id}/merge`, { into_id: intoId }),
  unmergeWardrobeItem: (id) => request('POST', `/api/wardrobe/items/${id}/unmerge`, {}),
  wardrobeDuplicates: (personId) =>
    request('GET', '/api/wardrobe/duplicates' + (personId ? `?person_id=${personId}` : '')),
  createOutfit: (outfit, key) => request('POST', '/api/outfits', outfit, key),
  outfit: (eventId) => request('GET', `/api/outfits/${eventId}`),
  removeWear: (eventId, itemId) => request('DELETE', `/api/outfits/${eventId}/items/${itemId}`),

  // ---- 媒体 ----
  media: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    )
    return request('GET', '/api/media?' + q.toString())
  },
  uploadMedia: (file, opts = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (opts.person_id) fd.append('person_id', opts.person_id)
    if (opts.event_id) fd.append('event_id', opts.event_id)
    if (opts.wardrobe_item_id) fd.append('wardrobe_item_id', opts.wardrobe_item_id)
    if (opts.captured_on) fd.append('captured_on', opts.captured_on)
    return request('POST', '/api/media', fd, opts.idempotency_key)
  },
  deleteMedia: (id) => request('DELETE', `/api/media/${id}`),
  storage: () => request('GET', '/api/media/storage'),
  // 图片地址不再带口令（改由 Cookie 鉴权）：URL 干净，日志/历史/Referer 都不泄漏
  mediaUrl: (m, thumb = true) => `/media/${thumb ? m.thumb_path || m.path : m.path}`,
}
