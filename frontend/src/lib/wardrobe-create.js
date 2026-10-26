// 衣物独立创建（无日期）的纯逻辑 —— P0 衣橱首图链路
// 设计：与后端 WardrobeItemIn 对齐，不含任何日期字段；显式归属人，不静默选第一个人。

export const EMPTY_WEAR_TEXT = '暂无穿着记录'
export const UNMERGE_WARNING = '撤销合并只恢复“已合并”标记，穿着记录不会自动拆回。如需还原请手动调整。'
export const UNMERGE_DETAIL = '穿着记录已合到目标单品，撤销后不会自动拆回。'

export function getEmptyWearText() {
  return EMPTY_WEAR_TEXT
}

export function getUnmergeWarning() {
  return UNMERGE_WARNING
}

// 归一化：去首尾空格、转小写，用于前端查重提示（后端 canonical_key 更严格）
export function normalizeKey(text) {
  if (!text) return ''
  return String(text).trim().toLowerCase().replace(/\s+/g, '')
}

// 搜索归一化
export function normalizeSearch(q) {
  if (!q) return ''
  return String(q).trim().toLowerCase()
}

// 构建创建荷载（绝不含日期）
export function buildWardrobeItemPayload({ personId, name, category, color, tags, notes, sensitivity, replacesItemId }) {
  const pid = personId != null ? Number(personId) : null
  const payload = {
    person_id: pid,
    category: (category || 'other').trim(),
    name: String(name || '').trim(),
    color: color ? String(color).trim() || null : null,
    tags: tags ? String(tags).trim() || null : null,
    notes: notes ? String(notes).trim() || null : null,
    sensitivity: sensitivity || 'normal',
  }
  // 替换关系（新件指向被替代的旧件）：空值不发，避免 PATCH 时把已有关联清掉
  const rid = replacesItemId != null && replacesItemId !== '' ? Number(replacesItemId) : null
  if (rid) payload.replaces_item_id = rid
  // 清理空字符串
  if (!payload.category) payload.category = 'other'
  return payload
}

// 校验：名称必填，归属人必填，不允许日期字段
export function validateWardrobeItem(payload, { requirePerson = true } = {}) {
  const errors = []
  if (!payload || typeof payload !== 'object') {
    return { valid: false, errors: ['参数错误'] }
  }
  if (!payload.name || !String(payload.name).trim()) {
    errors.push('请填写名称')
  }
  if (String(payload.name || '').length > 128) {
    errors.push('名称过长')
  }
  if (requirePerson && (payload.person_id == null || Number.isNaN(Number(payload.person_id)) || Number(payload.person_id) <= 0)) {
    errors.push('请选择归属人')
  }
  if ('event_date' in payload || 'event_time' in payload || 'date' in payload) {
    errors.push('衣物不应含日期')
  }
  if (payload.category && typeof payload.category !== 'string') {
    errors.push('类别格式错误')
  }
  return { valid: errors.length === 0, errors }
}

// 是否需要显式选人（当前范围为全部时）
export function requiresExplicitPerson(effectivePersonId) {
  return !effectivePersonId
}

// 前端本地查重预览：同人+同类别+同名同色（小写去空格）
export function findDuplicatePreview(items, candidate) {
  if (!items || !candidate) return null
  const nameKey = normalizeKey(candidate.name)
  const colorKey = normalizeKey(candidate.color)
  if (!nameKey) return null
  return (
    items.find((it) => {
      if (candidate.person_id && it.person_id !== Number(candidate.person_id)) return false
      if (candidate.category && it.category !== candidate.category) return false
      return normalizeKey(it.name) === nameKey && normalizeKey(it.color) === colorKey
    }) || null
  )
}

