import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = (rel) => readFileSync(join(here, '..', rel), 'utf8')

// ---------------------------------------------------------------- router
const router = src('src/router.js')

test('router 保留全部既有 URL（不删不改）', () => {
  for (const p of [
    "'/'",
    "'/new'",
    "'/timeline'",
    "'/wardrobe'",
    "'/relations'",
    "'/gallery'",
    "'/person/:id'",
    "'/cycle'",
    "'/todos'",
    "'/search'",
    "'/settings'",
  ]) {
    assert.ok(router.includes(`path: ${p}`), `缺失路由 ${p}`)
  }
})

test('router 新增 /people 且录入路由隐藏底部 tabbar', () => {
  assert.ok(router.includes("path: '/people'"))
  assert.ok(/path: '\/new'[\s\S]*hideTabbar: true/.test(router), '/new 应 hideTabbar')
  assert.ok(/path: '\/person\/:id'[\s\S]*back: true/.test(router), '个人页应有返回')
})

test('router 分段分组只挂在既有页面上，范围页标记 scoped', () => {
  assert.ok(/group: 'timeline'/.test(router))
  assert.ok(/group: 'people'/.test(router))
  // 只读范围指示器依据：时间轴/相册/衣橱/待办/个人页/生理期
  for (const name of ['timeline', 'wardrobe', 'gallery', 'todos', 'person', 'cycle']) {
    assert.ok(router.includes(`name: '${name}'`) && /scoped: true/.test(router), `${name} 应 scoped`)
  }
})

// ---------------------------------------------------------------- App shell
const app = src('src/App.vue')

test('App 使用 4 tab 常量、渲染分组分段与固定「＋记录」', () => {
  assert.match(app, /from '\.\/lib\/nav'/)
  assert.match(app, /v-for="t in TABS"/)
  assert.match(app, /class="segtab"/)
  assert.match(app, /class="fab"/)
  assert.match(app, /router-view/)
})

test('App 底部 tab 用图标 + 文字标签（不是纯文字）', () => {
  assert.match(app, /van-icon :name="t\.icon"/)
  assert.match(app, /class="tab-label"/)
  assert.match(app, /t\.label/)
})

test('App 录入路由与「正在编辑」时隐藏 tabbar 与「＋记录」', () => {
  assert.match(
    app,
    /showTabbar = computed\(\(\) => !route\.meta\?\.hideTabbar && !store\.editingRecord\)/
  )
  assert.match(app, /showFab = computed\(\(\) => route\.name !== 'new' && !store\.editingRecord\)/)
})

test('App 含全局搜索入口与首页设置齿轮', () => {
  assert.match(app, /name="search"/)
  assert.match(app, /name="setting-o"/)
  assert.match(app, /router\.push\('\/search'\)/)
})

test('App 只读范围指示器：按 ?person / 路由参数显示，不改全局', () => {
  assert.match(app, /routeScopePersonId/)
  assert.match(app, /class="scope-tag"/)
  // 指示器只读：不调用 setCurrentPerson
  assert.ok(!app.includes('setCurrentPerson'), 'App 不应写回全局 scope')
})

test('App 分段链接与「＋记录」带上当前范围的人', () => {
  assert.match(app, /segTarget\(s\)/)
  assert.match(app, /scopeQuery\(effectiveScopeId\.value\)/)
  assert.match(app, /segTarget/)
})

test('App 衣橱入口按服装模块门控（未知不隐藏）', () => {
  assert.match(app, /anyOutfitEnabled/)
  assert.match(app, /hasModule\(id, 'outfit'\)/)
})

test('App 布局：全局 border-box、topbar 固定高度、icon 触控 ≥44px、fab 底部留白', () => {
  assert.match(app, /box-sizing: border-box/)
  assert.match(app, /--topbar-h: 44px/)
  assert.match(app, /top: calc\(var\(--safe-top\) \+ var\(--topbar-h\)\)/) // 分段条精确偏移
  assert.match(app, /min-width: 44px/)
  assert.match(app, /min-height: 44px/)
  assert.match(app, /\.page\.has-tabbar/)
})

// ---------------------------------------------------------------- store
const store = src('src/store.js')

test('store 提供惰性模块开关 + 正在编辑共享态', () => {
  assert.match(store, /loadModulesFor/)
  assert.match(store, /hasModule/)
  assert.match(store, /editingRecord: false/)
  assert.match(store, /setEditingRecord/)
})

// ---------------------------------------------------------------- Settings
const settings = src('src/views/SettingsView.vue')

