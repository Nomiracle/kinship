<template>
  <div>
    <!-- 哪一天：跨零点防错（不是今天必须显式确认）。
         pick 模式下日期归记录页管（选择器只管选衣物，不碰日期） -->
    <div class="card" v-if="!pickMode">
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
      <p class="muted" style="margin: 8px 0 0" :class="{ warn: !isToday }">
        将记到：<strong>{{ dateHuman }}</strong>
        <span v-if="!isToday">（不是今天，请再确认一次）</span>
      </p>
    </div>

    <div class="card">
      <h3>这次穿了什么</h3>
      <div class="chips" style="margin-bottom: 6px">
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
          :type="isPicked(it) ? 'primary' : 'default'"
          size="large"
          @click="togglePick(it)"
        >
          {{ it.name }}<span class="muted"> · 穿{{ it.wear_count }}</span>
        </van-tag>
        <span v-if="!itemsOfCategory.length" class="muted">
          这个类别还没有单品 —— 在下面直接新建
        </span>
      </div>

      <van-field v-model="newName" label="新单品" :placeholder="'名称，如：' + pickCategoryLabel + '一件'" />
      <van-field v-model="newColor" label="颜色" placeholder="可空" />
      <van-button size="small" plain style="margin-top: 6px" @click="addNew">＋ 加进来</van-button>

      <!-- ★ 跨类别已选清单：切到别的类别也看得到、点一下就能取消。
           （分组勾选没有汇总行时，回过神就找不到自己勾了什么） -->
      <div v-if="pickedAll" class="picked-row">
        <div class="muted">已选 {{ pickedAll }} 件（点一下取消）：</div>
        <div class="chips" style="margin-top: 4px">
          <van-tag
            v-for="p in picked"
            :key="'i' + p.item_id"
            closable
            size="large"
            @click="unpick(p.item_id)"
          >
            {{ nameOf(p.item_id) }}
          </van-tag>
          <van-tag
            v-for="(n, i) in newItems"
            :key="'n' + i"
            closable
            size="large"
            @click="newItems.splice(i, 1)"
          >
            {{ n.name }}<span v-if="n.color">（{{ n.color }}）</span>
          </van-tag>
        </div>
      </div>

      <template v-if="!pickMode">
        <van-field v-model="location" label="地点" placeholder="如：家里（可空）" />
        <van-field v-model="note" label="备注" placeholder="这次穿搭的备注（可空）" />
      </template>
      <p class="muted" style="margin: 6px 0 0">
        本次选了 {{ pickedAll }} 件 —— 保存后只生成 1 条穿搭记录；同名单品会复用已有的，不会重复建。
      </p>

      <template v-if="!pickMode && others.length">
        <p class="muted" style="margin: 10px 0 4px">同时关联其他人（三人场合等，可多选）</p>
        <div class="chips">
          <van-tag
            v-for="p in others"
            :key="p.id"
            :type="extraIds.includes(p.id) ? 'primary' : 'default'"
            size="large"
            @click="toggleExtra(p.id)"
          >
            {{ store.displayName(p) }}
          </van-tag>
        </div>
      </template>

      <!-- 图片：记录页那条链路里，这次穿搭的照归记录页的图片区（保存后挂事件），
           pick 模式不重复放一个上传区 -->
      <div v-if="!pickMode" style="margin-top: 10px">
        <div class="muted" style="margin-bottom: 6px">
          图片（可选，可多选；一张全身照 = 这次穿搭的照，单品靠上面勾选关联，不用一件件单独拍）
        </div>
        <van-uploader v-model="fileList" multiple :max-count="9" :preview-size="64" />
      </div>

      <!-- pick 模式：只勾，不发任何请求；真正的保存由记录页的「保存」完成 -->
      <template v-if="pickMode">
        <p class="muted" style="margin: 10px 0 0">
          选好点「确定」回到记录页 —— 这时还**没有**记下来，记录页点「保存」才算真记。
        </p>
        <div style="display: flex; gap: 8px; margin-top: 10px">
          <van-button block plain @click="cancelPick">取消</van-button>
          <van-button block type="primary" @click="confirmPick">
            确定（已选 {{ pickedAll }} 件）
          </van-button>
        </div>
      </template>
      <van-button v-else block type="primary" style="margin-top: 12px" :loading="saving" @click="submit">
        保存
      </van-button>
    </div>
  </div>
