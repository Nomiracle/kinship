// 单品状态：值域、标签、是否「在手」，以及「改状态」表单的纯逻辑。
// 与后端 backend/models.py 的 WARDROBE_STATUSES / WARDROBE_STATUS_LABELS 一一对应。

export const STATUS_OPTIONS = [
  { key: 'in_use', label: '在役' },
  { key: 'idle', label: '闲置收纳' },
  { key: 'sold', label: '已卖出' },
  { key: 'gifted', label: '已送人' },
  { key: 'lost', label: '已丢失' },
  { key: 'damaged', label: '损坏待修' },
  { key: 'discarded', label: '已丢弃' },
]

export const STATUS_LABELS = STATUS_OPTIONS.reduce((acc, o) => {
  acc[o.key] = o.label
  return acc
}, {})

// 在手 = 还能穿、还算「衣橱里的东西」；其余都是已离手
export const ON_HAND_STATUSES = ['in_use', 'idle']

// 离手必须写一句原因（否则半年后看到「已卖出」也不知道为什么）
export const OFF_HAND_STATUSES = ['sold', 'gifted', 'lost', 'damaged', 'discarded']

export function statusLabel(item) {
  if (!item) return ''
  return item.status_label || STATUS_LABELS[item.status] || item.status || ''
}

export function isOnHand(item) {
  return !!item && ON_HAND_STATUSES.includes(item.status) && !item.merged_into_id
}

export function requiresReason(status) {
  return OFF_HAND_STATUSES.includes(status)
}

// 列表筛选：hand 在手 / in_use 在役 / idle 闲置 / offhand 已离手 / all 全部
export function filterByStatusScope(items, scope) {
  if (!Array.isArray(items)) return []
  if (!scope || scope === 'all') return items.slice()
  if (scope === 'offhand') return items.filter((it) => !ON_HAND_STATUSES.includes(it.status))
  if (scope === 'hand') return items.filter((it) => ON_HAND_STATUSES.includes(it.status))
  return items.filter((it) => it.status === scope)
}

// 改状态表单 → PATCH body（空值不传，避免把已有原因清掉）
export function buildStatusPatch({ status, reason, date }) {
  const patch = {}
  if (status) patch.status = status
  const text = (reason || '').trim()
  if (text) patch.status_reason = text
  if (date) patch.status_changed_on = date
  return patch
}

// 返回第一个错误文案；没错返回空串
export function validateStatusChange({ status, reason }) {
  if (!status) return '请选择状态'
  if (!STATUS_LABELS[status]) return '未知状态'
  if (requiresReason(status) && !(reason || '').trim()) {
    return '「' + STATUS_LABELS[status] + '」需要写一句原因'
  }
  if ((reason || '').length > 255) return '原因最多 255 个字'
  return ''
}

// 「加入衣橱」显示文案：added_at 已是本地墙钟（服务端写入，不做时区换算）
export function formatAdded(item) {
  if (!item) return ''
  if (item.added_at) return item.added_at
  if (item.added_on) return item.added_on
  return ''
}

// 替换关系候选：同一个人、不在合并态、排除自己
export function replaceCandidates(items, currentId) {
  if (!Array.isArray(items)) return []
  return items.filter((it) => !it.merged_into_id && it.id !== currentId)
}
