<template>
  <!-- 口令未设置：先登录 -->
  <div v-if="!authed" class="login">
    <div class="login-box">
      <h1>{{ title }}</h1>
      <p class="hint">请输入页面口令（在部署目录 .env 的 ARCHIVE_TOKEN 里）</p>
      <van-field
        v-model="tokenInput"
        type="password"
        label="口令"
        placeholder="粘贴口令"
        @keyup.enter="doLogin"
      />
      <van-button block type="primary" style="margin-top: 12px" @click="doLogin">进入</van-button>
      <p v-if="loginError" class="err">{{ loginError }}</p>
    </div>
  </div>

  <!-- 已登录：顶栏 + 正文 + 底部导航 -->
  <div v-else class="app">
    <header class="topbar">
      <div class="bar">
        <button v-if="showBack" class="iconbtn" aria-label="返回" @click="goBack">
          <van-icon name="arrow-left" />
        </button>
        <span class="title">{{ headerTitle }}</span>
        <!-- 只读范围指示器：显示本页实际看到谁（来自 ?person / 路由参数），不改全局 scope -->
        <span v-if="showScope" class="scope-tag" :title="'本页范围：' + scopeText">
          看：{{ scopeText }}
        </span>
        <span class="actions">
          <button v-if="showSearch" class="iconbtn" aria-label="搜索" @click="router.push('/search')">
            <van-icon name="search" />
          </button>
          <button v-if="showGear" class="iconbtn" aria-label="设置" @click="router.push('/settings')">
            <van-icon name="setting-o" />
          </button>
        </span>
      </div>
    </header>

    <!-- 分组内二级分段：复用既有路由（记录/相册/衣橱、人物/关系），并带上当前范围 -->
    <nav v-if="segments" class="subnav">
      <div class="bar segs">
        <router-link
          v-for="s in segments"
          :key="s.key"
          :to="segTarget(s)"
          class="segtab"
          :class="{ active: s.key === segKey }"
        >
          {{ s.label }}
        </router-link>
      </div>
    </nav>

    <main class="page" :class="{ 'has-tabbar': showTabbar }">
      <div class="container">
        <router-view />
      </div>
    </main>

    <!-- 固定「＋记录」入口：录入/编辑路由下隐藏；带上当前实际范围的人 -->
    <router-link v-if="showFab" class="fab" :to="fabTo">＋ 记录</router-link>

    <!-- 底部 4 个主 tab（图标 + 文字）：录入/编辑路由与记录编辑弹层下隐藏 -->
    <nav v-if="showTabbar" class="tabbar">
      <div class="bar tabs">
        <router-link
          v-for="t in TABS"
          :key="t.key"
          :to="t.to"
          class="tab"
          :class="{ active: t.key === tabKey }"
        >
          <van-icon :name="t.icon" />
          <span class="tab-label">{{ t.label }}</span>
        </router-link>
      </div>
    </nav>
  </div>
</template>

<script setup>
import { computed, watch, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, getToken, setToken } from './api'
import { useArchiveStore } from './store'
import { TABS, activeTabKey, activeSegmentKey, segmentsForRoute } from './lib/nav'
import { normalizePersonId, scopeQuery, routeScopePersonId } from './lib/scope'
import { anyOutfitEnabled } from './lib/modules'

const store = useArchiveStore()
const route = useRoute()
const router = useRouter()
const authed = ref(!!getToken())
const tokenInput = ref('')
const loginError = ref('')
const title = ref('Kinship Archive')

const headerTitle = computed(() => route.meta?.title || title.value)
const showBack = computed(() => !!route.meta?.back)
const showSearch = computed(() => route.name !== 'search')
const showGear = computed(() => route.name === 'dashboard')
// 编辑记录弹层打开时也隐藏 tabbar / FAB（避免弹层里叠一层导航）
const showTabbar = computed(() => !route.meta?.hideTabbar && !store.editingRecord)
const showFab = computed(() => route.name !== 'new' && !store.editingRecord)
const tabKey = computed(() => activeTabKey(route))
const segKey = computed(() => activeSegmentKey(route))

// ---- 范围（只读，不改全局）----
// 本页「实际显示谁」：个人详情用路由参数，其余下游页用 ?person；都没有 → null。
const scopePersonId = computed(() => routeScopePersonId(route))
// 需要补全局范围的地方（分段/FAB）：优先本页 ?person，其次全局当前人物。
const effectiveScopeId = computed(
  () => scopePersonId.value || normalizePersonId(store.currentPersonId)
)
const showScope = computed(() => !!route.meta?.scoped)
const scopeText = computed(() => {
  const id = scopePersonId.value || (route.meta?.scoped ? normalizePersonId(store.currentPersonId) : null)
  if (!id) return '全部'
  const p = store.persons.find((x) => x.id === id)
  return p ? store.displayName(p) : '全部'
})

// 分组分段是否带 ?person：时间轴分组是「跟随范围」的，人物分组不是。
const segmentQuery = computed(() =>
  route.meta?.group === 'timeline' ? scopeQuery(effectiveScopeId.value) : {}
)
function segTarget(s) {
  return { path: s.to, query: segmentQuery.value }
}
const fabTo = computed(() => ({ path: '/new', query: scopeQuery(effectiveScopeId.value) }))

