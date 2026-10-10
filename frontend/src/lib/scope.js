// 「全局 scope」与「下游页 ?person 覆盖」的纯逻辑。
//
// 规则：只有具体的人（正整数）才生成 ?person=<id>；「全部」/无效值不生成任何
// query（显式 null），这样下游页能区分「跟随全局（全部）」而不是误带到某个人。
// 下游页读 ?person 只为「显示这一页」，绝不写回全局 scope（换人只在首页）。

export function normalizePersonId(value) {
  // 只接受「正的安全整数」：小数（2.5）、负数、0、空串、'all'、Infinity、
  // 超出 MAX_SAFE_INTEGER 的值一律视为无效 → null。
  if (value === null || value === undefined || value === '') return null
  const id = typeof value === 'number' ? value : Number(value)
  if (!Number.isSafeInteger(id) || id <= 0) return null
  return id
}

// 生成 router-link 的 query：具体人 → { person: id }；全部/无效 → {}（无 person 键）
export function scopeQuery(personId) {
  const id = normalizePersonId(personId)
  return id ? { person: id } : {}
}

// 下游页求「实际显示谁」：优先 URL 的 ?person，其次全局当前人物；都不写回全局。
export function resolveScopedPerson(queryPerson, globalPersonId) {
  return normalizePersonId(queryPerson) || normalizePersonId(globalPersonId)
}

// 本页「实际显示谁」的只读解析（不改全局）：
//   - /person/:id 详情页用路由参数（那里没有 ?person）；
//   - 其余下游页（时间轴/相册/衣橱/待办）用 ?person；
//   - 都没有 → null（=「全部」或跟随全局）。
export function routeScopePersonId(route) {
  if (!route) return null
  if (route.name === 'person') return normalizePersonId(route.params?.id)
  return normalizePersonId(route.query?.person)
}
