<template>
  <div>
    <div class="card">
      <div class="chips">
        <van-tag
          v-for="t in filters"
          :key="t.key"
          :type="type === t.key ? 'primary' : 'default'"
          @click="setType(t.key)"
        >
          {{ t.label }}
        </van-tag>
      </div>
      <van-field v-model="from" type="date" label="从" />
      <van-field v-model="to" type="date" label="到" />
      <p class="muted" style="margin: 6px 0 0">
        显示：{{ scopeLabelText }}<template v-if="scopedFromQuery">（本页只看这个人）</template>
        <template v-else>（换人在首页）</template>
      </p>
    </div>

    <div class="card" v-for="e in items" :key="e.id">
      <div class="row">
        <span>
          <van-tag plain>{{ typeLabel(e.type_key) }}</van-tag>
          <span class="muted" style="margin-left: 6px">{{ e.event_date }}</span>
          <span class="muted" v-if="!singlePerson"> · {{ e.person_name || '—' }}</span>
        </span>
        <span class="acts">
          <span class="link" @click="openEdit(e)">编辑</span>
          <span class="danger" @click="remove(e)">删除</span>
        </span>
      </div>
      <div v-if="e.title"><strong>{{ e.title }}</strong></div>
      <!-- 穿搭：单品 chips（去重后的实体，不再是散落的单品事件） -->
      <div v-if="e.items && e.items.length" class="chips" style="margin-top: 6px">
        <van-tag v-for="it in e.items" :key="it.item_id" size="medium" plain>
          {{ itemLabel(it) }}<span v-if="it.color" class="muted"> · {{ it.color }}</span>
        </van-tag>
      </div>
      <div v-if="e.body" style="font-size: 13px; margin-top: 4px; white-space: pre-wrap">{{ e.body }}</div>
      <div v-if="e.media && e.media.length" class="thumbs">
        <template v-for="m in e.media" :key="m.id">
          <img
            v-if="m.kind !== 'video'"
            :src="api.mediaUrl(m)"
            loading="lazy"
            @click="openFull(m)"
          />
          <!-- 视频不能塞进 <img>（会变破图）：给个带 ▶ 的方块，点开看原片 -->
          <div v-else class="vthumb" @click="openFull(m)">▶</div>
        </template>
      </div>
      <div v-if="e.tags" class="chips" style="margin-top: 6px">
        <van-tag v-for="(t, i) in e.tags.split(',')" :key="i" plain>{{ t.trim() }}</van-tag>
      </div>
    </div>

    <van-empty v-if="!items.length" description="还没有记录" />
    <div class="muted" v-if="total > items.length" style="text-align: center">
      共 {{ total }} 条，已显示 {{ items.length }} 条
    </div>

    <!-- 编辑 -->
    <van-popup v-model:show="showEdit" position="bottom" round :style="{ height: '86%' }">
      <div class="edit" v-if="form">
        <div class="row">
          <h3 style="margin: 0">编辑记录 · {{ typeLabel(form.type_key) }}</h3>
          <span class="muted" @click="showEdit = false">关闭</span>
        </div>

        <van-field v-model="form.event_date" type="date" label="日期" />

        <!-- 穿搭：改的是「穿了哪几件」这个事实本身 -->
        <template v-if="form.type_key === 'outfit'">
          <!-- 已选（跨类别可见/可取消）：只在当前类别的 chip 上看勾选状态会让人找不到已选的那几件 -->
          <div class="chips" style="margin: 6px 0 0">
            <span class="muted">已选：</span>
            <van-tag
              v-for="p in editItems"
              :key="p.item_id"
              closable
              size="large"
              @click="unpick(p.item_id)"
            >
              {{ p.name }}<span v-if="p.color" class="muted">（{{ p.color }}）</span>
            </van-tag>
            <span v-if="!editItems.length && !newItems.length" class="muted">还没选任何单品</span>
          </div>
          <div class="chips" style="margin: 10px 0 6px">
            <van-tag
              v-for="c in store.wardrobeCategories"
              :key="c.key"
              :type="pickCategory === c.key ? 'primary' : 'default'"
              @click="pickCategory = c.key"
            >
              {{ c.label }}
            </van-tag>
          </div>
          <div class="chips" style="margin-bottom: 8px">
            <van-tag
              v-for="it in itemsOfCategory"
              :key="it.id"
              :type="isPicked(it.id) ? 'primary' : 'default'"
              size="large"
              @click="togglePick(it)"
            >
              {{ it.name }}<span class="muted"> · 穿{{ it.wear_count }}</span>
            </van-tag>
            <span v-if="!itemsOfCategory.length" class="muted">这个类别下还没有单品</span>
          </div>
          <van-field v-model="newName" label="新单品" placeholder="名称（类别取上面选中的）" />
          <van-field v-model="newColor" label="颜色" placeholder="可空" />
          <van-button size="small" plain style="margin-top: 6px" @click="addNew">＋ 加进来</van-button>
          <div class="chips" style="margin: 10px 0">
            <van-tag v-for="(n, i) in newItems" :key="i" closable size="large" @click="newItems.splice(i, 1)">
              {{ n.name }}<span v-if="n.color">（{{ n.color }}）</span>
            </van-tag>
          </div>
          <p class="muted">
            本次共 {{ editItems.length + newItems.length }} 件。保存后会按单品重算标题与正文；
            单品本身（穿几次、哪件）在衣橱页维护。
          </p>
          <van-cell title="手改标题 / 正文">
            <template #right-icon>
              <van-switch v-model="manualText" size="20" />
            </template>
          </van-cell>
          <template v-if="manualText">
            <van-field v-model="form.title" label="标题" />
            <van-field v-model="form.body" type="textarea" rows="3" autosize label="正文" />
          </template>
          <van-field v-model="form.tags" label="标签" placeholder="逗号分隔" />
        </template>

        <!-- 其他类型 -->
        <template v-else>
          <van-field v-model="form.title" :label="titleLabel(form.type_key)" />
          <van-field
            v-if="form.type_key !== 'period'"
            v-model="form.body"
            type="textarea"
            rows="3"
            autosize
            label="详细"
          />
          <van-field v-model="form.tags" label="标签" placeholder="逗号分隔" />
        </template>

        <template v-if="form.type_key === 'meeting'">
          <van-field v-model="form.location" label="地点" placeholder="在哪里" />
          <van-field v-model="form.hours" type="number" label="时长(小时)" placeholder="可留空" />
          <van-cell title="过夜">
            <template #right-icon>
              <van-switch v-model="form.overnight" size="20" />
            </template>
          </van-cell>
          <p class="muted">改日期/地点会同步「相处」明细，统计与「多久没见」不会错位。</p>
        </template>
        <p class="muted" v-if="form.type_key === 'period'">
          改日期会同步生理期明细；若目标日期已有记录会报冲突（不会静默失败）。
        </p>

        <!-- 图片：编辑时增删。事件已经存在 → 直接挂 event_id
             （记录页那边是「先建事件拿 id 再传」，这里不用绕那一圈） -->
        <div v-if="mediaVisible" class="media-edit">
          <div class="muted" style="margin-bottom: 6px">
            图片（可多选、可删、点开看原图；iPhone 拍的 HEIC 会自动转）
          </div>
          <div v-if="form.media.length" class="thumbs">
            <div v-for="m in form.media" :key="m.id" class="thumb-box">
              <img v-if="m.kind !== 'video'" :src="api.mediaUrl(m)" @click="openFull(m)" />
              <!-- 视频不能塞进 <img>（会变破图）：给个带 ▶ 的方块，点开看原片 -->
              <div v-else class="vthumb" @click="openFull(m)">▶</div>
              <span class="thumb-del" title="删掉这张" @click="removePhoto(m)">×</span>
            </div>
          </div>
          <van-uploader v-model="fileList" multiple :max-count="9" :preview-size="64" />
          <p class="muted">新选的图片在点「保存」时上传；删除已有图片立即生效。</p>
        </div>
        <p v-else-if="form.media.length" class="muted" style="margin-top: 10px">
          这个人没开「图片」模块 —— 已挂的 {{ form.media.length }} 张能看不能改。
        </p>

        <van-button block type="primary" style="margin-top: 12px" :loading="saving" @click="save">
          保存
        </van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { resolveScopedPerson } from '../lib/scope'