test('设置页不再承载人物管理/添加人物（已迁到 /people）', () => {
  assert.ok(!settings.includes('添加一个人'), '不应再有「添加一个人」卡片')
  assert.ok(!settings.includes('如：妈妈 / 阿明'), '不应再有添加人物表单')
  assert.ok(!settings.includes('createPerson'), '不应再直接建人')
  assert.ok(settings.includes('to="/people"'), '应提供去人物页入口')
})

test('设置页保留 隐私/关于/退出/收起诊断', () => {
  assert.ok(settings.includes('隐私模式'))
  assert.ok(settings.includes('关于'))
  assert.ok(settings.includes('退出登录'))
  assert.match(settings, /diagOpen = ref\(false\)/)
})

// ---------------------------------------------------------------- PeopleView
const people = src('src/views/PeopleView.vue')

test('PeopleView：添加入口是显式按钮，表单默认收起（非永久表单）', () => {
  assert.match(people, /showAdd = ref\(false\)/)
  assert.match(people, /v-if="showAdd"/)
  assert.match(people, /＋ 添加人物/)
})

test('PeopleView：列表里不再直接删除（删除只在个人管理）', () => {
  assert.ok(!people.includes('deletePerson'), '列表流程不应直接删人')
  assert.ok(!people.includes('removePerson'), '不应有列表内删除函数')
})

test('PeopleView：移除误导的「同一人多圈」说明，空状态指向按钮', () => {
  assert.ok(!people.includes('同一个人可以同时在多个圈里'), '应移除误导文案')
  assert.match(people, /还没有人，点上面的「＋ 添加人物」/)
})

// ---------------------------------------------------------------- PersonView
const person = src('src/views/PersonView.vue')

