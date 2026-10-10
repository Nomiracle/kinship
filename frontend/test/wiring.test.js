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
