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

    <!-- 穿搭：先在弹层「选择衣物」里勾好，回到本页显示已选（带缩略图），
         本页底部那个「保存」才是唯一的真保存（弹层里不会写库） -->
    <div class="card" v-if="type === 'outfit'">
      <h3>穿搭 · 选了哪几件</h3>
      <p class="muted" style="margin: 0 0 8px">
        先点「选择衣物」在弹层里勾（单品挂在人名下，记谁就选谁的衣橱）。选好回到这里，
        底部点「保存」才真记下来。
      </p>
      <div v-if="picked.length" class="picked-grid">
        <div v-for="p in picked" :key="pickKey(p)" class="picked-item">
          <img v-if="thumbOf(p)" :src="thumbOf(p)" :alt="p.name" />
          <span v-else class="picked-ph">{{ categoryLabel(p.category) }}</span>
          <div class="picked-name">{{ pickLabel(p) }}</div>
        </div>
      </div>
      <p v-else class="muted" style="margin: 0 0 8px">还没选衣物 —— 点下面按钮打开衣橱勾选</p>
      <div style="display: flex; gap: 8px">
        <van-button size="small" type="primary" @click="openPicker">选择衣物</van-button>
        <van-button v-if="picked.length" size="small" plain @click="picked = []">清空</van-button>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        已选 {{ picked.length }} 件 —— 保存后只生成 1 条穿搭记录；同名单品会复用已有的，不会重复建。
      </p>
    </div>

    <div class="card">
      <h3>哪一天</h3>
      <div class="chips" style="margin-bottom: 8px">
        <van-button size="small" :type="isToday ? 'primary' : 'default'" @click="setToday">
          今天
        </van-button>
        <van-button size="small" :type="isYesterday ? 'primary' : 'default'" @click="setDate(shift(-1))">
          昨天
        </van-button>
        <van-button size="small" :type="isBeforeYesterday ? 'primary' : 'default'" @click="setDate(shift(-2))">
          前天
        </van-button>
      </div>
      <!-- 精确到秒：原生 datetime-local（step=1）。只填日期 = 只记到日，
           界面不会显示 00:00，也不会假装那是凌晨记的。 -->
      <input v-model="eventWhen" type="datetime-local" step="1" class="picker" />
      <div class="chips" style="margin-top: 6px">
        <van-tag type="default" @click="setTime(nowLocalTime())">此刻</van-tag>
        <van-tag v-if="eventTime" plain @click="setTime('')">只记到日（清掉时间）</van-tag>
      </div>
      <!-- 跨零点防错：不是今天就明确回显「哪一天 + 星期几」，避免又记错日期 -->
      <p class="muted" style="margin: 8px 0 0" :class="{ warn: !isToday }">
        将记到：<strong>{{ dateHuman }}</strong>
        <span v-if="!isToday">（不是今天，请再确认一次）</span>
      </p>
    </div>

    <div class="card">
      <h3>内容</h3>

      <!-- 服装：标题/正文默认按勾选的单品自动生成（单品是真源）；要手改就打开开关 -->
      <template v-if="type === 'outfit'">
        <van-field v-model="note" label="备注" placeholder="这次穿搭的备注（可空）" />
        <van-field v-model="tags" label="标签" placeholder="逗号分隔，便于以后检索" />
        <van-cell title="手改标题 / 正文">
          <template #right-icon>
            <van-switch v-model="manualText" size="20" />
          </template>
        </van-cell>
        <template v-if="manualText">
          <van-field v-model="title" label="标题" placeholder="留空则按单品自动生成" />
          <van-field
            v-model="body"
            type="textarea"
            rows="3"
            autosize
            label="正文"
            placeholder="留空则按单品自动生成"
          />
        </template>
        <p class="muted">不手改时，标题/正文按勾选的单品自动生成（单品才是真源）。</p>
      </template>

      <template v-else>
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
      </template>

      <div v-if="mediaEnabled" style="margin-top: 10px">
        <div class="muted" style="margin-bottom: 6px">{{ mediaHint }}</div>
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

    <!-- 刚记的：按「写入时间」倒序（不是事件日期 —— 记到过去某天也得出现在这儿，
         否则像没记上），每条带 人物 / 单品 chips / 首图 -->
    <div class="card" v-if="recent.length">
      <h3>刚记的</h3>
      <div class="recent" v-for="r in recent" :key="r.id">
        <div class="row" style="padding: 0">
          <span>
            <van-tag plain>{{ typeLabel(r.type_key) }}</van-tag>
            <span class="muted" style="margin-left: 6px">{{ r.person_name || '—' }}</span>
          </span>
          <span class="muted">{{ fmt(r.event_date) }}</span>
        </div>
        <div class="recent-title">{{ r.title || r.body?.slice(0, 20) || '（无内容）' }}</div>
        <div v-if="recentThumb(r) || (r.items || []).length" class="recent-meta">
          <img v-if="recentThumb(r)" class="mini" :src="recentThumb(r)" alt="这次记录的照片" />
          <van-tag v-for="it in r.items || []" :key="it.item_id" plain size="medium">
            {{ itemLabel(it) }}<span v-if="it.color" class="muted"> · {{ it.color }}</span>
          </van-tag>
        </div>
      </div>
    </div>

    <!-- 选择衣物：弹层里只勾、不发任何请求；「确定」把草稿交回本页，「取消」丢弃 -->
    <van-popup v-model:show="showPicker" position="bottom" round :style="{ height: '86%' }">
      <div v-if="showPicker" class="pick-wrap">
        <div class="row">
          <h3 style="margin: 0">选择衣物 · {{ personLabel }}</h3>
          <span class="muted" @click="showPicker = false">关闭</span>
        </div>
        <OutfitForm
          mode="pick"
          :person-id="Number(personId)"
          :initial="picked"
          @confirm="onPickConfirm"
          @cancel="showPicker = false"
        />
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { availableEventTypes, reconcileEventType } from '../lib/modules'
import { normalizePersonId } from '../lib/scope'
import { eventThumb, itemThumb, pickKey, pickLabel, toOutfitRefs } from '../lib/outfit-pick'
import {
  dayOf,
  fmtTime,
  nowLocalTime,
  normalizeTime,
  splitLocal,
  toLocalInput,
} from '../lib/event-day'
import OutfitForm from '../components/OutfitForm.vue'

