<template>
  <div>
    <!-- 顶栏：显示谁 + 去重入口 -->
    <div class="card">
      <div class="row">
        <span class="muted">显示：{{ scopeLabelText }}（换人在首页）</span>
        <span class="muted">共 {{ items.length }} 件</span>
      </div>
      <div class="chips" style="margin-top: 8px">
        <van-tag
          :type="category ? 'default' : 'primary'"
          size="large"
          @click="category = ''"
        >
          全部
        </van-tag>
        <van-tag
          v-for="c in store.wardrobeCategories"
          :key="c.key"
          :type="category === c.key ? 'primary' : 'default'"
          size="large"
          @click="category = c.key"
        >
          {{ c.label }}
        </van-tag>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        一件衣服只存一条；反复穿会累加「穿过 N 次」，不再重复记事件。
      </p>
    </div>

    <!-- 去重：候选清单（只出候选，合并要你点） -->
    <div class="card" v-if="dupGroups.length">
      <div class="row">
        <h3 style="margin: 0">疑似重复 {{ dupGroups.length }} 组</h3>
        <span class="muted" @click="showDup = !showDup">{{ showDup ? '收起' : '展开' }}</span>
      </div>
      <div v-if="showDup">
        <div v-for="(g, i) in dupGroups" :key="i" class="dup">
          <div class="muted">
            {{ g.confidence === 'high' ? '确定重复' : '疑似同一件' }} · {{ g.reason }} ·
            {{ store.wardrobeCategoryLabel(g.category) }}
          </div>
          <div class="row" v-for="it in g.items" :key="it.id">
            <span>
              {{ label(it) }}
              <span class="muted">· 穿过 {{ it.wear_count }} 次</span>
            </span>
            <span
              v-if="it.id !== g.items[0].id"
              class="link"
              @click="merge(it.id, g.items[0].id, it, g.items[0])"
            >
              并到「{{ label(g.items[0]) }}」
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 单品列表（按类别分组） -->
    <div class="card" v-for="g in groups" :key="g.key">
      <h3>{{ g.label }}（{{ g.items.length }}）</h3>
      <div class="row item" v-for="it in g.items" :key="it.id" @click="open(it)">
        <span class="name">
          <span class="dot" :style="{ background: colorCss(it.color) }"></span>
          {{ label(it) }}
          <span v-if="it.merged_into_id" class="muted">（已合并）</span>
        </span>
        <span class="muted">
          穿 {{ it.wear_count }} 次<span v-if="it.last_worn_on"> · 最近 {{ human(it.last_worn_on) }}</span>
        </span>
      </div>
    </div>

    <van-empty v-if="!items.length" description="还没有单品：去「记录」页记一次穿搭，或在这里新建" />

    <!-- 新建单品 -->
    <div class="card">
      <h3>新建单品</h3>
      <van-field v-model="nName" label="名称" placeholder="如：黑色阔腿裤" />
      <van-field v-model="nColor" label="颜色" placeholder="如：黑色（可空）" />
      <van-field label="类别">
        <template #input>
          <select v-model="nCategory" class="picker">
            <option v-for="c in store.wardrobeCategories" :key="c.key" :value="c.key">
              {{ c.label }}
            </option>
          </select>
        </template>
      </van-field>
      <van-button block type="primary" size="small" style="margin-top: 8px" @click="create">
        新建
      </van-button>
      <p class="muted" style="margin: 8px 0 0">
        同一个人 + 同类别 + 同名 + 同色 建不出第二条（会提示复用已有的）。
      </p>
    </div>

    <!-- 单品详情 -->
    <van-popup v-model:show="showDetail" position="bottom" round :style="{ height: '82%' }">
      <div class="detail" v-if="detail">
        <div class="row">
          <h3 style="margin: 0">{{ label(detail) }}</h3>
          <span class="muted" @click="showDetail = false">关闭</span>
        </div>
        <p class="muted">
          穿过 {{ detail.wear_count }} 次
          <span v-if="detail.first_worn_on"> · 首次 {{ detail.first_worn_on }}</span>
          <span v-if="detail.last_worn_on"> · 最近 {{ detail.last_worn_on }}</span>
        </p>

        <van-field v-model="edit.name" label="名称" />
        <van-field v-model="edit.color" label="颜色" />
        <van-field v-model="edit.tags" label="标签" placeholder="逗号分隔，如：露肩,格子" />
        <van-field v-model="edit.notes" label="备注" type="textarea" rows="2" autosize />
        <van-field label="类别">
          <template #input>
            <select v-model="edit.category" class="picker">
              <option v-for="c in store.wardrobeCategories" :key="c.key" :value="c.key">
                {{ c.label }}
              </option>
            </select>
          </template>
        </van-field>
        <div class="chips" style="margin-top: 8px">
          <van-button size="small" type="primary" @click="save">保存</van-button>
          <van-button size="small" @click="pickMerge = true">合并到…</van-button>
          <van-button size="small" @click="toggleActive">
            {{ detail.active ? '停用' : '恢复' }}
          </van-button>
          <van-button v-if="detail.merged_into_id" size="small" type="warning" @click="unmerge">
            撤销合并
          </van-button>
          <van-button size="small" type="danger" @click="remove">删除</van-button>
        </div>

        <h4>照片</h4>
        <div class="thumbs">
          <img v-for="m in detail.media" :key="m.id" :src="api.mediaUrl(m)" />
        </div>
        <van-uploader :after-read="upload" :max-count="1" style="margin-top: 6px">
          <van-button size="small" plain>＋ 上传照片</van-button>
        </van-uploader>

        <h4>穿着历史（{{ detail.wears.length }}）</h4>
        <div v-for="w in detail.wears" :key="w.event_id" class="wear">
          <div class="row">
            <span>
              {{ w.event_date }}
              <span class="muted">· {{ slotLabel(w.slot) }}</span>
            </span>
            <span class="muted">
              {{ (w.together || []).length ? '和 ' + w.together.join('、') : '单独' }}
            </span>
          </div>
          <div v-if="w.note" class="muted">备注：{{ w.note }}</div>
        </div>
        <van-empty v-if="!detail.wears.length" description="还没穿过（或只是「提起过」）" />
      </div>
    </van-popup>

    <!-- 合并目标选择 -->
    <van-popup v-model:show="pickMerge" position="bottom" round :style="{ height: '60%' }">
      <div class="detail">
        <h3>把「{{ label(detail) }}」合并到</h3>
        <p class="muted">穿着记录会改挂到目标单品，源单品标记作废（可撤销）。</p>
        <div class="row" v-for="it in mergeCandidates" :key="it.id" @click="merge(detail.id, it.id, detail, it)">
          <span>{{ label(it) }}</span>
          <span class="muted">穿 {{ it.wear_count }} 次</span>
        </div>
        <van-empty v-if="!mergeCandidates.length" description="同类别里没有别的单品" />
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { resolveScopedPerson } from '../lib/scope'