</template>

<script setup>
// 穿搭记录面板：记录页（通用记事）与衣橱专有页共用这一份。
// 只有这里知道「单品怎么勾、失败模式是什么」，避免两份勾选 UI 各自腐化。
import { computed, onMounted, ref, watch } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'

const props = defineProps({
  personId: { type: Number, required: true },
  // 从单品详情「再穿一次」进来时预选这件，并自动切到它所在的类别
  preselect: { type: Array, default: () => [] },
  // 'save'（默认）= 衣橱侧的「立即记」：自带「保存」，点它就写库；
  // 'pick'         = 记录页的弹层选择器：只勾、不发请求，用「确定/取消」把草稿交回记录页
  mode: { type: String, default: 'save' },
  // pick 模式回显已有草稿：[{ item_id } | { category, name, color }]
  initial: { type: Array, default: () => [] },
})
const emit = defineEmits(['saved', 'confirm', 'cancel'])
// ★ 选择器模式绝不自己写库：这条链路上「保存」只有记录页那一个
const pickMode = computed(() => props.mode === 'pick')

const store = useArchiveStore()
const WEEK = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

// ---- 日期 ----
const todayStr = new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD（本地时区）
const eventDate = ref(todayStr)
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

// ---- 单品 ----
const wardrobeItems = ref([])
const pickCategory = ref('top')
const picked = ref([]) // [{ item_id }] —— 复用已有单品
const newItems = ref([]) // [{ category, name, color }] —— 没有就新建
const location = ref('')
const note = ref('')
const newName = ref('')
const newColor = ref('')
const fileList = ref([])
const extraIds = ref([])
const saving = ref(false)

const pickCategoryLabel = computed(() => store.wardrobeCategoryLabel(pickCategory.value))
const itemsOfCategory = computed(() =>
  wardrobeItems.value.filter((i) => i.category === pickCategory.value && !i.merged_into_id)
)
const pickedAll = computed(() => picked.value.length + newItems.value.length)
const others = computed(() => store.persons.filter((p) => p.id !== props.personId))

