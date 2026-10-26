// 「刚记的」列表合并。
//
// 为什么需要它：保存成功后原来会再 `GET /api/events?...order=created` 把整个列表
// 重新拉一遍。在手机链路上（中国电信 → CF → 东京，实测每往返 400–500ms）这次回源
// 就是白等的一个往返 —— POST 的返回体（EventOut）已经包含渲染所需的全部字段
// （id / type_key / person_name / event_date / title / body / items）。
//
// 唯一的例外：这次带了图片。上传后的 media 只存在于服务端那一份里，返回体里没有，
// 所以调用方在上传张数 > 0 时仍应回源（见 NewRecord.vue 的 submit）。
export function mergeRecent(list, created, limit = 5) {
  const old = Array.isArray(list) ? list : []
  if (!created || !created.id) return old
  // 同 id 去重：防止「回源 + 本地插入」两条路径都走时出现重复行
  return [created, ...old.filter((r) => r && r.id !== created.id)].slice(0, limit)
}
