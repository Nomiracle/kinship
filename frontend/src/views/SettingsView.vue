<template>
  <div>
    <div class="card">
      <h3>服务状态</h3>
      <div class="row"><span>数据库</span><span>{{ health?.database?.ok ? '正常' : '异常' }}</span></div>
      <div class="row"><span>库名</span><span>{{ health?.database?.name }}</span></div>
      <div class="row"><span>口令保护</span><span>{{ health?.auth_required ? '已启用' : '未设置' }}</span></div>
      <div class="row"><span>前端产物</span><span>{{ health?.dist_present ? '已就绪' : '缺失' }}</span></div>
      <div class="row"><span>部署目录</span><span class="muted">{{ health?.deploy_dir }}</span></div>
      <div class="row"><span>媒体用量</span><span>{{ storage?.files || 0 }} 个文件 · {{ storage?.mb || 0 }} MB</span></div>
      <div class="row"><span>媒体目录</span><span class="muted">{{ storage?.dir }}</span></div>
      <div class="row"><span>图片处理</span><span>{{ storage?.sips_available ? 'sips 可用（HEIC 自动转）' : 'sips 不可用' }}</span></div>
    </div>

    <div class="card">
      <h3>添加一个人</h3>
      <van-field v-model="form.display_name" label="称呼" placeholder="如：妈妈 / 阿明" />
      <div class="row">
        <span class="muted">关系</span>
        <select v-model="form.relation_type" class="picker">
          <option v-for="r in relationTypes" :key="r.key" :value="r.key">{{ r.label }}</option>
        </select>
      </div>
      <van-field v-model="form.birthday" type="date" label="生日" placeholder="可留空" />
      <van-cell title="农历生日">
        <template #right-icon><van-switch v-model="form.birthday_lunar" size="20" /></template>
      </van-cell>
      <template v-if="form.birthday_lunar">
        <van-field v-model.number="form.lunar_month" type="digit" label="农历月" />
        <van-field v-model.number="form.lunar_day" type="digit" label="农历日" />
      </template>
      <van-button block type="primary" style="margin-top: 10px" @click="addPerson">添加</van-button>
      <p class="muted">模块会按关系类型自动开好，之后可在个人页调整。</p>
    </div>

    <div class="card">
      <h3>人物管理</h3>
      <div class="row" v-for="p in store.persons" :key="p.id">
        <span>
          <router-link :to="'/person/' + p.id" style="text-decoration: none; color: inherit">
            {{ store.displayName(p) }}
          </router-link>
          <span class="muted" style="margin-left: 6px">{{ store.relationLabel(p.relation_type) }}</span>
          <van-tag plain style="margin-left: 4px">{{ store.circleLabel(p.circle) }}</van-tag>
          <span class="muted" v-if="p.via_name" style="margin-left: 4px">· 通过 {{ p.via_name }}</span>
          <span class="muted" v-if="p.birthday || p.birthday_lunar" style="margin-left: 6px">
            {{ p.birthday_lunar ? `农历${p.lunar_month}/${p.lunar_day}` : p.birthday }}
          </span>
        </span>
        <span class="danger" v-if="!p.is_self" @click="removePerson(p)">删除</span>
      </div>
    </div>

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
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
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
const form = reactive({
  display_name: '',
  relation_type: 'family',
  birthday: '',
  birthday_lunar: false,
  lunar_month: null,
  lunar_day: null,
})

const relationTypes = computed(() => (store.config?.relation_types || []).filter((r) => r.key !== 'self'))

async function load() {
  // 并发：两个请求互不依赖，慢链路上少一个往返
  const [h, s] = await Promise.all([api.health(), api.storage()])
  health.value = h
  storage.value = s
}

async function addPerson() {
  if (!form.display_name.trim()) return
  const payload = {
    display_name: form.display_name.trim(),
    relation_type: form.relation_type,
    birthday: form.birthday || null,
    birthday_lunar: form.birthday_lunar,
  }
  if (form.birthday_lunar) {
    payload.lunar_month = form.lunar_month
    payload.lunar_day = form.lunar_day
  }
  try {
    await api.createPerson(payload)
    showToast('已添加')
    Object.assign(form, {
      display_name: '',
      birthday: '',
      birthday_lunar: false,
      lunar_month: null,
      lunar_day: null,
    })
    await store.loadPersons()
  } catch (e) {
    showToast(e.message || '添加失败')
  }
}

async function removePerson(p) {
  try {
    await showConfirmDialog({ title: '删除', message: `删除「${p.display_name}」及其全部记录？` })
  } catch {
    return
  }
  try {
    await api.deletePerson(p.id)
    await store.loadPersons()
    showToast('已删除')
  } catch (e) {
    showToast(e.message || '删除失败')
  }
}

function logout() {
  setToken('')
  location.reload()
}

onMounted(load)
</script>

<style scoped>
.picker {
  padding: 6px;
  border: 1px solid #ebedf0;
  border-radius: 6px;
  font-size: 13px;
}
</style>
