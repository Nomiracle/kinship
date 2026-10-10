// 模块门控：一个人「能记什么」= 该人的模块开关。
// 规则与 /api/config 的 event_types[].module 一致：
//   - 没绑 module 的（文字/情绪/里程碑/爱好/社交）任何时候都能记；
//   - 绑了 module 的，必须该模块已启用。
// 前端不写死映射，全部读 config，避免各页门控分叉。

export function availableEventTypes(eventTypes, enabledModules) {
  const enabled = new Set(enabledModules || [])
  return (eventTypes || []).filter((t) => !t.module || enabled.has(t.module))
}

// 切人后当前选中的类型可能已失效 → 回退到 fallback（默认 text），
// 否则会记出这个人没有开的功能类型。
export function reconcileEventType(currentType, types, fallback = 'text') {
  return (types || []).some((t) => t.key === currentType) ? currentType : fallback
}

// 某个模块三态（返回值语义，配合 api.modules 的惰性加载）：
//   true  → 已知启用
//   false → 已知未启用
//   null  → 未知（仍在加载 / 加载失败）—— 调用方据此「暂不隐藏」
export function moduleState(enabledModules, key) {
  if (!Array.isArray(enabledModules)) return null
  return enabledModules.includes(key)
}

// 衣橱（服装模块）入口是否可见。传一组三态值：
//   - 任意一个是 true → 可见（「全部」scope 下只要有一个人开了服装就显示）；
//   - 全部已知且都是 false → 隐藏；
//   - 存在未知（null/undefined）→ 可见（加载中/失败时不隐藏，legacy 路由仍可达）。
export function anyOutfitEnabled(states) {
  let unknown = false
  for (const s of states || []) {
    if (s === true) return true
    if (s !== false) unknown = true
  }
  return unknown
}
