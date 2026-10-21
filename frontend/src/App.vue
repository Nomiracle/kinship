<template>
  <div v-if="!authed" class="login">
    <div class="login-box">
      <h1>{{ title }}</h1>
      <p class="hint">输入页面口令，进入你的私人档案</p>
      <van-field v-model="tokenInput" type="password" label="口令" placeholder="页面口令" @keyup.enter="doLogin" />
      <van-button block type="primary" style="margin-top:12px" @click="doLogin">进入</van-button>
      <p v-if="loginError" class="err" role="alert">{{ loginError }}</p>
    </div>
  </div>
  <div v-else class="app">
    <header class="topbar">
      <div class="bar">
        <button v-if="showBack" class="iconbtn" aria-label="返回" @click="goBack"><van-icon name="arrow-left" /></button>
        <span class="title">{{ headerTitle }}</span>
        <div v-if="showScope" class="scope-tag">
          <select aria-label="本页人物范围" :value="effectiveScopeId || 'all'" @change="changeScope">
            <option value="all">全部人物</option>
            <option v-for="p in store.persons" :key="p.id" :value="p.id">{{ store.displayName(p) }}</option>
          </select>
          <button class="default-scope" @click="setDefaultScope" aria-label="将本页人物范围设为默认">设为默认</button>
        </div>
        <span class="actions">
          <button v-if="showSearch" class="iconbtn" aria-label="搜索" @click="router.push('/search')"><van-icon name="search" /></button>
          <button v-if="showGear" class="iconbtn" aria-label="设置" @click="router.push('/settings')"><van-icon name="setting-o" /></button>
        </span>
      </div>
    </header>
    <nav v-if="segments" class="subnav" aria-label="分组导航">
      <div class="bar segs">
        <router-link v-for="s in segments" :key="s.key" :to="segTarget(s)" class="segtab" :class="{ active: s.key === segKey }">{{ s.label }}</router-link>
      </div>
    </nav>
    <main class="page" :class="{ 'has-tabbar': showTabbar }"><div class="container"><router-view /></div></main>
    <button v-if="showFab" class="fab" @click="showCreate = true">＋ 新增</button>
    <van-popup v-model:show="showCreate" position="bottom" round safe-area-inset-bottom>
      <section class="create-menu" aria-label="新增">
        <h2>新增</h2>
        <button v-for="c in createActions" :key="c.to" @click="create(c)"><van-icon :name="c.icon" /> {{ c.label }} <span>{{ c.hint }}</span></button>
        <van-button block plain @click="showCreate = false">取消</van-button>
      </section>
    </van-popup>
    <nav v-if="showTabbar" class="tabbar" aria-label="主导航">
      <div class="bar tabs"><router-link v-for="t in TABS" :key="t.key" :to="tabTarget(t)" class="tab" :class="{ active: t.key === tabKey }"><van-icon :name="t.icon" /><span class="tab-label">{{ t.label }}</span></router-link></div>
    </nav>
  </div>
</template>

