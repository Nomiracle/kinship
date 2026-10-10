<template>
  <div>
    <div class="card">
      <h3>隐私模式</h3>
      <p class="muted">
        打开后，列表与下拉里的人名里，标记为「敏感」的人显示为 ●●●（
        伴侣那边的人默认敏感）。个人详情页不受影响 —— 你既然点进去了就正常显示。
      </p>
      <van-switch v-model="privacyMode" size="20" />
      <span class="muted" style="margin-left: 8px">{{ privacyMode ? '已开启' : '已关闭' }}</span>
    </div>

    <div class="card">
      <h3>人物</h3>
      <p class="muted">增删人物、按圈子筛选、添加关系，都在「人物」页。</p>
      <router-link to="/people"><van-button size="small">去人物管理 →</van-button></router-link>
    </div>

    <div class="card">
      <h3>关于</h3>
      <p class="muted">
        通用关系档案系统。代码公开、数据全在本机：后端 {{ health?.version }}，库
        {{ health?.database?.name }}。图片与备份在部署目录（仓库之外）。
      </p>
      <p class="muted">
        生理期预测基于平均周期，误差约 ±3 天，仅用于关怀提醒，不可用于避孕或任何医学判断。
      </p>
      <van-button size="small" @click="logout">退出登录</van-button>
    </div>

    <!-- 诊断（默认收起） -->
    <div class="card">
      <div class="row" style="padding: 0" @click="diagOpen = !diagOpen">
        <h3 style="margin: 0">诊断</h3>
        <span class="muted">{{ diagOpen ? '收起 ▲' : '展开 ▼' }}</span>
      </div>
      <template v-if="diagOpen">
        <div class="row"><span>数据库</span><span>{{ health?.database?.ok ? '正常' : '异常' }}</span></div>
        <div class="row"><span>库名</span><span>{{ health?.database?.name }}</span></div>
        <div class="row"><span>口令保护</span><span>{{ health?.auth_required ? '已启用' : '未设置' }}</span></div>
        <div class="row"><span>前端产物</span><span>{{ health?.dist_present ? '已就绪' : '缺失' }}</span></div>
        <div class="row"><span>部署目录</span><span class="muted">{{ health?.deploy_dir }}</span></div>
        <div class="row"><span>媒体用量</span><span>{{ storage?.files || 0 }} 个文件 · {{ storage?.mb || 0 }} MB</span></div>
        <div class="row"><span>媒体目录</span><span class="muted">{{ storage?.dir }}</span></div>
        <div class="row"><span>图片处理</span><span>{{ storage?.sips_available ? 'sips 可用（HEIC 自动转）' : 'sips 不可用' }}</span></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, setToken } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
// 隐私模式绑到 store（并持久化：否则刷新就回到关闭，等于没用）
const privacyMode = computed({
  get: () => store.privacyMode,
  set: (v) => store.setPrivacyMode(v),
})
const health = ref(null)
const storage = ref(null)
const diagOpen = ref(false)

async function load() {
  // 并发：两个请求互不依赖，慢链路上少一个往返
  try {
    const [h, s] = await Promise.all([api.health(), api.storage()])
    health.value = h
    storage.value = s
  } catch {
    // 诊断拿不到不影响主功能
  }
}

function logout() {
  setToken('')
  location.reload()
}

onMounted(load)
</script>
