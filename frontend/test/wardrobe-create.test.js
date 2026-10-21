import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildWardrobeItemPayload,
  validateWardrobeItem,
  filterWardrobeItems,
  findDuplicatePreview,
  parseDuplicateError,
  getEmptyWearText,
  getUnmergeWarning,
  normalizeKey,
  requiresExplicitPerson,
  assertNewItemState,
  collectColors,
  nextActions,
  generateIdempotencyKey,
  snapshotPayload,
  ensureFileStableKeys,
  getFileStableKey,
  createWardrobeSubmitManager,
  uploadWardrobePhotos,
  scopeQueryPreserveAll,
} from '../src/lib/wardrobe-create.js'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = (rel) => readFileSync(join(here, '..', rel), 'utf8')

// ---- 构建荷载无日期，且归属显式 ----

test('buildWardrobeItemPayload 不含日期字段', () => {
  const p = buildWardrobeItemPayload({ personId: 3, name: ' 黑色阔腿裤 ', category: 'bottom', color: ' 黑色 ' })
  assert.equal(p.person_id, 3)
  assert.equal(p.name, '黑色阔腿裤')
  assert.equal(p.category, 'bottom')
  assert.equal(p.color, '黑色')
  assert.ok(!('event_date' in p))
  assert.ok(!('event_time' in p))
  assert.ok(!('date' in p))
})

test('buildWardrobeItemPayload 空颜色转为 null', () => {
  const p = buildWardrobeItemPayload({ personId: 1, name: '白衬衫', category: 'top', color: '' })
  assert.equal(p.color, null)
})

test('validateWardrobeItem 名称必填、归属人必填', () => {
  assert.equal(validateWardrobeItem({ name: '', person_id: 1 }).valid, false)
  assert.equal(validateWardrobeItem({ name: '  ', person_id: 1 }).valid, false)
  assert.equal(validateWardrobeItem({ name: '白衬衫', person_id: null }).valid, false)
  assert.equal(validateWardrobeItem({ name: '白衬衫', person_id: 0 }).valid, false)
  assert.equal(validateWardrobeItem({ name: '白衬衫', person_id: 5 }).valid, true)
})

test('validateWardrobeItem 拒绝日期字段', () => {
  const r = validateWardrobeItem({ name: '裤子', person_id: 1, event_date: '2026-10-21' })
  assert.equal(r.valid, false)
  assert.ok(r.errors.some((e) => e.includes('日期')))
})

test('requiresExplicitPerson 全部范围需显式选人', () => {
  assert.equal(requiresExplicitPerson(null), true)
  assert.equal(requiresExplicitPerson(undefined), true)
  assert.equal(requiresExplicitPerson(0), true)
  assert.equal(requiresExplicitPerson(5), false)
})

test('normalizeKey 去空格小写', () => {
  assert.equal(normalizeKey(' 黑色 '), '黑色')
  assert.equal(normalizeKey('BLACK '), 'black')
  assert.equal(normalizeKey(''), '')
})

// ---- 查重预览 ----

test('findDuplicatePreview 同名同色同类命中', () => {
  const items = [
    { id: 1, person_id: 2, category: 'top', name: '白衬衫', color: '白色' },
    { id: 2, person_id: 2, category: 'bottom', name: '黑裤', color: '黑色' },
  ]
  const hit = findDuplicatePreview(items, { person_id: 2, category: 'top', name: ' 白衬衫 ', color: ' 白色 ' })
  assert.ok(hit)
  assert.equal(hit.id, 1)
  const miss = findDuplicatePreview(items, { person_id: 2, category: 'top', name: '白衬衫', color: '黑色' })
  assert.equal(miss, null)
})

test('parseDuplicateError 从 409 提取 existing_id', () => {
  const err = { status: 409, detail: { message: '已有同名同色单品，请复用或改名', existing_id: 7 } }
  const dup = parseDuplicateError(err)
  assert.equal(dup.existingId, 7)
})

test('filterWardrobeItems 类别/颜色/搜索/无记录筛选', () => {
  const items = [
    { id: 1, category: 'top', name: '白衬衫', color: '白色', tags: '商务', wear_count: 2, last_worn_on: '2026-10-01' },
    { id: 2, category: 'top', name: '黑T', color: '黑色', wear_count: 0, last_worn_on: null },
    { id: 3, category: 'bottom', name: '黑裤', color: '黑色', wear_count: 0, last_worn_on: null },
  ]
  assert.equal(filterWardrobeItems(items, { category: 'top' }).length, 2)
  assert.equal(filterWardrobeItems(items, { color: '黑色' }).length, 2)
  assert.equal(filterWardrobeItems(items, { q: '白衬衫' }).length, 1)
  assert.equal(filterWardrobeItems(items, { q: '商务' }).length, 1)
  assert.equal(filterWardrobeItems(items, { onlyNoHistory: true }).length, 2)
  assert.equal(filterWardrobeItems(items, { category: 'top', onlyNoHistory: true }).length, 1)
})