// 从 409 错误中提取 existing_id / duplicate 信息
export function parseDuplicateError(err) {
  if (!err) return null
  const detail = err.detail || err.data?.detail || err.response?.data?.detail
  if (detail && typeof detail === 'object' && detail.existing_id) {
    return { existingId: detail.existing_id, message: detail.message || '已有同名同色单品' }
  }
  // 兼容后端直接抛的字符串
  const msg = err.message || ''
  if (msg.includes('已有同名同色') || msg.includes('已有单品')) {
    return { existingId: null, message: msg }
  }
  return null
}

// 衣橱列表过滤（客户端）：类别/颜色/搜索/无穿着记录
export function filterWardrobeItems(items, { category, color, q, onlyNoHistory, searchFields = ['name', 'color', 'tags', 'notes'] } = {}) {
  if (!Array.isArray(items)) return []
  let out = items.slice()
  if (category) {
    out = out.filter((it) => it.category === category)
  }
  if (color) {
    const ck = normalizeKey(color)
    out = out.filter((it) => !!normalizeKey(it.color) && (normalizeKey(it.color).includes(ck) || ck.includes(normalizeKey(it.color))))
  }
  if (q) {
    const nq = normalizeSearch(q)
    out = out.filter((it) => {
      for (const f of searchFields) {
        const v = it[f]
        if (v && String(v).toLowerCase().includes(nq)) return true
      }
      return false
    })
  }
  if (onlyNoHistory) {
    out = out.filter((it) => Number(it.wear_count || 0) === 0)
  }
  return out
}

// 颜色选项从现有 items 中提取（去重）
export function collectColors(items) {
  const set = new Set()
  for (const it of items || []) {
    if (it.color) set.add(String(it.color).trim())
  }
  return [...set].sort()
}

// 创建后初始状态断言（wear_count=0, 无日期）
export function assertNewItemState(item) {
  return item && item.wear_count === 0 && (item.first_worn_on == null) && (item.last_worn_on == null)
}

// 构建上传重试队列：失败项保留，其余移除
export function partitionUploadResults(results) {
  const ok = []
  const failed = []
  for (const r of results || []) {
    if (r.ok) ok.push(r)
    else failed.push(r)
  }
  return { ok, failed }
}

// 生成继续操作链接 — preserve person='all' when scope is all
export function nextActions(itemId, personId, rawPersonQuery) {
  let q = ''
  if (rawPersonQuery === 'all') q = '?person=all'
  else if (personId) q = `?person=${personId}`
  else if (rawPersonQuery === 'all' || rawPersonQuery == null) {
    // if caller explicitly passed 'all', preserve it; otherwise empty
    q = ''
  }
  // fallback: if personId null but raw query indicates all, keep all
  if (!personId && rawPersonQuery === 'all') q = '?person=all'
  return {
    wardrobe: '/wardrobe' + q,
    outfit: `/wardrobe/new${q}${q ? '&' : '?'}item=${itemId}`,
    edit: `/wardrobe/items/${itemId}/edit${q}`,
  }
}

// ------------------------------------------------------------
// 新增：幂等与提交生命周期（用于行为测试，非纯字符串匹配）
// ------------------------------------------------------------