const store = useArchiveStore()
const route = useRoute()
const type = ref('')
const from = ref('')
const to = ref('')
const items = ref([])
const total = ref(0)
// 本页实际显示谁：优先 URL ?person（从个人页点进来），否则跟随全局；都不写回全局。
const scopedFromQuery = computed(() => !!resolveScopedPerson(route.query.person, null))
const effectivePersonId = computed(() =>
  resolveScopedPerson(route.query.person, store.currentPersonId)
)
const scopeLabelText = computed(() => {
  const id = effectivePersonId.value
  if (!id) return '全部'
  const p = store.persons.find((x) => x.id === id)
  return p ? store.displayName(p) : '全部'
})
const singlePerson = computed(() => !!effectivePersonId.value)

const filters = computed(() => [{ key: '', label: '全部' }, ...store.eventTypes])

// ---- 编辑 ----
const showEdit = ref(false)
const saving = ref(false)
const manualText = ref(false)
const form = ref(null)
const editItems = ref([])      // [{ item_id }] 这次穿搭引用的单品
const newItems = ref([])       // 编辑时现加的单品
const pickCategory = ref('top')
const newName = ref('')
const newColor = ref('')
const wardrobeItems = ref([])
const fileList = ref([])       // 编辑时新选、待「保存」才上传的图片

