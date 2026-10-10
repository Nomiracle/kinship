<template>
  <div>
    <div class="card">
      <h3>记录谁</h3>
      <select v-model="personId" class="picker" @change="onPickPerson">
        <option v-for="p in store.persons" :key="p.id" :value="p.id">
          {{ store.displayName(p) }}
        </option>
      </select>
      <p class="muted" style="margin-top: 8px">同时关联其他人（三人场合等，可多选）</p>
      <div class="chips">
        <van-tag
          v-for="p in store.persons.filter((x) => x.id !== personId)"
          :key="p.id"
          :type="extraIds.includes(p.id) ? 'primary' : 'default'"
          size="large"
          @click="toggleExtra(p.id)"
        >
          {{ store.displayName(p) }}
        </van-tag>
      </div>
    </div>

    <div class="card">
      <h3>记什么</h3>
      <div class="chips">
        <van-tag
          v-for="t in availableTypes"
          :key="t.key"
          :type="type === t.key ? 'primary' : 'default'"
          size="large"
          @click="type = t.key"
        >
          {{ t.label }}
        </van-tag>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        按「{{ personLabel }}」启用的模块显示（{{ availableTypes.length }} 项）—— 去个人页可开关模块。
      </p>
    </div>

    <!-- 服装有专有流程（衣橱）：这里只留入口，不再把「勾单品」混进通用记事 -->
    <div class="card" v-if="outfitEnabled">
      <h3>记穿搭（服装）</h3>
      <p class="muted" style="margin: 0 0 8px">
        服装已独立成「衣橱」的专有流程：勾单品、累加穿次数、照片挂这次穿搭。
      </p>
      <van-button block size="small" type="primary" @click="goOutfit">
        ＋ 记一次穿着（今天）
      </van-button>
    </div>

    <div class="card">
      <h3>哪一天</h3>
      <div class="chips" style="margin-bottom: 8px">
        <van-button size="small" :type="isToday ? 'primary' : 'default'" @click="setDate(todayStr)">
          今天
        </van-button>
        <van-button size="small" :type="isYesterday ? 'primary' : 'default'" @click="setDate(shift(-1))">
          昨天
        </van-button>
        <van-button size="small" :type="isBeforeYesterday ? 'primary' : 'default'" @click="setDate(shift(-2))">
          前天
        </van-button>
      </div>
      <input v-model="eventDate" type="date" class="picker" />
      <!-- 跨零点防错：不是今天就明确回显「哪一天 + 星期几」，避免又记错日期 -->
      <p class="muted" style="margin: 8px 0 0" :class="{ warn: !isToday }">
        将记到：<strong>{{ dateHuman }}</strong>
        <span v-if="!isToday">（不是今天，请再确认一次）</span>
      </p>
    </div>

    <div class="card">
      <h3>内容</h3>
      <van-field v-model="title" :label="titleLabel" :placeholder="titlePlaceholder" />

      <van-field
        v-if="type === 'text' || type === 'health' || type === 'mood'"
        v-model="body"
        type="textarea"
        rows="3"
        autosize
        label="详细"
        placeholder="她说过的、穿过的、发生的事…"
      />

      <template v-if="type === 'period'">
        <p class="muted">
          只记录开始日期。会同时落一条生理期明细，用于周期统计与提醒（预测误差约 ±3 天，仅作关怀提醒）。
        </p>
      </template>

      <template v-if="type === 'meeting'">
        <van-field v-model="location" label="地点" placeholder="在哪里" />
        <van-field v-model="hours" type="number" label="时长(小时)" placeholder="可留空" />
        <van-cell title="过夜">
          <template #right-icon>
            <van-switch v-model="overnight" size="20" />
          </template>
        </van-cell>
      </template>

      <van-field
        v-if="type === 'text'"
        v-model="tags"
        label="标签"
        placeholder="逗号分隔，便于以后检索"
      />

      <div v-if="mediaEnabled" style="margin-top: 10px">
        <div class="muted" style="margin-bottom: 6px">图片（可选，可多选；iPhone 拍的 HEIC 会自动转）</div>
        <van-uploader v-model="fileList" multiple :max-count="9" :preview-size="64" />
      </div>
      <p v-else class="muted" style="margin-top: 10px">（这个人没开「图片」模块，附件区已隐藏）</p>

      <van-button
        block
        type="primary"
        style="margin-top: 12px"
        :loading="saving"
        @click="submit"
      >
        保存
      </van-button>
    </div>

    <div class="card" v-if="recent.length">
      <h3>刚记的</h3>
      <div class="row" v-for="r in recent" :key="r.id">
        <span>
          <van-tag plain>{{ typeLabel(r.type_key) }}</van-tag>
          {{ r.title || r.body?.slice(0, 20) }}
        </span>
        <span class="muted">{{ fmt(r.event_date) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { availableEventTypes, reconcileEventType } from '../lib/modules'
import { normalizePersonId, scopeQuery } from '../lib/scope'

const store = useArchiveStore()
const route = useRoute()
const router = useRouter()
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

const type = ref('text')
const personId = ref(null)
// --- 按这个人的模块开关决定「能记什么」 ---
const modules = ref([])
const personObj = computed(
  () => store.persons.find((p) => p.id === Number(personId.value)) || null
)
const personLabel = computed(() => (personObj.value ? store.displayName(personObj.value) : '这个人'))
// 绑了 module 的类型要求该模块已启用；没绑 module 的（文字/情绪/里程碑/爱好/社交）任何时候都能记
const availableTypes = computed(() => availableEventTypes(store.eventTypes, modules.value))
const mediaEnabled = computed(() => modules.value.includes('media'))
// 服装不在这里记（已迁到衣橱专有页），只留一个入口卡片
const outfitEnabled = computed(() => modules.value.includes('outfit'))
function goOutfit() {
  router.push({ path: '/wardrobe/new', query: scopeQuery(personId.value) })
}

async function loadModules() {
  if (!personId.value) return
  try {
    const m = await api.modules(Number(personId.value))
    modules.value = m?.enabled || []
  } catch {
    modules.value = []
  }
  // 切人后当前选中的类型可能已不可用 → 回退到「文字」，否则会记出这个人没有的类型
  type.value = reconcileEventType(type.value, availableTypes.value)
}
// onMounted 第一次定人时会自己并发拉一遍，这次 watcher 要跳过，否则请求发两遍
let skipNextPick = false
watch(personId, async () => {
  if (skipNextPick) {
    skipNextPick = false
    return
  }
  await loadModules()
})
// 同时在场的人（三人场合）：事件会同时挂到这些人名下
const extraIds = ref([])
function toggleExtra(id) {
  const i = extraIds.value.indexOf(id)
  if (i >= 0) extraIds.value.splice(i, 1)
  else extraIds.value.push(id)
}
// 记录页的人 = 全局当前人物：在这儿换人同时更新全局，
// 但只有在"你主动选"时才回写（默认值回写会把首页的「全部」悄悄改掉）
function onPickPerson(e) {
  const id = e.target.value
  if (id) store.setCurrentPerson(id)
}

const eventDate = ref('')
const title = ref('')
const body = ref('')
const tags = ref('')
const location = ref('')
const hours = ref('')
const overnight = ref(false)
const saving = ref(false)
const recent = ref([])
const fileList = ref([])

// 服装的勾单品逻辑不在这里了：抽成 components/OutfitForm.vue，
// 由衣橱专有页（/wardrobe/new）与时间轴的编辑面板共用（见 NewRecord 顶部「记穿搭」入口）。

const todayStr = new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD（本地时区）
function shift(days) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toLocaleDateString('sv-SE')
}
function setDate(v) {
  eventDate.value = v
}

const isToday = computed(() => eventDate.value === todayStr)
const isYesterday = computed(() => eventDate.value === shift(-1))
const isBeforeYesterday = computed(() => eventDate.value === shift(-2))

const dateHuman = computed(() => {
  if (!eventDate.value) return ''
  const d = new Date(eventDate.value + 'T00:00:00')
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')} ${WEEK[d.getDay()]}`
})

const titleLabel = computed(
  () => ({ text: '标题', period: '备注', meeting: '做了什么' }[type.value] || '标题')
)
const titlePlaceholder = computed(
  () =>
    ({
      text: '一句话概括',
      period: '可留空',
      meeting: '如：一起吃饭、双人开黑',
    }[type.value] || '')
)

function fmt(s) {
  return s ? s.slice(5) : ''
}
function typeLabel(key) {
  const t = store.eventTypes.find((x) => x.key === key)
  return t ? t.label : key
}

async function uploadPickedFiles(createdId) {
  if (!fileList.value.length) return null
  let ok = 0
  for (const item of fileList.value) {
    try {
      await api.uploadMedia(item.file || item, {
        person_id: Number(personId.value),
        event_id: createdId,
        captured_on: eventDate.value,
      })
      ok += 1
    } catch (e) {
      showToast(`图片上传失败：${e.message}`)
    }
  }
  fileList.value = []
  return ok
}

function resetContent() {
  title.value = ''
  body.value = ''
  tags.value = ''
  location.value = ''
  hours.value = ''
  overnight.value = false
}

async function submit() {
  if (!personId.value) {
    showToast('先选一个人')
    return
  }
  if (!eventDate.value) {
    showToast('先选日期')
    return
  }
  // 跨零点第二次确认：非今天必须显式确认
  if (!isToday.value) {
    try {
      await showConfirmDialog({
        title: '确认日期',
        message: `确定记到 ${dateHuman.value} 吗？\n（不是今天，跨零点容易记错）`,
        confirmButtonText: '就是这天',
        cancelButtonText: '改回今天',
      })
    } catch {
      setDate(todayStr)
      return
    }
  }
  saving.value = true
  try {
    const payload = {
      person_id: Number(personId.value),
      type_key: type.value,
      event_date: eventDate.value,
      title: title.value || null,
      body: body.value || null,
      tags: tags.value || null,
    }
    // 三人场合：把同时在场的人一起挂上（后端 event_persons 表）
    if (extraIds.value.length) {
      payload.person_ids = [...new Set([Number(personId.value), ...extraIds.value])]
    }
    if (type.value === 'meeting') {
      payload.location = location.value || null
      payload.overnight = overnight.value
      payload.hours = hours.value ? Number(hours.value) : null
    }
    const created = await api.createEvent(payload)
    const ok = await uploadPickedFiles((created && created.id) || null)
    if (ok === null) showToast('已记录')
    else if (ok) showToast(`已记录，含 ${ok} 张图片`)
    else showToast('已记录（图片未上传成功）')
    resetContent()
    await loadRecent()
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadRecent() {
  const res = await api.events({ person_id: personId.value, limit: 5 })
  recent.value = res.items || []
}

onMounted(async () => {
  eventDate.value = todayStr
  // 硬刷新直接进本页时 persons 可能还没加载完 —— 先补一次再定人（旧版这里会空着）
  await store.ensureLoaded()
  // 三件事互不依赖 → 并发（慢链路上少两个往返）。
  // 先举标志再赋值：watch(personId) 会在下一个微任务触发，见标志就跳过（不重复发请求）。
  skipNextPick = true
  // 「＋记录」FAB / 个人页入口会带 ?person=<id>：优先用它（本页照此记到那个人），
  // 其次跟随全局当前人物，再退到第一个可记录的人。
  personId.value =
    normalizePersonId(route.query.person) ||
    store.currentPersonId ||
    store.others[0]?.id ||
    store.persons[0]?.id
  await Promise.all([loadModules(), loadRecent()])
  skipNextPick = false // 万一 personId 没变化（watcher 没触发），别把标志留在 true
})

// 万一 bootstrap 比本页慢，人员到位后再补一次
watch(
  () => store.persons.length,
  async (n) => {
    if (n && !personId.value) {
      personId.value =
        normalizePersonId(route.query.person) ||
        store.currentPersonId ||
        store.others[0]?.id ||
        store.persons[0]?.id
      await loadModules()
    }
  }
)
</script>

<style scoped>
.picker {
  width: 100%;
  padding: 8px;
  border: 1px solid #ebedf0;
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
}
</style>
