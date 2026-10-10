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

  <!-- 已登录：正文 + 底部导航 -->
  <div v-else class="app">
    <header class="topbar">
      <span class="title">{{ title }}</span>
      <!-- 只读的"当前看谁"：切换器在首页，其他页面只跟随、不再放控件 -->
      <span class="scope" v-if="store.persons.length && route.path !== '/'">
        显示：{{ store.scopeLabel }}
      </span>
    </header>

    <main class="page">
      <router-view />
    </main>

    <nav class="tabbar">
      <router-link to="/" class="tab">今天</router-link>
      <router-link to="/new" class="tab">记录</router-link>
      <router-link to="/timeline" class="tab">时间轴</router-link>
      <router-link to="/wardrobe" class="tab">衣橱</router-link>
      <router-link to="/relations" class="tab">关系</router-link>
      <router-link to="/gallery" class="tab">相册</router-link>
      <router-link to="/todos" class="tab">待办</router-link>
      <router-link to="/search" class="tab">搜索</router-link>
      <router-link to="/settings" class="tab">设置</router-link>
    </nav>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, getToken, setToken } from './api'
import { useArchiveStore } from './store'

const store = useArchiveStore()
const route = useRoute()
const authed = ref(!!getToken())
const tokenInput = ref('')
const loginError = ref('')
const title = ref('Kinship Archive')

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
}
body {
  margin: 0;
  background: #f7f8fa;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  color: #323233;
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
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  background: #fff;
  border-bottom: 1px solid #ebedf0;
}
.topbar .title {
  font-weight: 600;
  font-size: 15px;
}
.scope {
  font-size: 12px;
  color: #969799;
}
.page {
  padding: 12px 12px calc(64px + var(--safe-bottom));
}
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  background: #fff;
  border-top: 1px solid #ebedf0;
  padding-bottom: var(--safe-bottom);
}
.tab {
  flex: 1;
  text-align: center;
  padding: 10px 0;
  font-size: 12px;
  color: #646566;
  text-decoration: none;
}
.tab.router-link-active {
  color: #1989fa;
  font-weight: 600;
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
</style>