const store = useArchiveStore()
const route = useRoute()
// 衣橱实际显示谁：优先 URL ?person（从个人页点进来），否则跟随全局；不写回全局。
const effectivePersonId = computed(() =>
  resolveScopedPerson(route.query.person, store.currentPersonId)
)
const scopeLabelText = computed(() => {
  const id = effectivePersonId.value
  if (!id) return '全部'
  const p = store.persons.find((x) => x.id === id)
  return p ? store.displayName(p) : '全部'
})
const items = ref([])
const dupGroups = ref([])
const category = ref('')
const showDup = ref(true)
const showDetail = ref(false)
const pickMerge = ref(false)
const detail = ref(null)
const edit = reactive({ name: '', color: '', tags: '', notes: '', category: 'other' })
const nName = ref('')
const nColor = ref('')
const nCategory = ref('top')

const COLORS = {
  黑色: '#222', 白色: '#fff', 灰色: '#bbb', 蓝色: '#3b6fd4', 棕色: '#8b5a2b',
  绿色: '#3aa76d', 红色: '#e03e3e', 粉色: '#f06292', 紫色: '#8e5bd8', 金色: '#d4af37',
  米色: '#e8d9b5', 银色: '#c0c6cc',
}

function colorCss(color) {
  if (!color) return '#e5e5e5'
  for (const k of Object.keys(COLORS)) if (color.includes(k) || k.includes(color)) return COLORS[k]
  return '#e5e5e5'
}
function label(it) {
  if (!it) return ''
  return store.privacyMode && it.sensitivity === 'sensitive' ? '●●●' : it.name
}
function slotLabel(slot) {
  const map = { top: '上身', bottom: '下身', outer: '外套', dress: '裙装', shoes: '鞋', accessory: '配饰', bag: '包', other: '其他' }
  return map[slot] || slot
}
function human(d) {
  if (!d) return ''
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d + 'T00:00:00')) / 86400000)
  if (days <= 0) return '今天'
  if (days === 1) return '昨天'
  return days + ' 天前'
}