test('collectColors 去重并排序', () => {
  const colors = collectColors([{ color: '黑色' }, { color: '白色' }, { color: '黑色' }, { color: null }])
  assert.deepEqual(colors.sort(), ['黑色', '白色'].sort())
})

test('文案：暂无穿着记录 / 撤销合并警告', () => {
  assert.equal(getEmptyWearText(), '暂无穿着记录')
  assert.ok(getUnmergeWarning().includes('不会自动拆回'))
})

test('assertNewItemState 新建衣物 wear_count=0 且无日期', () => {
  assert.equal(assertNewItemState({ wear_count: 0, first_worn_on: null, last_worn_on: null }), true)
  assert.equal(assertNewItemState({ wear_count: 1, first_worn_on: null, last_worn_on: null }), false)
})

test('nextActions 生成后续链接并保留 person=all', () => {
  const a = nextActions(5, 2)
  assert.ok(a.outfit.includes('/wardrobe/new'))
  assert.ok(a.outfit.includes('item=5'))
  assert.ok(a.edit.includes('/wardrobe/items/5/edit'))
  const b = nextActions(5, null, 'all')
  assert.ok(b.wardrobe.includes('person=all'))
  assert.ok(b.outfit.includes('person=all'))
})

// ---- 新增：幂等键与快照、稳定文件键、提交管理器行为 ----

test('generateIdempotencyKey 唯一且 <=128', () => {
  const a = generateIdempotencyKey()
  const b = generateIdempotencyKey()
  assert.ok(a && typeof a === 'string' && a.length > 8)
  assert.ok(a.length <= 128)
  assert.notEqual(a, b)
})

test('snapshotPayload 深拷贝不可变', () => {
  const orig = { person_id: 1, name: 'a', nested: { x: 1 } }
  const snap = snapshotPayload(orig)
  orig.nested.x = 99
  orig.name = 'b'
  assert.equal(snap.nested.x, 1)
  assert.equal(snap.name, 'a')
})

test('ensureFileStableKeys 为每文件捕获一次 UUID，与 index/name 无关且 <=128', () => {
  const f1 = { name: 'a.jpg' }
  const f2 = { name: 'a.jpg' }
  ensureFileStableKeys([f1, f2])
  assert.ok(f1._wardrobeFileKey)
  assert.ok(f2._wardrobeFileKey)
  assert.ok(f1._wardrobeFileKey.length <= 128)
  assert.notEqual(f1._wardrobeFileKey, f2._wardrobeFileKey, '同名不同文件应不同键')
  const k1 = f1._wardrobeFileKey
  // 再次调用不改变键
  ensureFileStableKeys([f1])
  assert.equal(f1._wardrobeFileKey, k1)
  // 改名不影响已捕获键
  f1.name = 'renamed.jpg'
  ensureFileStableKeys([f1])
  assert.equal(f1._wardrobeFileKey, k1)
  // index 变化也不影响（模拟重排序）
  const f3 = { _wardrobeFileKey: k1, name: 'a.jpg' }
  assert.equal(getFileStableKey(f3), k1)
})

test('ensureFileStableKeys 处理 vant fileList 结构', () => {
  const inner = { name: 'photo.jpg' }
  const wrapper = { file: inner, url: 'blob:...' }
  ensureFileStableKeys([wrapper])
  assert.ok(wrapper._wardrobeFileKey)
  assert.ok(inner._wardrobeFileKey)
  assert.equal(wrapper._wardrobeFileKey, inner._wardrobeFileKey)
})

test('createWardrobeSubmitManager 快照锁与稳定键跨响应丢失', () => {
  const m = createWardrobeSubmitManager()
  const payload = { person_id: 1, name: '黑裤', category: 'bottom', color: '黑' }
  const files = [{ name: 'a.jpg' }, { name: 'b.jpg' }]
  const { payload: snap1, key: key1 } = m.ensureSnapshot(payload, files)
  // 原 payload 改动不应影响快照
  payload.name = '白裤'
  files[0].name = 'changed.jpg'
  const { payload: snap2, key: key2 } = m.ensureSnapshot(payload, files)
  assert.equal(snap2.name, '黑裤', '快照不可变')
  assert.equal(key1, key2, '稳定键复用')
  assert.equal(m.hasSnapshot(), true)
  // 文件键稳定
  const kA = getFileStableKey(files[0])
  assert.ok(kA)
  assert.equal(kA, files[0]._wardrobeFileKey)
  // 标记不确定后不丢弃
  m.markUncertain()
  assert.equal(m.uncertain, true)
  assert.equal(m.key, key1)
  assert.equal(m.snapshot.name, '黑裤')
  // 标记创建后保留
  m.markCreated({ id: 123, name: '黑裤' })
  assert.equal(m.createdItem.id, 123)
  assert.equal(m.uncertain, false)
  // 显式新草稿才清
  m.clearForNewDraft()
  assert.equal(m.hasSnapshot(), false)
  assert.equal(m.createdItem, null)
  // 新快照应新键
  payload.name = '新裤'
  const { key: key3 } = m.ensureSnapshot(payload, [])
  assert.notEqual(key1, key3)
})