function nameOf(itemId) {
  const it = wardrobeItems.value.find((x) => x.id === itemId)
  return it ? it.name : '#' + itemId
}
function isPicked(it) {
  return picked.value.some((p) => p.item_id === it.id)
}
function togglePick(it) {
  const i = picked.value.findIndex((p) => p.item_id === it.id)
  if (i >= 0) picked.value.splice(i, 1)
  else
    picked.value.push({
      item_id: it.id,
      category: it.category,
      name: it.name,
      color: it.color,
      // 记录页的「已选」区要拿它显示缩略图（单品自己在衣橱里挂的照片）
      media: it.media || [],
    })
}
function unpick(itemId) {
  const i = picked.value.findIndex((p) => p.item_id === itemId)
  if (i >= 0) picked.value.splice(i, 1)
}
function toggleExtra(id) {
  const i = extraIds.value.indexOf(id)
  if (i >= 0) extraIds.value.splice(i, 1)
  else extraIds.value.push(id)
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

async function loadItems() {
  try {
    const res = await api.wardrobeItems({ person_id: props.personId })
    wardrobeItems.value = res.items || []
  } catch {
    wardrobeItems.value = []
  }
  applyPreselect()
  applyInitial()
}
function pushItem(it) {
  if (picked.value.some((p) => p.item_id === it.id)) return
  picked.value.push({
    item_id: it.id,
    category: it.category,
    name: it.name,
    color: it.color,
    // 记录页的「已选」区拿它显示缩略图
    media: it.media || [],
  })
}
// 预选：只认「这个人名下、还没合并」的单品，顺手把类别切过去让它可见
function applyPreselect() {
  const ids = (props.preselect || []).map(Number).filter(Boolean)
  if (!ids.length) return
  for (const id of ids) {
    const it = wardrobeItems.value.find((x) => x.id === id && !x.merged_into_id)
    if (!it) continue
    pushItem(it)
    pickCategory.value = it.category
  }
}
// pick 模式回显记录页已选的草稿：带 id 的从衣橱补全名称/照片，没 id 的（新单品）放回输入区
function applyInitial() {
  if (!pickMode.value) return
  for (const p of props.initial || []) {
    if (p && p.item_id) {
      const it = wardrobeItems.value.find((x) => x.id === p.item_id && !x.merged_into_id)
      if (it) pushItem(it)
      continue
    }
    if (p && p.name) {
      newItems.value.push({ category: p.category || 'other', name: p.name, color: p.color || null })
    }
  }
}
// 草稿 → 交给父级（记录页）。带 item_id 的走复用，没 id 的保存时先查后建（后端 resolve_refs）
function selection() {
  return [
    ...picked.value.map((p) => ({
      item_id: p.item_id,
      category: p.category,
      name: p.name,
      color: p.color || null,
      media: p.media || [],
    })),
    ...newItems.value.map((n) => ({
      category: n.category,
      name: n.name,
      color: n.color || null,
      media: [],
    })),
  ]
}
function confirmPick() {
  emit('confirm', { items: selection() })
}
function cancelPick() {
  emit('cancel')
}

function resetContent() {
  picked.value = []
  newItems.value = []
  note.value = ''
  location.value = ''
  newName.value = ''
  newColor.value = ''
  extraIds.value = []
  fileList.value = []
}

async function uploadPickedFiles(createdId) {
  if (!fileList.value.length) return null
  let ok = 0
  for (const item of fileList.value) {
    try {
      await api.uploadMedia(item.file || item, {
        person_id: props.personId,
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

async function submit() {
  if (!props.personId) {
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
  // 没勾单品照样能存，但衣橱是按单品聚合的 —— 只说一句，别让人事后找不到
  if (pickedAll.value === 0) {
    try {
      await showConfirmDialog({
        title: '这次没有勾单品',
        message:
          '没有关联任何单品 → 衣橱里不会计入（穿次数/最近穿着都不会变），只在时间轴留一条记录。\n确定这样保存吗？',
        confirmButtonText: '就这样保存',
        cancelButtonText: '回去勾单品',
      })
    } catch {
      return
    }
  }
  saving.value = true
  try {
    const items = [
      ...picked.value.map((p) => ({ item_id: p.item_id })),
      ...newItems.value.map((n) => ({ category: n.category, name: n.name, color: n.color })),
    ]
    const created = await api.createOutfit({
      person_id: props.personId,
      event_date: eventDate.value,
      items,
      note: note.value || null,
      location: location.value || null,
      person_ids: extraIds.value.length
        ? [...new Set([props.personId, ...extraIds.value])]
        : null,
    })
    const ok = await uploadPickedFiles(created.id)
    resetContent()
    await loadItems()
    emit('saved', created)
    const what = created.title ? `：${created.title}` : ''
    if (ok === null) showToast(`已记录穿搭${what}`)
    else if (ok) showToast(`已记录穿搭${what}，含 ${ok} 张图片`)
    else showToast('已记录穿搭（图片未上传成功）')
  } catch (e) {
    showToast(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (store.persons.length === 0) store.ensureLoaded()
  loadItems()
})
// 换人 / 换预选（从别的单品点「再穿一次」）都要重置并重拉
watch(
  [() => props.personId, () => (props.preselect || []).join(',')],
  async () => {
    resetContent()
    await loadItems()
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
.picked-row {
  margin: 10px 0;
  padding: 8px;
  background: #f7f8fa;
  border-radius: 8px;
}
</style>
