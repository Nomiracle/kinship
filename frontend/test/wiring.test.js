import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
const here = dirname(fileURLToPath(import.meta.url))
const src = rel => readFileSync(join(here, '..', rel), 'utf8')
// Comments cannot substitute for executable wiring. Behavioral tests supplement
// these structural checks; browser tests exercise the real render and requests.
const code = rel => src(rel).replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
const router = code('src/router.js'), app = code('src/App.vue'), store = code('src/store.js')
const people = code('src/views/PeopleView.vue'), person = code('src/views/PersonView.vue'), settings = code('src/views/SettingsView.vue')

test('既有 URL 和独立衣物路由保留，录入隐藏导航', () => {
  for(const path of ['/', '/new', '/timeline', '/wardrobe', '/wardrobe/new', '/wardrobe/items/new', '/wardrobe/items/:id/edit', '/gallery', '/people', '/person/:id', '/relations', '/cycle', '/todos', '/search', '/settings']) assert.ok(router.includes(`path: '${path}'`), path)
  for(const path of ['/new', '/wardrobe/new', '/wardrobe/items/new', '/wardrobe/items/:id/edit']) {
    const line = router.split('\n').find(l => l.includes(`path: '${path}'`))
    assert.match(line, /hideTabbar: true/); assert.match(line, /back: true/)
  }
  assert.match(router, /name: 'wardrobe'.*title: '衣橱'.*tab: 'wardrobe'/)
})
test('四主导航、二级导航和新增实体选择器', () => {
  for(const pattern of [/v-for="t in TABS"/, /van-icon :name="t.icon"/, /class="tab-label"/, /class="segtab"/, /router-view/, /＋ 新增/]) assert.match(app, pattern)
  for(const label of ['记一件事','记穿搭','添加衣物','添加人物']) assert.ok(app.includes(`label: '${label}'`))
})
test('录入与弹窗编辑隐藏导航，保存区域保留安全区', () => {
  for(const key of ['showTabbar','showFab']) assert.match(app, new RegExp(`${key} = computed\\(\\(\\) => !route\\.meta\\?\\.hideTabbar && !store\\.editingRecord\\)`))
  for(const pattern of [/safe-bottom/, /\.page:not\(\.has-tabbar\)/, /min-width:44px/, /min-height:44px/, /@media\(min-width:1000px\)/]) assert.match(app, pattern)
})
test('人物范围本页切换与显式默认保存分开', () => {
  assert.match(app, /aria-label="本页人物范围"/); assert.match(app, /resolveScopedPerson/)
  const body = app.slice(app.indexOf('function changeScope'), app.indexOf('function setDefaultScope'))
  assert.match(body, /router\.replace/); assert.ok(!body.includes('setCurrentPerson'))
  assert.match(app, /function setDefaultScope\(\)[\s\S]*store\.setCurrentPerson/)
  assert.match(app, /name="search"/); assert.match(app, /name="setting-o"/)
})
test('store 不猜首人物，模块、隐私和编辑共享态保留', () => {
  for(const name of ['loadModulesFor','hasModule','setEditingRecord','genderLabel','setPrivacyMode']) assert.ok(store.includes(name))
  assert.ok(!store.includes('favourite'))
})
test('设置页保留隐私、关于、退出及折叠诊断', () => {
  for(const label of ['隐私模式','关于','退出登录']) assert.ok(settings.includes(label))
  assert.match(settings, /diagOpen = ref\(false\)/); assert.ok(!settings.includes('createPerson')); assert.ok(settings.includes('to="/people"'))
})
test('人物添加默认折叠、支持新增深链，删除仅管理页', () => {
  assert.match(people, /showAdd = ref\(false\)/); assert.match(people, /v-if="showAdd"/); assert.match(people, /route\.query\.add === '1'/)
  assert.ok(!people.includes('deletePerson')); assert.ok(!people.includes('同一个人可以同时在多个圈里'))
  assert.match(people, /还没有人，点上面的「＋ 添加人物」/)
})
test('PersonView 不遮蔽 pred，模块开关和管理保留', () => {
  assert.match(person, /const pred = ref\(/); assert.match(person, /predData/); assert.match(person, /pred\.value = cycleUsable\.value \? predData : null/)
  for(const name of ['scopeQuery','mgmtOpen = ref(false)','deletePerson','openManagement','addAttr','modulesAvailable','blockedModules']) assert.ok(person.includes(name))
  assert.ok(person.indexOf('属性') < person.indexOf('最近记录')); assert.match(person, /enabledModules\.includes\('outfit'\)/)
  assert.match(person, /v-model="pickedCategory"/)
})
test('生日、性别及生理期参考语义保持', () => {
  for(const file of ['Dashboard.vue','PersonView.vue','PeopleView.vue']) assert.match(code(`src/views/${file}`), /birthdayLine\(/)
  assert.match(code('src/views/Dashboard.vue'), /生理期 · 约 \{\{ p\.cycle\.next_in_days \}\} 天后/)
  assert.match(person, /v-model="form\.gender"/); assert.match(people, /v-model="form\.gender"/)
  assert.match(code('src/views/CycleView.vue'), /pred\.fertility_note/)
})
test('记录和旧穿搭路由只包装统一 Composer', () => {
  for(const file of ['NewRecord.vue','WardrobeNew.vue']) {
    const text = code(`src/views/${file}`); assert.match(text, /<RecordComposer/)
    assert.ok(!/api\.(createEvent|createOutfit|uploadMedia)/.test(text))
  }
  assert.match(code('src/views/WardrobeNew.vue'), /initial-type="outfit"/)
})
test('Timeline 用 Composer 编辑并保留按日分组、搜索、预览与编辑态', () => {
  const tl = code('src/views/Timeline.vue')
  for(const pattern of [/<RecordComposer/, /<EventDayList/, /group: 'day'/, /loadMore/, /setEditingRecord/, /onUnmounted/, /previewUrls/]) assert.match(tl, pattern)
  assert.ok(!/api\.(createEvent|createOutfit|patchEvent|uploadMedia)/.test(tl))
})
test('共享 Composer 日期与可选时间分开，表单与附件分层', () => {
  const composer = code('src/components/records/RecordComposer.vue')
  assert.match(composer, /type="date"/); assert.match(composer, /type="time"/); assert.ok(!composer.includes('datetime-local'))
  for(const name of ['EventFields','OutfitFields','RecordAttachments','OutfitForm']) assert.ok(composer.includes(`<${name}`))
  assert.ok(!composer.includes('store.setCurrentPerson')); assert.ok(!composer.includes('store.others[0]'))
})
test('OutfitForm 仅选择草稿，没有第二套落库实现', () => {
  const picker = code('src/components/OutfitForm.vue')
  assert.ok(!/api\.(createOutfit|createWardrobeItem|createEvent|uploadMedia)/.test(picker))
  assert.match(picker, /emit\('confirm'/); assert.match(picker, /emit\('cancel'/); assert.match(picker, /preselect|initial/)
})
test('衣橱添加与穿搭入口分开，范围不写默认且保留图片预览', () => {
  const wardrobe = code('src/views/Wardrobe.vue')
  for(const pattern of [/添加衣物/, /wardrobe\/items\/new/, /wardrobe\/new/, /暂无穿着记录/, /resolveScopedPerson/, /van-image-preview/]) assert.match(wardrobe, pattern)
  assert.ok(!wardrobe.includes('setCurrentPerson'))
})
test('日卡继续复用、默认折叠，发生与录入时间分别显示', () => {
  const days = code('src/components/EventDayList.vue')
  for(const pattern of [/const open = ref\(\[\]\)/, /toggleAll/, /dayThumbs\(d, 2\)/, /录入/, /发生/, /original\(e\)/]) assert.match(days, pattern)
  assert.match(person, /<EventDayList/); assert.match(person, /:editable="false"/)
})
test('设计 token 与必要 Vant 图标样式显式引入', () => {
  const main = code('src/main.js')
  assert.match(main, /import 'vant\/es\/icon\/style'/); assert.match(main, /import '.\/styles\/tokens.css'/)
  assert.match(src('src/styles/tokens.css'), /--accent:/)
})
