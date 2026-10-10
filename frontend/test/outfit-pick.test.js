import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  eventThumb,
  isEmptyPick,
  itemThumb,
  pickKey,
  pickLabel,
  toOutfitRefs,
} from '../src/lib/outfit-pick.js'

// 假 mediaUrl：缩略图 / 原图两种 URL（像 api.mediaUrl 一样，优先用 thumb_path）
const mediaUrl = (m, thumb = true) =>
  `${thumb ? 'thumb' : 'full'}:/${(thumb && m.thumb_path) || m.path}`

test('toOutfitRefs：带 id 的复用单品，没 id 的先查后建（顺序保持）', () => {
  const refs = toOutfitRefs([
    { item_id: 12, category: 'bottom', name: '黑裤', color: '黑色' },
    { category: 'top', name: '白毛衣', color: null },
  ])
  assert.deepEqual(refs, [
    { item_id: 12 },
    { category: 'top', name: '白毛衣', color: null },
  ])
})

test('toOutfitRefs：空草稿 → 空数组（后端收到空 items 会按 0 单品处理）', () => {
  assert.deepEqual(toOutfitRefs([]), [])
  assert.deepEqual(toOutfitRefs(undefined), [])
  assert.deepEqual(toOutfitRefs([{ category: 'shoes', name: '小白鞋' }]), [
    { category: 'shoes', name: '小白鞋', color: null },
  ])
})

test('toOutfitRefs：缺类别的内联单品兜底到 other，不会发成没有 category 的引用', () => {
  assert.deepEqual(toOutfitRefs([{ name: '围巾' }]), [
    { category: 'other', name: '围巾', color: null },
  ])
})

test('itemThumb：优先单品自己的第一张图；没有照片/只有视频 → null（界面用类别占位）', () => {
  assert.equal(
    itemThumb({ media: [{ kind: 'image', path: 'a.jpg', thumb_path: 'a_t.jpg' }] }, mediaUrl),
    'thumb:/a_t.jpg'
  )
  assert.equal(itemThumb({ media: [{ kind: 'video', path: 'v.mp4' }] }, mediaUrl), null)
  assert.equal(itemThumb({ media: [] }, mediaUrl), null)
  assert.equal(itemThumb({}, mediaUrl), null)
  // 第一张是视频、第二张是图片 → 取图片那张（不要给破图）
  assert.equal(
    itemThumb(
      { media: [{ kind: 'video', path: 'v.mp4' }, { kind: 'image', path: 'b.jpg' }] },
      mediaUrl
    ),
    'thumb:/b.jpg'
  )
})

test('eventThumb：记录自己的首图（挂在事件上）', () => {
  assert.equal(eventThumb({ media: [{ id: 1, kind: 'image', path: 'x.jpg' }] }, mediaUrl), 'thumb:/x.jpg')
  assert.equal(eventThumb({ media: [{ id: 2, kind: 'video', path: 'y.mp4' }] }, mediaUrl), null)
  assert.equal(eventThumb(null, mediaUrl), null)
})

test('pickKey / pickLabel：已选区能稳定去重并显示「名称 · 颜色」', () => {
  assert.equal(pickKey({ item_id: 7 }), 'i7')
  assert.equal(pickKey({ category: 'top', name: '白毛衣' }), 'ntop:白毛衣')
  assert.equal(pickLabel({ name: '黑裤', color: '黑色' }), '黑裤 · 黑色')
  assert.equal(pickLabel({ name: '黑裤', color: null }), '黑裤')
  assert.equal(isEmptyPick([]), true)
  assert.equal(isEmptyPick([{ item_id: 1 }]), false)
})