export function generateIdempotencyKey() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  } catch {}
  // fallback 保证唯一且 <=128
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}-${Math.random().toString(36).slice(2, 10)}`
}

export function snapshotPayload(payload) {
  return JSON.parse(JSON.stringify(payload))
}

// 为每个待上传文件生成/复用稳定 UUID（与 index/name 无关，捕获一次后不变，<=128）
export function ensureFileStableKeys(files) {
  if (!Array.isArray(files)) return []
  for (const f of files) {
    if (!f) continue
    // 兼容 vant 的 fileList 项：可能是 {file: File, url...} 或直接 File
    const target = f.file ? f.file : f
    // 已有则保留
    if (target._wardrobeFileKey && typeof target._wardrobeFileKey === 'string' && target._wardrobeFileKey.length <= 128) {
      if (target !== f && !f._wardrobeFileKey) f._wardrobeFileKey = target._wardrobeFileKey
      continue
    }
    // 容器本身也可能存
    if (f._wardrobeFileKey && typeof f._wardrobeFileKey === 'string' && f._wardrobeFileKey.length <= 128) {
      if (target !== f) target._wardrobeFileKey = f._wardrobeFileKey
      continue
    }
    const k = generateIdempotencyKey()
    // 长度保证 <=128（UUID 36 远小于）
    const final = k.length > 128 ? k.slice(0, 128) : k
    if (target !== f) {
      target._wardrobeFileKey = final
      f._wardrobeFileKey = final
    } else {
      f._wardrobeFileKey = final
    }
  }
  return files
}

export function getFileStableKey(file) {
  if (!file) return null
  const raw = file.file || file
  return raw._wardrobeFileKey || file._wardrobeFileKey || null
}

// 衣物创建提交管理器：快照锁、稳定键、保留创建ID、失败重试同键
export function createWardrobeSubmitManager() {
  let snapshot = null
  let key = null
  let createdItem = null
  let uncertain = false
  let partial = false // 部分上传失败
  return {
    get snapshot() { return snapshot },
    get key() { return key },
    get createdItem() { return createdItem },
    get uncertain() { return uncertain },
    get partial() { return partial },
    hasSnapshot() { return !!snapshot },
    isLocked() { return uncertain || !!snapshot && !createdItem },
    ensureSnapshot(payload, files) {
      if (!snapshot) {
        snapshot = snapshotPayload(payload)
        key = generateIdempotencyKey()
        if (key.length > 128) key = key.slice(0, 128)
        if (files) ensureFileStableKeys(files)
      } else if (files) {
        // 为后续新增的文件补键，已有快照仍复用原 key/payload，不因新文件改动快照
        ensureFileStableKeys(files)
      }
      return { payload: snapshot, key }
    },
    markCreated(item) {
      createdItem = item || null
      uncertain = false
      partial = false
    },
    markUncertain() {
      uncertain = true
    },
    markPartial() {
      partial = true
    },
    clearPartial() { partial = false },
    retainAfterUncertain() {
      // 不丢弃 snapshot/key/createdItem
    },
    clearForNewDraft() {
      snapshot = null
      key = null
      createdItem = null
      uncertain = false
      partial = false
    },
    shouldBlockSubmit(saving) {
      return !!saving || uncertain || partial
    },
    // 用于编辑：不复用创建快照，编辑本身无 createdItem 断言
    resetForEdit() {
      snapshot = null
      key = null
      createdItem = null
      uncertain = false
      partial = false
    },
  }
}

// 上传辅助：按稳定键逐个上传，返回 ok/failed，失败项保留原 file 对象与 key
export async function uploadWardrobePhotos(api, files, { person_id, wardrobe_item_id, captured_on }) {
  if (!files || !files.length) return { ok: [], failed: [] }
  ensureFileStableKeys(files)
  const ok = []
  const failed = []
  for (const f of files) {
    const raw = f.file || f
    if (!raw) {
      failed.push(f)
      continue
    }
    const stableKey = getFileStableKey(f)
    try {
      await api.uploadMedia(raw, { person_id, wardrobe_item_id, captured_on, idempotency_key: stableKey })
      ok.push(f)
    } catch (e) {
      failed.push(f)
    }
  }
  return { ok, failed }
}

// 编辑态上传：复用同一 itemId 的稳定键重试（与创建共用同一套 per-file UUID）
export async function uploadWardrobeEditPhotos(api, itemId, personId, files, capturedOn) {
  return uploadWardrobePhotos(api, files, { person_id: personId, wardrobe_item_id: itemId, captured_on: capturedOn })
}

// scope helper：保留 person='all'（显式全部），否则用 scopeQuery 语义
export function scopeQueryPreserveAll(effectivePersonId, rawQueryPerson) {
  if (rawQueryPerson === 'all') return { person: 'all' }
  if (effectivePersonId) return { person: effectivePersonId }
  return {}
}