const store = useArchiveStore()
const route = useRoute()
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
// 服装：本页用弹层「选择衣物」勾单品（选择器本身不写库），
// 底部的「保存」是唯一的真保存 —— 走 POST /api/outfits（/wardrobe/new 留给衣橱侧的「立即记」）

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
  // 单品挂在人名下：换人后原来的「已选」必定对不上（后端 resolve_refs 也会拒绝跨人引用）
  if (picked.value.length) {
    picked.value = []
    showToast('已换人，请重新选择衣物')
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

// ---- 穿搭草稿（本页的「已选」）----
// 弹层选择器只把结果交回这里：带 item_id 的复用已有单品，{category,name,color} 的保存时先查后建。
// ★ 这一层不写库：本页底部的「保存」是这条链路上唯一的真保存。
const picked = ref([])
const showPicker = ref(false)
const note = ref('')
const manualText = ref(false)

const mediaHint = computed(() =>
  type.value === 'outfit'
    ? '图片（可选，可多选；一张全身照 = 这次穿搭的照，单品靠上面勾选选择）'
    : '图片（可选，可多选；iPhone 拍的 HEIC 会自动转）'
)
function thumbOf(p) {
  return itemThumb(p, api.mediaUrl)
}
function recentThumb(r) {
  return eventThumb(r, api.mediaUrl)
}
function categoryLabel(key) {
  return store.wardrobeCategoryLabel(key)
}
// 隐私模式：敏感单品在浏览态打码（与时间轴同一口径）
function itemLabel(it) {
  return store.privacyMode && it.sensitivity === 'sensitive' ? '●●●' : it.name
}
function openPicker() {
  if (!personId.value) {
    showToast('先选一个人')
    return
  }
  showPicker.value = true
}
function onPickConfirm(payload) {
  picked.value = (payload && payload.items) || []
  showPicker.value = false
  showToast(
    picked.value.length ? `已选 ${picked.value.length} 件，点「保存」才记下来` : '没有勾任何单品'
  )
}

const eventWhen = ref('')
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
// ---- 日期 / 时间（一个 datetime-local 输入，拆成日期与时刻）----
const eventDay = computed(() => splitLocal(eventWhen.value).date)
const eventTime = computed(() => splitLocal(eventWhen.value).time)
// 「今天」默认带上此刻（记的就是现在发生的事）；昨天/前天只到日、不带时间
function setToday() {
  eventWhen.value = toLocalInput(todayStr, nowLocalTime())
}
function setDate(v) {
  eventWhen.value = toLocalInput(v, '')
}
function setTime(v) {
  eventWhen.value = toLocalInput(eventDay.value, v)
}
// 保存成功后把时间刷新到此刻：否则连记两条会都用同一条旧时刻
function refreshTimeIfToday() {
  if (isToday.value) eventWhen.value = toLocalInput(todayStr, nowLocalTime())
}

const isToday = computed(() => eventDay.value === todayStr)
const isYesterday = computed(() => eventDay.value === shift(-1))
const isBeforeYesterday = computed(() => eventDay.value === shift(-2))

const dateHuman = computed(() => {
  if (!eventDay.value) return ''
  const d = new Date(eventDay.value + 'T00:00:00')
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')} ${WEEK[d.getDay()]}`
  return eventTime.value ? `${day} ${eventTime.value.slice(0, 5)}` : day
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

function fmt(r) {
  // 只记到日的记录不显示时间；记了时刻才显示 '10-12 14:03'
  const d = dayOf(r.event_date).slice(5)
  const t = fmtTime(r)
  return d ? (t ? `${d} ${t}` : d) : ''
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
        // captured_on 是 DATE 列：取日期部分
        captured_on: eventDay.value,
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
  // 穿搭草稿也要清：保存成功后不能把上一次的「已选」留在页面上
  picked.value = []
  note.value = ''
  manualText.value = false
}

async function submit() {
  if (!personId.value) {
    showToast('先选一个人')
    return
  }
  if (!eventDay.value) {
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
      setToday()
      return
    }
  }
  // 服装：没勾单品也能记，但衣橱是按单品聚合的 —— 先二次确认；
  // 「去选衣物」就直接把选择器打开，别让人回头找按钮
  if (type.value === 'outfit' && picked.value.length === 0) {
    try {
      await showConfirmDialog({
        title: '这次没有勾单品',
        message:
          '没有关联任何单品 → 衣橱里不会计入（穿次数/最近穿着都不会变），只在时间轴留一条记录。\n确定这样保存吗？',
        confirmButtonText: '就这样保存',
        cancelButtonText: '去选衣物',
      })
    } catch {
      openPicker()
      return
    }
  }
  saving.value = true
  try {
    const when = { event_date: eventDay.value, event_time: normalizeTime(eventTime.value) }
    const payload = {
      person_id: Number(personId.value),
      type_key: type.value,
      ...when,
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
    // ★ 服装走穿搭接口（1 条事件 + N 个单品引用，穿次数随之累加）；其它类型走通用事件接口
    const created =
      type.value === 'outfit'
        ? await api.createOutfit({
            person_id: Number(personId.value),
            ...when,
            items: toOutfitRefs(picked.value),
            note: note.value || null,
            tags: tags.value || null,
            // 手改过才提交标题/正文；没手改就让后端按单品渲染（单品才是真源）
            title: manualText.value ? title.value || null : null,
            body: manualText.value ? body.value || null : null,
            person_ids: extraIds.value.length
              ? [...new Set([Number(personId.value), ...extraIds.value])]
              : null,
          })
        : await api.createEvent(payload)
    const ok = await uploadPickedFiles((created && created.id) || null)
    const what = type.value === 'outfit' ? '穿搭' : ''
    if (ok === null) showToast(`已记录${what}`)
    else if (ok) showToast(`已记录${what}，含 ${ok} 张图片`)
    else showToast(`已记录${what}（图片未上传成功）`)
    resetContent()
    refreshTimeIfToday()   // 连记两条时，第二条的时间要是「此刻」而不是上一条的旧时刻
    await loadRecent()
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function loadRecent() {
  // ★ 按写入时间倒序（order=created），不是事件日期：记到过去某天的记录也得出现在「刚记的」里
  const res = await api.events({ person_id: personId.value, limit: 5, order: 'created' })
  recent.value = res.items || []
}

onMounted(async () => {
  eventWhen.value = toLocalInput(todayStr, nowLocalTime())
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
  border-radius: 8px;
  border: 1px solid #ebedf0;
  font-size: 14px;
}
/* 已选衣物：缩略图 + 名称（单品在衣橱里没挂照片时用类别色块占位） */
.picked-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.picked-item {
  width: 72px;
}
.picked-item img,
.picked-ph {
  width: 72px;
  height: 72px;
  border-radius: 8px;
  display: block;
  background: #f2f3f5;
  object-fit: cover;
}
.picked-ph {
  color: #969799;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.picked-name {
  font-size: 12px;
  color: #323233;
  margin-top: 2px;
  word-break: break-all;
}
/* 刚记的：每条一小块（人物 / 单品 chips / 首图） */
.recent + .recent {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f2f3f5;
}
.recent-title {
  font-size: 13px;
  margin: 2px 0 4px;
}
.recent-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.recent-meta .mini {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
}
/* 选择衣物弹层：内容自己滚，别让弹层撑破 */
.pick-wrap {
  height: 100%;
  padding: 12px;
  overflow-y: auto;
}
</style>