test('PersonView 修复 pred 解构遮蔽 ref 的运行时 bug', () => {
  assert.match(person, /const pred = ref\(/) // 仍有 ref
  assert.match(person, /predData/) // 解构改用 predData
  // 解构列表中不得出现裸 pred（回归守护）
  assert.ok(!/\[\s*[^\]]*\bpred\b\s*,\s*\w+\s*\]\s*=\s*await/.test(person), '解构里不该有 pred 变量')
  // 生理期显示条件：已启用 **且** 当前性别允许（男性页面不再显示生理期卡片）
  assert.match(person, /pred\.value = cycleUsable\.value \? predData : null/)
  assert.match(person, /const cycleUsable = computed\(/, 'cycleUsable 必须是计算属性')
})

test('PersonView 用 ?person 作用域链接，管理面板默认收起，可删除', () => {
  assert.match(person, /scopeQuery/)
  assert.match(person, /mgmtOpen = ref\(false\)/)
  assert.match(person, /deletePerson/)
})

test('PersonView 在管理之外有只读关系摘要，并带「管理」动作', () => {
  assert.match(person, /openManagement/)
  assert.match(person, /@click="openManagement\(\)"/)
  assert.match(person, /关系/)
})

test('PersonView 属性新增有分类选择 + 添加按钮（此前无入口）', () => {
  assert.match(person, /v-model="pickedCategory"/)
  assert.match(person, /@click="addAttr"/)
  assert.match(person, /function addAttr/)
})

test('PersonView 内容顺序：属性/生理期排在最近记录之前', () => {
  const iAttr = person.indexOf('属性')
  const iRecent = person.indexOf('最近记录')
  assert.ok(iAttr >= 0 && iRecent >= 0, '两个区块都应存在')
  assert.ok(iAttr < iRecent, '属性应排在最近记录之前')
})

test('PersonView 衣橱快捷入口按服装模块门控', () => {
  assert.match(person, /enabledModules\.includes\('outfit'\)/)
})

// ---------------------------------------------------------------- 性别 / 生日显性化
// 背景：首页只显示「约 24 天后」（生理期预测）而生日在 28 天后 → 被误读。
// 这两条规则必须一直有人守：① 生日必须给明确写法；② 生理期必须按性别门控。

test('生日显示统一走 lib/birthday（不是各页面自己拼天数）', () => {
  for (const f of ['src/views/Dashboard.vue', 'src/views/PersonView.vue', 'src/views/PeopleView.vue']) {
    const s = src(f)
    assert.match(s, /from '\.\.\/lib\/birthday'/, `${f} 应引用 lib/birthday`)
    assert.match(s, /birthdayLine\(/, `${f} 应使用 birthdayLine`)
  }
})

test('Dashboard 的生理期标签带语义（不再是无标签的「约 N 天后」）', () => {
  const dash = src('src/views/Dashboard.vue')
  assert.match(dash, /生理期 · 约 \{\{ p\.cycle\.next_in_days \}\} 天后/)
  assert.ok(!/约 \{\{ p\.cycle\.next_in_days \}\} 天后/.test(dash.replace('生理期 · 约', ''))
    || dash.includes('生理期 · 约'), '标签必须带「生理期」前缀')
})

test('性别字段贯通：store 有 genderLabel，页面有性别编辑/新建入口', () => {
  assert.match(store, /genderLabel/)
  assert.match(person, /form\.gender/)
  assert.match(person, /v-model="form\.gender"/)
  assert.match(people, /v-model="form\.gender"/)
})

test('模块开关只列「该性别可用」的模块（男性看不到生理期开关）', () => {
  assert.match(person, /modulesAvailable/)
  assert.match(person, /blockedModules/)
  assert.match(person, /v-for="k in modulesAvailable"/)
  // 不能再直接用全局 config.modules 渲染开关列表（那会给男性显示生理期）
  assert.ok(!/v-for="k in allModules"/.test(person), '开关列表不应再读全局 allModules')
})

test('CycleView 展示易孕期参考（含免责话术，由后端给）', () => {
  const cycle = src('src/views/CycleView.vue')
  assert.match(cycle, /pred\.fertility/)
  assert.match(cycle, /pred\.fertility_note/)
})

// ---------------------------------------------------------------- Timeline / NewRecord / main.js
test('Timeline 内联编辑时置共享态，并在卸载时复位', () => {
  const tl = src('src/views/Timeline.vue')
  assert.match(tl, /store\.setEditingRecord\(v\)/)
  assert.match(tl, /onUnmounted\(\(\) => store\.setEditingRecord\(false\)\)/)
})

// 时间轴编辑面板的图片：后端上传接口一直支持带 event_id，缺的只是编辑面板里的入口
// （曾经编辑一条记录加不了图）。这几条守住：入口在、挂对归属、日期不串、能删。
test('Timeline 编辑面板可增删图片（挂 event_id、用事件日期、按媒体模块门控）', () => {
  const tl = src('src/views/Timeline.vue')
  assert.match(tl, /van-uploader v-model="fileList"/, '编辑面板要有图片选择器')
  assert.match(tl, /api\.uploadMedia\(raw, \{/, '要走既有上传接口')
  assert.match(tl, /event_id: f\.id/, '必须挂到这条记录上（否则时间轴不会显示）')
  // 拍摄日期用事件日期：用「今天」会把老照片排到相册最前面
  assert.match(tl, /captured_on: f\.event_date/)
  assert.match(tl, /api\.deleteMedia\(m\.id\)/, '已有图片要能在面板里删')
  assert.match(tl, /mediaVisible/, '按该人的「图片」模块门控')
  assert.match(tl, /hasModule\(Number\(form\.value\?\.person_id\), 'media'\)/)
  // 新图在「保存」时才上传（取消编辑不留半截数据）
  assert.match(tl, /const uploaded = await uploadPickedFiles\(f\)/)
})

test('NewRecord 认领 ?person（FAB 带过来的当前范围）', () => {
  assert.match(src('src/views/NewRecord.vue'), /normalizePersonId\(route\.query\.person\)/)
})

test('main.js 显式引入 icon 样式（顶栏图标）', () => {
  assert.match(src('src/main.js'), /import 'vant\/es\/icon\/style'/)
})

test('下游页（时间轴/相册/衣橱）读取 ?person 且不写回全局 scope', () => {
  for (const f of ['src/views/Timeline.vue', 'src/views/Gallery.vue', 'src/views/Wardrobe.vue']) {
    const s = src(f)
    assert.match(s, /resolveScopedPerson/, `${f} 应解析 ?person`)
    assert.ok(!s.includes('setCurrentPerson'), `${f} 不应写回全局 scope`)
  }
})

// ---------------------------------------------------------------- 服装：专有记录页（衣橱）
// 决策：服装不再混在通用「记录页」里 —— 它要查单品目录 + 写引用，语义跟「记一件事」不同，
// 而且今天就是这么漏掉单品的。但入口不能少：衣橱按钮 + 单品「再穿一次」+ 记录页的
// 「记穿搭」卡片，三条都指向 /wardrobe/new。
test('服装有专有记录页 /wardrobe/new（录入页隐藏 tabbar、返回落到衣橱）', () => {
  assert.ok(router.includes("path: '/wardrobe/new'"), '缺 /wardrobe/new 路由')
  assert.match(router, /path: '\/wardrobe\/new'[\s\S]*hideTabbar: true/)
  assert.match(router, /path: '\/wardrobe\/new'[\s\S]*backTo: '\/wardrobe'/)
})

test('记录页不再管服装：只留「记穿搭」入口，勾单品逻辑搬进共享组件', () => {
  const nr = src('src/views/NewRecord.vue')
  assert.ok(!nr.includes('wardrobeCategories'), '记录页不该再有单品勾选 UI')
  assert.ok(!nr.includes('createOutfit'), '记录页不该再直接建穿搭')
  assert.match(nr, /const outfitEnabled = computed/)
  assert.match(nr, /router\.push\(\{ path: '\/wardrobe\/new'/)
})

test('穿搭面板抽成 components/OutfitForm.vue：跨类别已选汇总 + 0 单品确认 + 预选', () => {
  const f = src('src/components/OutfitForm.vue')
  assert.match(f, /api\.createOutfit/)
  assert.match(f, /已选 \{\{ pickedAll \}\} 件/, '分组勾选必须有跨类别汇总行')
  assert.match(f, /这次没有勾单品/, '0 单品要二次确认（衣橱按单品聚合，不勾就白记）')
  assert.match(f, /preselect/)
})

test('衣橱有两个记录入口（记一次穿着 / 单品再穿一次），都带上当前范围的人', () => {
  const w = src('src/views/Wardrobe.vue')
  assert.match(w, /＋ 记一次穿着（今天）/)
  assert.match(w, /＋ 再穿一次（今天）/)
  assert.match(w, /function goRecord\(itemId\)/)
  assert.match(w, /scopeQuery\(effectivePersonId\.value\)/)
})

test('单品穿着历史带出那次穿搭的照片（不复制给每件单品）', () => {
  assert.match(src('src/views/Wardrobe.vue'), /w\.media/)
})

// 图片放大：三处（时间轴记录 / 衣橱单品详情 / 个人页服装图片）曾经是
// window.open(原图, '_blank')，手机上会把 SPA 丢到后台；衣橱单品详情甚至连点击都没接
// （照片点上去毫无反应）。现在统一页面内 van-image-preview。
test('点图放大走页面内预览：时间轴记录不再新开标签页', () => {
  const tl = src('src/views/Timeline.vue')
  assert.match(tl, /from '\.\.\/lib\/media-preview'/)
  assert.match(tl, /@click="openFull\(m, e\.media\)"/, '列表缩略图要带上这条记录的图片集合')
  assert.match(tl, /van-image-preview[\s\S]*:images="preview\.images"[\s\S]*:start-position="preview\.index"/)
  assert.match(tl, /@click="openFull\(m, form\.media\)"/, '编辑面板里的图同样要点得开')
  // window.open 只允许留给视频（没有页面内预览的东西）
  const opens = tl.match(/window\.open\(/g) || []
  assert.equal(opens.length, 1, '只应剩视频那一条 window.open')
  assert.match(tl, /if \(m && m\.kind === 'video'\) \{\s*window\.open/)
})

test('衣橱单品详情的照片/穿着照片可放大（此前点了没反应）', () => {
  const w = src('src/views/Wardrobe.vue')
  assert.match(w, /const detailPhotos = computed/, '预览集合 = 单品照片 + 各次穿着的照片')
  assert.match(w, /\(detail\.value\?\.wears \|\| \[\]\)\.flatMap\(\(w\) => w\.media \|\| \[\]\)/)
  assert.match(w, /v-if="m\.kind !== 'video'" :src="api\.mediaUrl\(m\)" @click="openFull\(m, detailPhotos\)"/)
  assert.match(w, /:src="api\.mediaUrl\(m\)" @click="openFull\(m, detailPhotos\)"/, '穿着历史里的图也要能放大')
  assert.match(w, /van-image-preview[\s\S]*:start-position="preview\.index"/)
  assert.ok(!/window\.open/.test(w), '衣橱不该再开新标签页（视频用 <a target=_blank>）')
})

test('个人页「服装 / 图片」同样页面内放大', () => {
  const p = src('src/views/PersonView.vue')
  assert.match(p, /@click="openFull\(m, photos\)"/)
  assert.match(p, /van-image-preview[\s\S]*:images="preview\.images"/)
})

test('专有记录页遵守下游页约定：读 ?person、不写回全局 scope', () => {
  const nw = src('src/views/WardrobeNew.vue')
  assert.match(nw, /normalizePersonId\(route\.query\.person\)/)
  assert.ok(!nw.includes('setCurrentPerson'), '不应写回全局 scope')
  assert.match(nw, /OutfitForm/)
  assert.match(nw, /hasModule\(personId\.value, 'outfit'\)/, '没开服装模块的人不给记')
})
