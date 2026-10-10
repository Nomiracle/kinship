// 「记录页选衣物」的纯逻辑：草稿 → 保存时到底发什么 / 已选区怎么显示。
//
// 为什么单独抽出来：这一层决定「保存时发出去的引用」，最容易出哑巴 bug
// （选了三件，保存后只记上一件 / 发成空数组 → 衣橱零变化），所以用纯函数 + 单测守住。
// 约定：草稿里有 item_id 的走「复用已有单品」，没有的走「先查后建」（后端 resolve_refs）。

// 草稿条目（UI 用的形状）
//   复用已有：{ item_id, category, name, color, media: [...] }
//   内联新建：{ category, name, color }（还没有 id，保存时才建）

export function pickKey(p) {
  if (p && p.item_id) return 'i' + p.item_id
  return 'n' + ((p && p.category) || 'other') + ':' + ((p && p.name) || '')
}

export function pickLabel(p) {
  if (!p) return ''
  return p.color ? p.name + ' · ' + p.color : p.name || ''
}

// 草稿 → POST /api/outfits 的 items（全量、顺序保持）
export function toOutfitRefs(picked) {
  return (picked || []).map((p) =>
    p.item_id
      ? { item_id: p.item_id }
      : { category: p.category || 'other', name: p.name, color: p.color || null }
  )
}

// 已选区的缩略图：优先单品自己在衣橱里挂的第一张图；
// 没有照片 / 只有视频 → null（界面用类别色块占位，不要给破图）
export function itemThumb(p, mediaUrl) {
  const list = (p && p.media) || []
  const img = list.find((m) => m && m.kind !== 'video' && (m.thumb_path || m.path))
  return img ? mediaUrl(img) : null
}

// 「刚记的」里那条记录的首图（记录自己的图片挂在事件上）
export function eventThumb(ev, mediaUrl) {
  const list = (ev && ev.media) || []
  const img = list.find((m) => m && m.kind !== 'video')
  return img ? mediaUrl(img) : null
}

// 有没有勾过东西（用于「换人后要不要提示」等）
export function isEmptyPick(picked) {
  return !(picked || []).length
}
