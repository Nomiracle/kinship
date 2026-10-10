// 图片「点开放大」的纯逻辑（页面内预览，不再 window.open 新标签页）。
//
// 为什么抽出来：时间轴记录、衣橱单品详情、个人页三处都要「点哪张就放大哪张」，
// 而列表里常混着视频（<img> 装不下、van-image-preview 也放不了），
// 预览集合必须只收图片、按 id 去重、并把被点那张的下标算对。
//
// 旧行为是 window.open(原图, '_blank')：手机上会把 SPA 丢到后台，
// 看完还得手动切回来；而相册页早就是页面内 van-image-preview（支持双指放大）。

// 可预览的图片（video 交给原片新标签页，见各页面的 openFull）
export function previewable(media) {
  return (media || []).filter((m) => m && m.kind !== 'video')
}

// 去重 + 定位被点的那张。
// 去重是必须的，而且要按「文件」去重而不是按行 id：媒体文件按内容哈希命名，同一张图
// 可能既有单品照片行、又被穿着历史的行引用（两行同一 path），只按 id 去重预览里会出现
// 两张一模一样的，左右滑动像卡住。path 缺失时退回 id。
// 找不到（点击项不在集合里，例如列表刚刷新过）时退化为第一张，预览至少能打开。
export function previewSet(media, clicked) {
  const seen = new Set()
  const images = []
  for (const m of previewable(media)) {
    const key = m.path || `id:${m.id}`
    if (seen.has(key)) continue
    seen.add(key)
    images.push(m)
  }
  const i = images.findIndex((m) =>
    clicked && (m.path ? m.path === clicked.path : m.id === clicked.id)
  )
  return { images, index: i < 0 ? 0 : i }
}

// 预览用的原图 URL（缩略图放大会糊）＋起始下标。
// mediaUrl 由调用方传入（api.mediaUrl），这里不依赖 api 模块，便于单测。
export function previewUrls(media, clicked, mediaUrl) {
  const { images, index } = previewSet(media, clicked)
  return { images: images.map((m) => mediaUrl(m, false)), index }
}