// ---- 衣橱入口门控（服装模块）----
// 当前范围涉及的每个人：具体人 → [该人]；「全部」→ 所有人。
const activeScopeIds = computed(() =>
  effectiveScopeId.value
    ? [effectiveScopeId.value]
    : store.persons.map((p) => p.id)
)
// 未知（加载中/失败）时不隐藏 → legacy 路由仍可达；全部已知且都没开服装才隐藏。
const wardrobeVisible = computed(() => {
  const ids = activeScopeIds.value
  if (!ids.length) return true
  return anyOutfitEnabled(ids.map((id) => store.hasModule(id, 'outfit')))
})
const segments = computed(() => {
  const segs = segmentsForRoute(route)
  if (!segs) return null
  return segs.filter((s) => s.key !== 'wardrobe' || wardrobeVisible.value)
})

// 进入时间轴分组时，补齐当前范围各人的模块开关（有缓存就跳过）
watch(
  [() => route.name, () => store.persons.length, activeScopeIds],
  () => {
    const segs = segmentsForRoute(route)
    if (!segs || !segs.some((s) => s.key === 'wardrobe')) return
    if (activeScopeIds.value.length) store.ensureModules(activeScopeIds.value)
  },
  { immediate: true }
)

// 返回：有历史就回退，冷启动深链（history.state.back 为空）落到 meta.backTo
function goBack() {
  const st = window.history.state
  if (st && st.back != null) router.back()
  else router.push(route.meta?.backTo || '/')
}

async function doLogin() {
  loginError.value = ''
  setToken(tokenInput.value.trim())
  try {
    await store.bootstrap()
    title.value = store.config?.app_title || title.value
    authed.value = true
  } catch (e) {
    setToken('')
    loginError.value = e.message || '登录失败'
  }
}

// 人物切换已收归首页（Dashboard）——这里不再需要切换处理

onMounted(async () => {
  if (!authed.value) return
  // 先用上次的缓存把界面撑起来（同步、0 往返），再回源刷新 —— 慢链路上不白屏
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
:root {
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-top: env(safe-area-inset-top, 0px);
  --content-max: 720px;
  --tabbar-h: 54px;
  --topbar-h: 44px;
}
*, *::before, *::after {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: #f7f8fa;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #323233;
}
/* 居中容器：width:100% + 内边距若无 border-box 会横向溢出，故全局 border-box（见上） */
.bar {
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  box-sizing: border-box;
}
.container {
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
}
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}
.login-box {
  width: 100%;
  max-width: 360px;
  background: #fff;
  border-radius: 12px;
  padding: 20px;
}
.login-box h1 {
  font-size: 20px;
  margin: 0 0 6px;
}
.hint,
.err {
  font-size: 12px;
  color: #969799;
}
.err {
  color: #ee0a24;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: #fff;
  border-bottom: 1px solid #ebedf0;
  padding-top: var(--safe-top);
}
/* 顶栏固定高度：二级分段条按同样的高度精确偏移，避免错位 */
.topbar .bar {
  display: flex;
  align-items: center;
  gap: 6px;
  height: var(--topbar-h);
  padding: 0 12px;
}
.topbar .title {
  font-weight: 600;
  font-size: 15px;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scope-tag {
  flex: 0 0 auto;
  font-size: 12px;
  color: #1989fa;
  background: #ecf5ff;
  border-radius: 10px;
  padding: 2px 8px;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar .actions {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
}
/* 触控目标 ≥ 44px */
.iconbtn {
  border: none;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  min-width: 44px;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: #323233;
  cursor: pointer;
}
/* 二级分段条（分组内），复用既有路由；偏移正好等于 安全区 + 顶栏高度 */
.subnav {
  position: sticky;
  top: calc(var(--safe-top) + var(--topbar-h));
  z-index: 15;
  background: #fff;
  border-bottom: 1px solid #ebedf0;
}
.segs {
  display: flex;
  gap: 4px;
  padding: 6px 8px;
}
.segtab {
  flex: 1;
  text-align: center;
  padding: 6px 0;
  font-size: 13px;
  color: #646566;
  text-decoration: none;
  border-radius: 8px;
}
.segtab.active {
  color: #1989fa;
  background: #ecf5ff;
  font-weight: 600;
}
.page {
  padding: 12px;
}
/* 有底部 tabbar 时给足底部留白：让最后一个条目不被 tabbar / 悬浮「＋记录」遮住 */
.page.has-tabbar {
  padding-bottom: calc(var(--tabbar-h) + var(--safe-bottom) + 72px);
}
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  background: #fff;
  border-top: 1px solid #ebedf0;
  padding-bottom: var(--safe-bottom);
}
.tabs {
  display: flex;
}
.tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 6px 0;
  min-height: calc(var(--tabbar-h) - 1px);
  font-size: 11px;
  line-height: 1;
  color: #646566;
  text-decoration: none;
}
.tab .van-icon {
  font-size: 20px;
}
.tab.active {
  color: #1989fa;
  font-weight: 600;
}
/* 固定「＋记录」：悬在 tabbar 之上 */
.fab {
  position: fixed;
  right: 16px;
  bottom: calc(var(--tabbar-h) + var(--safe-bottom) + 14px);
  z-index: 30;
  background: #1989fa;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  padding: 10px 16px;
  border-radius: 22px;
  text-decoration: none;
  box-shadow: 0 4px 12px rgba(25, 137, 250, 0.35);
}
.card {
  background: #fff;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
}
.card h3 {
  margin: 0 0 8px;
  font-size: 14px;
}
.muted {
  color: #969799;
  font-size: 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.warn {
  color: #ff976a;
}
.danger {
  color: #ee0a24;
}
.link {
  color: #1989fa;
  cursor: pointer;
}
</style>