<script setup>
import { computed, watch, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { getToken, setToken } from './api'
import { useArchiveStore } from './store'
import { TABS, activeTabKey, activeSegmentKey, segmentsForRoute } from './lib/nav'
import { normalizePersonId, scopeQuery, resolveScopedPerson } from './lib/scope'

const store = useArchiveStore()
const route = useRoute()
const router = useRouter()
const authed = ref(!!getToken())
const tokenInput = ref('')
const loginError = ref('')
const title = ref('Kinship Archive')
const showCreate = ref(false)
const headerTitle = computed(() => route.meta?.title || title.value)
const showBack = computed(() => !!route.meta?.back)
const showSearch = computed(() => route.name !== 'search')
const showGear = computed(() => route.name === 'dashboard')
const showTabbar = computed(() => !route.meta?.hideTabbar && !store.editingRecord)
const showFab = computed(() => !route.meta?.hideTabbar && !store.editingRecord)
const tabKey = computed(() => activeTabKey(route))
const segKey = computed(() => activeSegmentKey(route))
const segments = computed(() => segmentsForRoute(route))
const effectiveScopeId = computed(() => route.name === 'person' ? normalizePersonId(route.params.id) : resolveScopedPerson(route.query.person, store.currentPersonId))
// 创建页由表单选择归属，人物详情由路径确定，不再提供会产生歧义的外层选择器。
const showScope = computed(() => !!route.meta?.scoped && !route.meta?.hideTabbar && route.name !== 'person')
const pageScopes = new Map()
watch(() => [route.path, route.query.person], () => {
  if (route.meta?.scoped) pageScopes.set(route.path, route.query.person === undefined ? effectiveScopeId.value || 'all' : route.query.person)
}, { immediate: true })
function changeScope(event) {
  router.replace({ path: route.path, query: { ...route.query, person: event.target.value } })
}
function setDefaultScope() {
  store.setCurrentPerson(effectiveScopeId.value)
  showToast('已设为默认；其他页面的已选范围不变')
}
function tabTarget(t) {
  const person = pageScopes.get(t.to)
  return { path: t.to, query: person === undefined ? {} : { person } }
}
function segTarget(s) {
  // 二级视图属于同一记录浏览范围，保留显式全部，避免默认人物覆盖。
  return { path: s.to, query: effectiveScopeId.value ? scopeQuery(effectiveScopeId.value) : { person: 'all' } }
}
const createActions = [
  { to: '/new', label: '记一件事', icon: 'edit', hint: '日期、文字与照片' },
  { to: '/wardrobe/new', label: '记穿搭', icon: 'calendar-o', hint: '一次有日期的穿着' },
  { to: '/wardrobe/items/new', label: '添加衣物', icon: 'bag-o', hint: '长期档案，不记穿着次数' },
  { to: '/people', label: '添加人物', icon: 'friends-o', hint: '建立新的私人档案' },
]
function create(action) {
  showCreate.value = false
  router.push({ path: action.to, query: action.to === '/people' ? { add: '1' } : effectiveScopeId.value ? scopeQuery(effectiveScopeId.value) : { person: 'all' } })
}
function goBack() {
  if (window.history.state?.back != null) router.back()
  else router.push(route.meta?.backTo || '/')
}
async function doLogin() {
  loginError.value = ''
  setToken(tokenInput.value.trim())
  try {
    await store.bootstrap()
    title.value = store.config?.app_title || title.value
    authed.value = true
    tokenInput.value = ''
  } catch (e) {
    setToken('')
    loginError.value = e.message || '登录失败'
  }
}
onMounted(async () => {
  if (!authed.value) return
  store.hydrateFromCache()
  try {
    await store.bootstrap()
    title.value = store.config?.app_title || title.value
  } catch (e) {
    authed.value = false
    loginError.value = e.message || ''
  }
})
</script>

<style>
*, *::before, *::after { box-sizing: border-box; }
body { margin:0; background:var(--canvas); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif; }
button,input,select,textarea { font:inherit; }
button,select { touch-action:manipulation; }
a { color:var(--accent); }
.bar,.container { width:100%; max-width:var(--content-max); margin:0 auto; }
.login { min-height:100dvh; display:flex; align-items:center; justify-content:center; padding:24px; }
.login-box { width:100%; max-width:380px; padding:28px; border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); }
.login-box h1 { font-size:24px; margin:0 0 12px; }
.hint,.muted { font-size:12px; color:var(--muted); }
.err,.danger { color:var(--danger); }
.topbar { position:sticky; top:0; z-index:20; padding-top:var(--safe-top); background:var(--surface); border-bottom:1px solid var(--line); }
.topbar .bar { display:flex; gap:6px; align-items:center; min-height:var(--topbar-h); padding:6px 12px; }
.title { flex:1; font-size:18px; font-weight:650; min-width:0; }
.actions { display:flex; }
.iconbtn { display:inline-flex; justify-content:center; align-items:center; min-width:44px; min-height:44px; background:none; border:0; color:var(--ink); font-size:19px; cursor:pointer; }
.scope-tag { max-width:55%; display:flex; align-items:center; gap:6px; }
.scope-tag select { min-width:0; max-width:150px; min-height:40px; background:var(--accent-soft); color:var(--accent); border:0; border-radius:10px; padding:6px; }
.default-scope { border:0; background:none; color:var(--accent); font-size:11px; max-width:42px; min-height:44px; cursor:pointer; }
.subnav { position:sticky; top:calc(var(--safe-top) + var(--topbar-h)); z-index:15; background:var(--surface); border-bottom:1px solid var(--line); }
.segs { display:flex; gap:6px; padding:6px 12px; }
.segtab { flex:1; text-align:center; padding:10px; border-radius:10px; text-decoration:none; font-size:13px; color:var(--muted); }
.segtab.active { color:var(--accent); background:var(--accent-soft); }
.page { padding:16px; }
.page.has-tabbar { padding-bottom:calc(var(--tabbar-h) + var(--safe-bottom) + 88px); }
.page:not(.has-tabbar) { padding-bottom:calc(12px + var(--safe-bottom)); }
.tabbar { position:fixed; bottom:0; left:0; right:0; z-index:20; background:var(--surface); border-top:1px solid var(--line); padding-bottom:var(--safe-bottom); }
.tabs { display:flex; }
.tab { flex:1; min-height:var(--tabbar-h); display:flex; flex-direction:column; justify-content:center; align-items:center; gap:5px; font-size:12px; text-decoration:none; color:var(--muted); }
.tab .van-icon { font-size:22px; }
.tab.active { color:var(--accent); font-weight:650; }
.fab { position:fixed; bottom:calc(var(--tabbar-h) + var(--safe-bottom) + 16px); right:20px; z-index:30; min-height:48px; border:0; border-radius:25px; padding:12px 22px; background:var(--accent); color:white; box-shadow:0 4px 16px #234c4330; font-weight:650; cursor:pointer; }
.card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); padding:16px; margin-bottom:14px; }
.card h3 { font-size:15px; margin:0 0 12px; }
.row { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 0; font-size:14px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; }
.chips .van-tag { min-height:30px; padding:5px 10px; cursor:pointer; }
.warn { color:var(--warning); }
.link { color:var(--accent); cursor:pointer; }
.create-menu { max-width:600px; margin:auto; padding:24px 20px; }
.create-menu h2 { margin-top:0; font-size:20px; }
.create-menu > button:not(.van-button) { width:100%; border:0; border-top:1px solid var(--line); background:transparent; padding:18px 4px; text-align:left; font-size:16px; color:var(--ink); cursor:pointer; }
.create-menu button span { display:block; margin:6px 0 0 24px; color:var(--muted); font-size:12px; }
@media(min-width:1000px) {
  .app { padding-left:190px; }
  .tabbar { width:190px; top:0; right:auto; border-top:0; border-right:1px solid var(--line); padding:90px 12px 24px; }
  .tabs { flex-direction:column; gap:12px; }
  .tab { flex-direction:row; justify-content:flex-start; padding:12px 18px; gap:12px; border-radius:12px; }
  .tab.active { background:var(--accent-soft); }
  .fab { bottom:28px; right:32px; }
  .page { padding:24px; }
  .page.has-tabbar { padding-bottom:100px; }
}
@media(max-width:380px) { .topbar .bar { gap:2px; padding:6px; } .scope-tag { gap:0; } .scope-tag select { max-width:108px; } .title { font-size:16px; } .actions .iconbtn { min-width:36px; } }
</style>