const itemsOfCategory = computed(() =>
  wardrobeItems.value.filter((i) => i.category === pickCategory.value && !i.merged_into_id)
)

// 图片区是否可编辑：该人「图片」模块已知关闭才隐藏（未知 = 加载中/失败 → 不隐藏，
// 与 lib/modules 的三态约定一致）
const mediaVisible = computed(
  () => store.hasModule(Number(form.value?.person_id), 'media') !== false
)

function typeLabel(key) {
  const t = store.eventTypes.find((x) => x.key === key)
  return t ? t.label : key
}

function titleLabel(key) {
  return (
    { text: '标题', health: '标题', mood: '标题', milestone: '标题', hobby: '标题',
      social: '标题', contact: '标题', period: '备注', meeting: '做了什么', gift: '标题',
      outfit: '标题' }[key] || '标题'
  )
}

// 隐私模式：敏感单品在浏览态打码（详情页/衣橱页打开后不打码）
function itemLabel(it) {
  return store.privacyMode && it.sensitivity === 'sensitive' ? '●●●' : it.name
}

async function load() {
  const res = await api.events({
    person_id: effectivePersonId.value || undefined,
    type_key: type.value || undefined,
    date_from: from.value || undefined,
    date_to: to.value || undefined,
    limit: 200,
  })
  items.value = res.items || []
  total.value = res.total || 0
}

function setType(k) {
  type.value = k
}

// ---- 编辑面板 ----
async function openEdit(e) {
  form.value = reactive({
    id: e.id,
    type_key: e.type_key,
    person_id: e.person_id,
    event_date: e.event_date,
    title: e.title || '',
    body: e.body || '',
    tags: e.tags || '',
    location: '',
    hours: '',
    overnight: false,
    // 列表接口已把媒体带回来了 → 直接用，不必再请求一次
    media: (e.media || []).map((m) => ({ ...m })),
  })
  manualText.value = false
  newItems.value = []
  newName.value = ''
  newColor.value = ''
  fileList.value = []
  editItems.value = (e.items || []).map((it) => ({
    item_id: it.item_id,
    category: it.category,
    name: it.name,
    color: it.color,
  }))
  showEdit.value = true
  // 图片区按这个人的「图片」模块门控 → 惰性拉一次（已缓存则直接命中，不重复请求）
  store.loadModulesFor(e.person_id)

  if (e.type_key === 'outfit') {
    // 编辑穿搭要能改「穿了哪几件」→ 拉这个人的单品清单
    try {
      const res = await api.wardrobeItems({ person_id: e.person_id })
      wardrobeItems.value = res.items || []
    } catch (err) {
      wardrobeItems.value = []
    }
  }
  if (e.type_key === 'meeting') {
    // 相处明细里的地点/时长/过夜（事件表不存这些，取明细回填）
    try {
      const rows = await api.interactions(e.person_id)
      const hit = (rows || []).find((r) => r.note === e.title) ||
        (rows || []).find((r) => r.occurred_on === e.event_date)
      if (hit) {
        form.value.location = hit.location || ''
        form.value.hours = hit.hours === null || hit.hours === undefined ? '' : String(hit.hours)
        form.value.overnight = !!hit.overnight
      }
    } catch {
      /* 明细取不到就不回填，保存时也不会覆盖 */
    }
  }
}

function isPicked(itemId) {
  return editItems.value.some((p) => p.item_id === itemId)
}
function togglePick(it) {
  const i = editItems.value.findIndex((p) => p.item_id === it.id)
  if (i >= 0) editItems.value.splice(i, 1)
  else editItems.value.push({ item_id: it.id, category: it.category, name: it.name, color: it.color })
}
function unpick(itemId) {
  const i = editItems.value.findIndex((p) => p.item_id === itemId)
  if (i >= 0) editItems.value.splice(i, 1)
}
function addNew() {
  const name = newName.value.trim()
  if (!name) {
    showToast('先填名称')
    return
  }
  newItems.value.push({ category: pickCategory.value, name, color: newColor.value || null })
  newName.value = ''
  newColor.value = ''
}

