import { test } from 'node:test'
import assert from 'node:assert/strict'
import { previewable, previewSet, previewUrls } from '../src/lib/media-preview.js'

// 假 mediaUrl：缩略图 /原图 两种 URL，便于断言「预览用的是原图」
const mediaUrl = (m, thumb = true) => `${thumb ? 'thumb' : 'full'}:/${m.path}`

test('previewable 只收图片：视频与空行都排除', () => {
  const list = [
    { id: 1, kind: 'image', path: 'a.jpg' },
    { id: 2, kind: 'video', path: 'b.mp4' },
    { id: 3, kind: 'image', path: 'c.jpg' },
    null,
  ]
  assert.deepEqual(previewable(list).map((m) => m.id), [1, 3])
  assert.deepEqual(previewable(undefined), [])
})

test('previewSet 按 id 去重（同一张既挂事件又被穿着历史带出时不重复）', () => {
  const list = [
    { id: 1, kind: 'image', path: 'a.jpg' },
    { id: 2, kind: 'image', path: 'b.jpg' },
    { id: 1, kind: 'image', path: 'a.jpg' },
    { id: 7, kind: 'video', path: 'v.mp4' },
  ]
  const { images, index } = previewSet(list, list[1])
  assert.deepEqual(images.map((m) => m.id), [1, 2])
  assert.equal(index, 1, '点第 2 张（id=2）应从下标 1 开始')
})

test('previewSet 也按文件去重：媒体按内容哈希命名，两行同一 path 只算一张', () => {
  // 真实情形：单品照片行 + 穿着历史带出的行指向同一个文件（两条 id 不同）
  const list = [
    { id: 40, kind: 'image', path: '2026/10/x.jpeg' },
    { id: 41, kind: 'image', path: '2026/10/x.jpeg' },
    { id: 42, kind: 'image', path: '2026/10/y.jpeg' },
  ]
  const { images, index } = previewSet(list, list[2])
  assert.equal(images.length, 2, '同一 path 只保留一张')
  assert.equal(index, 1, 'y.jpeg 落在下标 1')
  // 点到重复行的第二行时，同样定位到那一张
  assert.equal(previewSet(list, { id: 41, kind: 'image', path: '2026/10/x.jpeg' }).index, 0)
  // 没有 path 的行退回按 id 去重
  const noPath = [{ id: 1, kind: 'image' }, { id: 1, kind: 'image' }, { id: 2, kind: 'image' }]
  assert.equal(previewSet(noPath, { id: 2 }).images.length, 2)
})

test('previewSet 定位被点的那张；找不到时退化为第一张（不让预览打不开）', () => {
  const list = [
    { id: 1, kind: 'image', path: 'a.jpg' },
    { id: 2, kind: 'image', path: 'b.jpg' },
    { id: 3, kind: 'image', path: 'c.jpg' },
  ]
  assert.equal(previewSet(list, list[2]).index, 2)
  assert.equal(previewSet(list, { id: 999, kind: 'image' }).index, 0)
  assert.equal(previewSet(list, null).index, 0)
})

test('previewUrls 用原图 URL（缩略图放大会糊），顺序与集合一致', () => {
  const list = [
    { id: 1, kind: 'image', path: 'a.jpg' },
    { id: 2, kind: 'video', path: 'b.mp4' },
    { id: 3, kind: 'image', path: 'c.jpg' },
  ]
  const { images, index } = previewUrls(list, list[2], mediaUrl)
  assert.deepEqual(images, ['full:/a.jpg', 'full:/c.jpg'])
  assert.equal(index, 1, '跳过了视频，id=3 应落在下标 1')
})

test('previewUrls 不依赖 api 模块（mediaUrl 由调用方注入，便于单测）', () => {
  const calls = []
  const spy = (m, thumb) => {
    calls.push([m.id, thumb])
    return 'x'
  }
  previewUrls([{ id: 5, kind: 'image', path: 'e.jpg' }], { id: 5 }, spy)
  assert.deepEqual(calls, [[5, false]], '必须显式传 thumb=false')
})