const groups = computed(() =>
  store.wardrobeCategories
    .map((c) => ({ ...c, items: items.value.filter((i) => i.category === c.key && (!category.value || category.value === c.key)) }))
    .filter((g) => g.items.length)
)
const mergeCandidates = computed(() => {
  if (!detail.value) return []
  return items.value.filter((i) => i.category === detail.value.category && i.id !== detail.value.id && !i.merged_into_id)
})

async function load() {
  const personId = effectivePersonId.value || undefined
  // 并发：两件事互不依赖，慢链路上少一个往返
  const [res, dup] = await Promise.all([
    api.wardrobeItems({
      person_id: personId,
      include_merged: true,
    }),
    api.wardrobeDuplicates(personId),
  ])
  items.value = res.items || []
  dupGroups.value = dup.groups || []
}

async function open(it) {
  detail.value = await api.wardrobeItem(it.id)
  Object.assign(edit, {
    name: detail.value.name,
    color: detail.value.color || '',
    tags: detail.value.tags || '',
    notes: detail.value.notes || '',
    category: detail.value.category,
  })
  showDetail.value = true
}

async function save() {
  try {
    await api.patchWardrobeItem(detail.value.id, {
      name: edit.name,
      color: edit.color || null,
      tags: edit.tags || null,
      notes: edit.notes || null,
      category: edit.category,
    })
    showToast('已保存')
    showDetail.value = false
    await load()
  } catch (e) {
    showToast(e.message)
  }
}

async function toggleActive() {
  await api.patchWardrobeItem(detail.value.id, { active: !detail.value.active })
  showToast(detail.value.active ? '已停用' : '已恢复')
  showDetail.value = false
  await load()
}

async function remove() {
  try {
    await showConfirmDialog({ title: '删除单品', message: `删除「${detail.value.name}」？` })
  } catch {
    return
  }
  try {
    await api.deleteWardrobeItem(detail.value.id)
    showToast('已删除')
  } catch (e) {
    showToast(e.message)
  }
  showDetail.value = false
  await load()
}

async function merge(srcId, intoId, src, dst) {
  try {
    await showConfirmDialog({
      title: '合并单品',
      message: `把「${src.name}」并到「${dst.name}」？\n穿着记录会合到一起，源单品作废（可撤销）。`,
    })
  } catch {
    return
  }
  const res = await api.mergeWardrobeItem(srcId, intoId)
  showToast(`已合并，转移 ${res.moved_wears} 条穿着记录`)
  pickMerge.value = false
  showDetail.value = false
  await load()
}

async function unmerge() {
  await api.unmergeWardrobeItem(detail.value.id)
  showToast('已撤销合并')
  showDetail.value = false
  await load()
}

async function create() {
  if (!nName.value.trim()) {
    showToast('先填名称')
    return
  }
  if (!effectivePersonId.value) {
    showToast('先在首页选一个人（单品要挂在人下面）')
    return
  }
  try {
    await api.createWardrobeItem({
      person_id: effectivePersonId.value,
      category: nCategory.value,
      name: nName.value.trim(),
      color: nColor.value || null,
    })
    showToast('已新建')
    nName.value = ''
    nColor.value = ''
    await load()
  } catch (e) {
    showToast(e.message)
  }
}

async function upload(file) {
  const raw = file.file || file
  try {
    await api.uploadMedia(raw, {
      person_id: detail.value.person_id,
      wardrobe_item_id: detail.value.id,
      captured_on: new Date().toLocaleDateString('sv-SE'),
    })
    showToast('已上传')
    detail.value = await api.wardrobeItem(detail.value.id)
  } catch (e) {
    showToast(e.message)
  }
}

watch(effectivePersonId, () => load())

onMounted(async () => {
  await store.ensureLoaded()
  await load()
})
</script>

<style scoped>
.item {
  cursor: pointer;
}
.name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid #dcdee0;
  display: inline-block;
}
.dup {
  border-top: 1px solid #f2f3f5;
  padding-top: 6px;
  margin-top: 6px;
}
.link {
  color: #1989fa;
  font-size: 12px;
}
.detail {
  padding: 14px;
  overflow-y: auto;
  height: 100%;
}
.detail h4 {
  margin: 14px 0 6px;
  font-size: 13px;
}
.thumbs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.thumbs img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 6px;
}
.picker {
  width: 100%;
  padding: 6px;
  border: 1px solid #ebedf0;
  border-radius: 6px;
  background: #fff;
  font-size: 14px;
}
</style>