test('createWardrobeSubmitManager 409 改名需新快照', () => {
  const m = createWardrobeSubmitManager()
  const p1 = { person_id: 1, name: '同名', category: 'top' }
  m.ensureSnapshot(p1, [])
  const k1 = m.key
  // 模拟 409 后清快照
  m.clearForNewDraft()
  const p2 = { person_id: 1, name: '改名后', category: 'top' }
  const { key: k2 } = m.ensureSnapshot(p2, [])
  assert.notEqual(k1, k2)
})

test('uploadWardrobePhotos 按稳定键逐个上传，失败保留同键重试', async () => {
  const uploaded = []
  const fakeApi = {
    uploadMedia: async (file, opts) => {
      uploaded.push([file.name, opts.idempotency_key])
      if (file.name === 'fail.jpg') throw new Error('network')
    },
  }
  const files = [{ name: 'a.jpg' }, { name: 'fail.jpg' }, { name: 'b.jpg' }]
  ensureFileStableKeys(files)
  const keysBefore = files.map((f) => getFileStableKey(f))
  const res = await uploadWardrobePhotos(fakeApi, files, { person_id: 1, wardrobe_item_id: 10, captured_on: '2026-10-12' })
  assert.equal(res.ok.length, 2)
  assert.equal(res.failed.length, 1)
  assert.equal(res.failed[0].name, 'fail.jpg')
  // 键稳定且与 index 无关
  assert.equal(getFileStableKey(files[1]), keysBefore[1])
  // 仅重试失败项，同键
  const failKey = keysBefore[1]
  const fakeApi2 = {
    uploadMedia: async (file, opts) => {
      assert.equal(opts.idempotency_key, failKey)
      assert.equal(opts.wardrobe_item_id, 10, 'edit/重试应挂同一 itemId')
    },
  }
  const retryRes = await uploadWardrobePhotos(fakeApi2, res.failed, { person_id: 1, wardrobe_item_id: 10, captured_on: '2026-10-12' })
  assert.equal(retryRes.failed.length, 0)
})

test('uploadWardrobePhotos 编辑态同 itemId 且独立键', async () => {
  const files = [{ name: 'x.jpg' }, { name: 'y.jpg' }]
  ensureFileStableKeys(files)
  const k1 = getFileStableKey(files[0])
  const k2 = getFileStableKey(files[1])
  assert.notEqual(k1, k2)
  // 模拟编辑：同 itemId 重试失败项仍同键
  const fakeApi = {
    uploadMedia: async (file, opts) => {
      if (file.name === 'x.jpg') throw new Error('fail')
      assert.ok(opts.idempotency_key === k2)
    },
  }
  const res = await uploadWardrobePhotos(fakeApi, files, { person_id: 5, wardrobe_item_id: 99, captured_on: '2026-10-12' })
  assert.equal(res.failed[0].name, 'x.jpg')
  assert.equal(getFileStableKey(res.failed[0]), k1)
})

test('scopeQueryPreserveAll 保留 person=all', () => {
  assert.deepEqual(scopeQueryPreserveAll(null, 'all'), { person: 'all' })
  assert.deepEqual(scopeQueryPreserveAll(5, 'all'), { person: 'all' })
  assert.deepEqual(scopeQueryPreserveAll(5, '5'), { person: 5 })
  assert.deepEqual(scopeQueryPreserveAll(null, null), {})
  assert.deepEqual(scopeQueryPreserveAll(null, undefined), {})
})

test('WardrobeItemForm 限制五张且字段集禁用', () => {
  const form = src('src/components/WardrobeItemForm.vue')
  assert.match(form, /:max-count="5"/)
  assert.match(form, /fieldset :disabled="isLocked"/)
  assert.match(form, /ensureFileStableKeys/)
  assert.match(form, /:disabled="isLocked"/)
})

test('WardrobeItemEditor 接通同键重试、编辑照片和离开守卫', () => {
  const ed = src('src/views/WardrobeItemEditor.vue').replace(/\/\/[^\n]*/g,'')
  assert.match(ed, /api\.createWardrobeItem\(p,submissionKey\.value\)/)
  assert.match(ed, /snapshotPayload/)
  assert.match(ed, /uploadWardrobePhotos\(api,files,uploadContext\)/)
  assert.match(ed, /uploadContext\.wardrobe_item_id=createdItem\.value\.id/)
  assert.match(ed, /onBeforeRouteLeave\(confirmLeave\)/)
  assert.match(ed, /onBeforeRouteUpdate/)
  assert.match(ed, /scopeQueryPreserveAll/)
  assert.match(ed, /failedFiles\.value=result\.failed/)
  assert.match(ed, /重试保存/)
})

test('Wardrobe.vue 保留 all 并带 scopeQuery', () => {
  const w = src('src/views/Wardrobe.vue')
  assert.match(w, /navQuery/)
  assert.match(w, /person.*all/)
  assert.match(w, /scopeQuery\(effectivePersonId/)
})
