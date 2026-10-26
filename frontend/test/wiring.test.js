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
test('衣橱状态：改状态入口、状态筛选、加入时间与替代关系都接上（active 不再是写入口）', () => {
  const wardrobe = code('src/views/Wardrobe.vue')
  for(const pattern of [/改状态/, /statusScope/, /filterByStatusScope/, /include_offhand: true/, /formatAdded/, /status_history/, /replaced_by/, /buildStatusPatch/]) assert.match(wardrobe, pattern)
  assert.ok(!/patchWardrobeItem\([^)]*active/.test(wardrobe), '不能再拿 active 当写入口')
  const form = code('src/components/WardrobeItemForm.vue')
  assert.match(form, /替代了/); assert.match(form, /replaces_item_id/); assert.match(form, /replaceOptions/)
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
test('相处跨日：开关+结束日期串到草稿与 payload，编辑优先用事件自带的 meeting', () => {
  const fields = code('src/components/records/EventFields.vue')
  // 结束日期是独立 prop/emit，别直接改 draft（父级才是唯一真源）
  assert.match(fields, /endedOn: \{ type: String, default: '' \}/)
  assert.match(fields, /'update:endedOn'/)
  for(const pattern of [/跨天/, /结束日期/, /toggleSpan/, /spanInfo/, /spanError/]) assert.match(fields, pattern)
  const composer = code('src/components/records/RecordComposer.vue')
  for(const pattern of [/ended-on="draft\.endedOn"/, /@update:ended-on="draft\.endedOn=\$event"/, /event-date="draft\.eventDate"/, /spanError\(draft\.eventDate,draft\.endedOn\)/]) assert.match(composer, pattern)
  const timeline = code('src/views/Timeline.vue')
  // 老兜底（拉全量 interactions 按 event_id 猜）只能留在 else 分支里
  assert.match(timeline, /const m=e\.meeting/)
  assert.ok(timeline.indexOf('const m=e.meeting') < timeline.indexOf('api.interactions(e.person_id)'))
  assert.match(code('src/lib/record-submit.js'), /ended_on:endedOn/)
})

// ---------------------------------------------------------------- 慢链路往返（2026-10 手机加载优化）
test('首页首屏：今天卡片/待办与 config/persons 同一波并发（不再串行等待）', () => {
  const dash = src('src/views/Dashboard.vue')
  assert.match(dash, /const first = load\(\)\.catch\(\(\) => showToast\('加载失败，请重试'\)\)/)
  assert.match(dash, /await Promise\.all\(\[first, store\.ensureLoaded\(\)\]\)/)
  // ★ 别再出现「先 await ensureLoaded() 再 load()」：新版 loadPersons 不自动挑人，
  //   串行只会白等一个往返（实测 1.2–2.4s）
  assert.ok(
    !/await store\.ensureLoaded\(\)\s*\n\s*await load\(\)/.test(dash),
    '首页首屏的两个数据源必须并发'
  )
})

test('保存纯文字后不再回源拿「刚记的」，只有带图才回源', () => {
  const rc = src('src/components/records/RecordComposer.vue')
  assert.match(rc, /const hadFiles=\(draft\.fileTasks\|\|\[\]\)\.length>0/)
  assert.match(rc, /if\(hadFiles\) await loadRecent\(\)/)
  assert.match(rc, /else recent\.value=mergeRecent\(recent\.value,result\.record\)/)
  assert.match(rc, /import \{mergeRecent\} from '\.\.\/\.\.\/lib\/recent\.js'/)
  // ★ 别再出现「保存成功后无条件 await loadRecent()」：那是白等一个往返
  assert.ok(
    !/emit\('saved',result\.record\)\s*\n\s*await loadRecent\(\)/.test(rc),
    '保存后不应无条件回源（纯文字用返回体插入即可；有图才回源）'
  )
})

test('chunk 预取延后到 load 之后并限并发（别和首屏抢连接）', () => {
  const main = src('src/main.js')
  assert.match(main, /window\.addEventListener\('load', run, \{ once: true \}\)/)
  assert.match(main, /setTimeout\(\(\) => prefetchViews\(\), 3000\)/)
  assert.ok(!/idle\(\(\) => prefetchViews\(\)\)/.test(main), '挂载后立刻预取会拖慢首屏')

  const router = src('src/router.js')
  assert.match(router, /export function prefetchViews\(concurrency = 2\)/)
  assert.match(router, /queue\.shift\(\)/)
  assert.ok(
    !/Object\.values\(views\)\.map\(\(load\) => load\(\)\)/.test(router),
    '13 个 chunk 一次性并发会挤占首屏'
  )
})

test('首页 Dashboard 静态引入（不额外付一趟 chunk 往返）', () => {
  const router = src('src/router.js')
  assert.match(router, /import Dashboard from '\.\/views\/Dashboard\.vue'/)
  assert.match(router, /dashboard: \(\) => Promise\.resolve\(Dashboard\)/)
  assert.ok(
    !/dashboard: \(\) => import\('\.\/views\/Dashboard\.vue'\)/.test(router),
    '首页懒加载会让首屏多等一整趟往返'
  )
})