// ---- 图片（编辑时）----
// 删除已有图片是**立即**生效的（和相册页一致）；新选的图片等点「保存」才上传，
// 这样「取消编辑」不会往库里塞半截数据。
async function removePhoto(m) {
  try {
    await showConfirmDialog({ title: '删掉这张图片', message: '同时删除磁盘文件，确定？' })
  } catch {
    return
  }
  try {
    await api.deleteMedia(m.id)
  } catch (e) {
    showToast(e.message || '删除失败')
    return
  }
  form.value.media = form.value.media.filter((x) => x.id !== m.id)
  showToast('已删除')
  await load() // 时间轴那条记录上的缩略图也要跟着变
}

async function uploadPickedFiles(f) {
  if (!fileList.value.length) return 0
  let ok = 0
  for (const item of fileList.value) {
    const raw = item.file || item
    try {
      await api.uploadMedia(raw, {
        person_id: f.person_id || undefined,
        event_id: f.id,
        // ★ 用事件日期而不是「今天」：相册按拍摄日排序，用今天会把老照片排到最前面
        captured_on: f.event_date,
      })
      ok += 1
    } catch (e) {
      showToast(`${raw.name || '图片'} 上传失败：${e.message}`)
    }
  }
  fileList.value = []
  return ok
}

async function save() {
  const f = form.value
  if (!f.event_date) {
    showToast('先选日期')
    return
  }
  const patch = { event_date: f.event_date }
  if (f.type_key === 'outfit') {
    patch.items = [
      ...editItems.value.map((p) => ({ item_id: p.item_id })),
      ...newItems.value.map((n) => ({ category: n.category, name: n.name, color: n.color })),
    ]
    patch.tags = f.tags || null
    // 不手改就不提交标题/正文 → 后端按单品重算（单品才是真源）
    if (manualText.value) {
      patch.title = f.title || null
      patch.body = f.body || null
    }
  } else {
    patch.title = f.title || null
    patch.tags = f.tags || null
    if (f.type_key !== 'period') patch.body = f.body || null
    if (f.type_key === 'meeting') {
      patch.location = f.location || null
      patch.hours = f.hours === '' ? null : Number(f.hours)
      patch.overnight = f.overnight
    }
  }
  saving.value = true
  try {
    await api.patchEvent(f.id, patch)
    // 先改后传：万一编辑本身失败（如生理期日期冲突 409），不会留下已上传的孤儿图片
    const uploaded = await uploadPickedFiles(f)
    showToast(uploaded ? `已保存，含 ${uploaded} 张图片` : '已保存')
    showEdit.value = false
    await load()
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(e) {
  try {
    await showConfirmDialog({ title: '删除记录', message: `删除「${e.title || e.type_key}」？` })
  } catch {
    return
  }
  await api.deleteEvent(e.id)
  showToast('已删除')
  await load()
}

function openFull(m) {
  window.open(api.mediaUrl(m, false), '_blank')
}

watch([type, from, to, effectivePersonId], load)

// 内联编辑弹层打开时置共享的「正在编辑」态 —— App 据此隐藏底部 tabbar / 「＋记录」，
// 免得编辑时下面还叠着一层导航。关闭或离开本页都要复位（onUnmounted 兜底）。
watch(showEdit, (v) => store.setEditingRecord(v))
onUnmounted(() => store.setEditingRecord(false))

onMounted(load)
</script>

<style scoped>
.thumbs {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.thumbs img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 6px;
}
.vthumb {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  background: #ebedf0;
  color: #646566;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.media-edit {
  margin-top: 10px;
}
.thumb-box {
  position: relative;
  flex: 0 0 auto;
  width: 72px;
  height: 72px;
}
.thumb-box img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 6px;
  display: block;
}
/* 删除按钮要够大够好点（手机上 20px 的 × 点不中） */
.thumb-del {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  font-size: 16px;
  line-height: 24px;
  text-align: center;
  cursor: pointer;
}
.acts {
  display: flex;
  gap: 12px;
  flex: 0 0 auto;
}
.link {
  color: #1989fa;
  cursor: pointer;
}
.edit {
  padding: 14px;
  height: 100%;
  overflow-y: auto;
}
</style>
