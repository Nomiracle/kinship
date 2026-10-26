<template>
  <div>
    <!-- 顶栏：显示谁 + 主操作 -->
    <div class="card">
      <div class="row">
        <span class="muted">显示：{{ scopeLabelText }}（可在顶部切换）</span>
        <span class="muted">共 {{ filteredItems.length }} / {{ items.length }} 件</span>
      </div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <van-button block type="primary" size="small" @click="goAdd">＋ 添加衣物</van-button>
        <van-button block plain size="small" @click="goRecord()">＋ 记一次穿着（今天）</van-button>
      </div>
      <p class="muted" style="margin: 8px 0 0">衣物为长期档案，新增不自动创建穿搭；照片挂在单品上。</p>
    </div>

    <!-- 筛选：搜索 / 类别 / 颜色 / 无记录 / 视图切换 -->
    <div class="card">
      <van-field v-model="q" placeholder="搜索 名称/颜色/标签/备注" clearable left-icon="search" />
      <div class="chips" style="margin-top: 8px">
        <van-tag :type="!category ? 'primary' : 'default'" size="large" @click="category = ''">全部</van-tag>
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
      <div v-if="availableColors.length" class="chips" style="margin-top: 8px">
        <van-tag :type="!colorFilter ? 'primary' : 'default'" size="small" @click="colorFilter = ''">全部颜色</van-tag>
        <van-tag
          v-for="col in availableColors"
          :key="col"
          :type="colorFilter === col ? 'primary' : 'default'"
          size="small"
          @click="colorFilter = colorFilter === col ? '' : col"
        >
          <span class="dot" :style="{ background: colorCss(col) }"></span> {{ col }}
        </van-tag>
      </div>
      <div class="row" style="margin-top:8px">
        <label class="muted" style="display:flex;align-items:center;gap:6px">
          <input type="checkbox" v-model="onlyNoHistory" /> 仅看暂无穿着记录
        </label>
        <span class="muted" @click="viewMode = viewMode === 'grid' ? 'list' : 'grid'">{{ viewMode === 'grid' ? '切换列表' : '切换网格' }}</span>
      </div>
      <div class="chips" style="margin-top: 8px">
        <van-tag
          v-for="s in statusScopes"
          :key="s.key"
          :type="statusScope === s.key ? 'primary' : 'default'"
          size="small"
          @click="statusScope = s.key"
        >{{ s.label }}</van-tag>
      </div>
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

    <!-- 照片优先：网格 / 列表 -->
    <div v-if="viewMode === 'grid' && filteredGroups.length" class="grid-wrap">
      <div v-for="g in filteredGroups" :key="g.key" class="grid-group">
        <h3>{{ g.label }}（{{ g.items.length }}）</h3>
        <div class="grid">
          <div v-for="it in g.items" :key="it.id" class="grid-card" @click="open(it)">
            <div class="thumb">
              <img v-if="thumbUrl(it)" :src="thumbUrl(it)" loading="lazy" />
              <span v-else class="thumb-ph">{{ g.label.slice(0,1) }}</span>
            </div>
            <div class="grid-meta">
              <span class="name"><span class="dot" :style="{ background: colorCss(it.color) }"></span> {{ label(it) }}</span>
              <span class="muted" style="font-size:11px">穿 {{ it.wear_count }} 次<span v-if="it.last_worn_on"> · 最近 {{ human(it.last_worn_on) }}</span><span v-else> · 暂无穿着记录</span></span>
            </div>
            <span v-if="it.status && it.status !== 'in_use'" class="muted" style="font-size:11px">（{{ statusLabel(it) }}）</span>
            <span v-if="it.merged_into_id" class="muted" style="font-size:11px">（已合并）</span>
          </div>
        </div>
      </div>
    </div>

    <template v-if="viewMode === 'list'">
      <div class="card" v-for="g in filteredGroups" :key="g.key">
        <h3>{{ g.label }}（{{ g.items.length }}）</h3>
        <div class="row item" v-for="it in g.items" :key="it.id" @click="open(it)">
          <span class="name">
            <img v-if="thumbUrl(it)" :src="thumbUrl(it)" class="list-thumb" />
            <span v-else class="list-thumb ph">{{ g.label.slice(0,1) }}</span>
            <span class="dot" :style="{ background: colorCss(it.color) }"></span>
            {{ label(it) }}
            <span v-if="it.status && it.status !== 'in_use'" class="muted">（{{ statusLabel(it) }}）</span>
            <span v-if="it.merged_into_id" class="muted">（已合并）</span>
          </span>
          <span class="muted">
            穿 {{ it.wear_count }} 次<span v-if="it.last_worn_on"> · 最近 {{ human(it.last_worn_on) }}</span><span v-else> · 暂无穿着记录</span>
          </span>
        </div>
      </div>
    </template>

    <van-empty v-if="!filteredItems.length" :description="items.length ? '无匹配单品' : '还没有单品：点上面的「＋ 添加衣物」'" />

    <!-- 单品详情 -->
    <van-popup v-model:show="showDetail" position="bottom" round class="wardrobe-detail" :style="{ height: '82%' }">
      <div class="detail" v-if="detail">
        <div class="row">
          <h3 style="margin: 0">{{ label(detail) }}</h3>
          <span class="muted" @click="showDetail = false">关闭</span>
        </div>
        <p class="muted">
          穿过 {{ detail.wear_count }} 次
          <span v-if="detail.first_worn_on"> · 首次 {{ detail.first_worn_on }}</span>
          <span v-if="detail.last_worn_on"> · 最近 {{ detail.last_worn_on }}</span>
          <span v-else> · 暂无穿着记录</span>
        </p>

        <dl class="item-summary">
          <dt>类别</dt><dd>{{ store.wardrobeCategoryLabel(detail.category) }}</dd>
          <dt>颜色</dt><dd>{{ detail.color || '未填写' }}</dd>
          <dt>状态</dt><dd>{{ statusLabel(detail) }}<span v-if="detail.status_reason" class="muted"> · {{ detail.status_reason }}</span><span v-if="detail.status_changed_on" class="muted"> · {{ detail.status_changed_on }}</span></dd>
          <dt>加入衣橱</dt><dd>{{ formatAdded(detail) || '未记录' }}</dd>
          <dt>标签</dt><dd>{{ detail.tags || '未填写' }}</dd>
          <dt>备注</dt><dd>{{ detail.notes || '未填写' }}</dd>
          <dt v-if="detail.replaces">替代了</dt><dd v-if="detail.replaces"><span class="link" @click="open({ id: detail.replaces.id })">{{ detail.replaces.name }}</span>（{{ detail.replaces.status_label }}）</dd>
          <dt v-if="(detail.replaced_by || []).length">被替代</dt>
          <dd v-if="(detail.replaced_by || []).length">
            <span v-for="(r, i) in detail.replaced_by" :key="r.id"><span v-if="i">、</span><span class="link" @click="open({ id: r.id })">{{ r.name }}</span>（{{ r.status_label }}）</span>
          </dd>
        </dl>
        <div class="chips" style="margin-top: 8px">
          <van-button size="small" type="primary" plain @click="goRecord(detail.id)">
            ＋ 再穿一次（今天）
          </van-button>
          <van-button size="small" plain @click="goEdit(detail.id)">编辑页</van-button>
          <van-button size="small" type="warning" @click="openStatus">改状态</van-button>
          <van-button size="small" @click="pickMerge = true">合并到…</van-button>
          <van-button v-if="detail.merged_into_id" size="small" type="warning" @click="unmerge">
            撤销合并
          </van-button>
          <van-button size="small" type="danger" @click="remove">删除</van-button>
        </div>

        <h4>状态变更（{{ (detail.status_history || []).length }}）</h4>
        <div v-for="h in detail.status_history || []" :key="h.id" class="wear">
          <div class="row">
            <span>{{ h.effective_on || h.created_at || '日期未记' }}</span>
            <span class="muted">{{ h.status_label }}</span>
          </div>
          <div v-if="h.reason" class="muted">原因：{{ h.reason }}</div>
        </div>
        <p v-if="!(detail.status_history || []).length" class="muted">暂无状态变更记录</p>

        <h4>照片</h4>
        <div class="thumbs">
          <template v-for="m in detail.media" :key="m.id">
            <img v-if="m.kind !== 'video'" :src="api.mediaUrl(m)" @click="openFull(m, detailPhotos)" />
            <a v-else class="video-ph" :href="api.mediaUrl(m, false)" target="_blank">▶</a>
          </template>
        </div>
        <van-button size="small" plain @click="goEdit(detail.id)">＋ 添加照片</van-button>

        <h4>穿着历史（{{ detail.wears.length }}）</h4>
        <div v-for="w in detail.wears" :key="w.event_id" class="wear">
          <div class="row">
            <span>
              {{ fmtWhen(w) }}
              <span class="muted">· {{ slotLabel(w.slot) }}</span>
            </span>
            <span class="muted">
              {{ (w.together || []).length ? '和 ' + w.together.join('、') : '单独' }}
            </span>
          </div>
          <div v-if="w.note" class="muted">备注：{{ w.note }}</div>
          <div v-if="(w.media || []).length" class="thumbs" style="margin-top: 6px">
            <template v-for="m in w.media" :key="m.id">
              <img v-if="m.kind === 'image'" :src="api.mediaUrl(m)" @click="openFull(m, detailPhotos)" />
              <a v-else class="video-ph" :href="api.mediaUrl(m, false)" target="_blank">▶</a>
            </template>
          </div>
        </div>
        <van-empty v-if="!detail.wears.length" description="暂无穿着记录" />
      </div>
    </van-popup>

    <van-popup v-model:show="showStatus" position="bottom" round :style="{ height: '62%' }">
      <div class="detail">
        <h3>改状态 · {{ label(detail) }}</h3>
        <p class="muted">当前：{{ statusLabel(detail) }}<span v-if="detail?.status_reason"> · {{ detail.status_reason }}</span></p>
        <div class="chips" style="margin-top: 8px">
          <van-tag
            v-for="s in STATUS_OPTIONS"
            :key="s.key"
            :type="statusForm.status === s.key ? 'primary' : 'default'"
            size="large"
            @click="statusForm.status = s.key"
          >{{ s.label }}</van-tag>
        </div>
        <van-field
          v-model="statusForm.reason"
          label="原因"
          type="textarea"
          rows="2"
          autosize
          maxlength="255"
          show-word-limit
          :placeholder="statusReasonHint"
        />
        <van-field label="生效日期">
          <template #input>
            <input v-model="statusForm.date" type="date" class="picker" />
          </template>
        </van-field>
        <p class="muted">已卖出/送人/丢失等离手状态必须写一句原因；「换成了哪几件」在新件的编辑页里选「替代了哪件」。</p>
        <div style="display:flex;gap:8px;margin-top:10px">
          <van-button block plain @click="showStatus = false">取消</van-button>
          <van-button block type="primary" :loading="savingStatus" @click="saveStatus">保存状态</van-button>
        </div>
        <p v-if="statusError" class="danger" style="margin:6px 0 0">{{ statusError }}</p>
      </div>
    </van-popup>

    <van-image-preview
      v-model:show="preview.show"
      :images="preview.images"
      :start-position="preview.index"
    />

    <van-popup v-model:show="pickMerge" position="bottom" round :style="{ height: '60%' }">
      <div class="detail">
        <h3>把「{{ label(detail) }}」合并到</h3>
        <p class="muted">穿着记录会改挂到目标单品，源单品标记作废。撤销合并只恢复标记，穿着记录不会自动拆回。</p>
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
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { resolveScopedPerson, scopeQuery } from '../lib/scope'
import { previewUrls } from '../lib/media-preview'
import { fmtWhen } from '../lib/event-day'
import { filterWardrobeItems, collectColors } from '../lib/wardrobe-create'
import {
  STATUS_OPTIONS,
  buildStatusPatch,
  filterByStatusScope,
  formatAdded,
  statusLabel,
  validateStatusChange,
} from '../lib/status'

const store = useArchiveStore()
const route = useRoute()
const router = useRouter()
const effectivePersonId = computed(() =>
  resolveScopedPerson(route.query.person, store.currentPersonId)
)
const rawPersonQuery = computed(() => route.query.person)
function navQuery() {
  if (rawPersonQuery.value === 'all') return { person: 'all' }
  // preserve explicit all, otherwise follow effective scope
  return scopeQuery(effectivePersonId.value)
}
const scopeLabelText = computed(() => {
  const id = effectivePersonId.value
  if (!id) return '全部'
  const p = store.persons.find((x) => x.id === id)
  return p ? store.displayName(p) : '全部'
})
const items = ref([])
const dupGroups = ref([])
const category = ref('')
const colorFilter = ref('')
const q = ref('')
const onlyNoHistory = ref(false)
const viewMode = ref('grid')
const showDup = ref(true)
const showDetail = ref(false)
const pickMerge = ref(false)
const detail = ref(null)

// 状态范围：默认只看「在手」；已离手要显式切过去（列表不刷新，纯前端过滤）
const statusScope = ref('hand')
const statusScopes = [
  { key: 'hand', label: '在手' },
  { key: 'in_use', label: '在役' },
  { key: 'idle', label: '闲置' },
  { key: 'offhand', label: '已离手' },
  { key: 'all', label: '全部' },
]
const showStatus = ref(false)
const savingStatus = ref(false)
const statusError = ref('')
const statusForm = reactive({ status: 'in_use', reason: '', date: '' })
const statusReasonHint = computed(() =>
  statusForm.status === 'sold' ? '如：闲鱼卖掉，换了新项链和戒指' : '为什么变成这个状态（离手必填）'
)


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

function thumbUrl(it) {
  const m = (it.media || []).find((x) => x.kind !== 'video')
  return m ? api.mediaUrl(m, true) : ''
}

const filteredItems = computed(() =>
  filterWardrobeItems(filterByStatusScope(items.value, statusScope.value), {
    category: category.value,
    color: colorFilter.value,
    q: q.value,
    onlyNoHistory: onlyNoHistory.value,
  })
)

const filteredGroups = computed(() =>
  store.wardrobeCategories
    .map((c) => ({ ...c, items: filteredItems.value.filter((i) => i.category === c.key) }))
    .filter((g) => g.items.length)
)

const availableColors = computed(() => collectColors(items.value))

const detailPhotos = computed(() => [
  ...(detail.value?.media || []),
  ...(detail.value?.wears || []).flatMap((w) => w.media || []),
])

const preview = reactive({ show: false, images: [], index: 0 })

function openFull(m, list) {
  const p = previewUrls(list && list.length ? list : [m], m, api.mediaUrl)
  preview.images = p.images
  preview.index = p.index
  preview.show = true
}

const mergeCandidates = computed(() => {
  if (!detail.value) return []
  return items.value.filter((i) => i.person_id === detail.value.person_id && i.category === detail.value.category && i.id !== detail.value.id && !i.merged_into_id)
})

function goAdd() {
  const q2 = navQuery()
  router.push({ path: '/wardrobe/items/new', query: q2 })
}
function goEdit(id) {
  const q2 = navQuery()
  router.push({ path: `/wardrobe/items/${id}/edit`, query: q2 })
}
function goRecord(itemId) {
  const q2 = navQuery()
  if (itemId) { q2.item = itemId; q2.person=detail.value?.person_id || effectivePersonId.value || 'all' }
  router.push({ path: '/wardrobe/new', query: q2 })
}

async function load() {
  const personId = effectivePersonId.value || undefined
  const [res, dup] = await Promise.all([
    api.wardrobeItems({
      person_id: personId,
      include_merged: true,
      // 一次拿全（含已离手），状态切换纯前端过滤 —— 少一趟请求，且旧件不「消失」
      include_offhand: true,
    }),
    api.wardrobeDuplicates(personId),
  ])
  items.value = res.items || []
  dupGroups.value = dup.groups || []
}

async function open(it) {
  detail.value = await api.wardrobeItem(it.id)
  showDetail.value = true
}

function openStatus() {
  statusError.value = ''
  statusForm.status = detail.value?.status || 'in_use'
  statusForm.reason = detail.value?.status_reason || ''
  statusForm.date = detail.value?.status_changed_on || new Date().toLocaleDateString('sv-SE')
  showStatus.value = true
}

async function saveStatus() {
  if (savingStatus.value || !detail.value) return
  const err = validateStatusChange({ status: statusForm.status, reason: statusForm.reason })
  if (err) {
    statusError.value = err
    return
  }
  statusError.value = ''
  savingStatus.value = true
  try {
    const patch = buildStatusPatch({
      status: statusForm.status,
      reason: statusForm.reason,
      date: statusForm.date,
    })
    await api.patchWardrobeItem(detail.value.id, patch)
    showToast('状态已更新')
    showStatus.value = false
    const id = detail.value.id
    showDetail.value = false
    await load()
    detail.value = await api.wardrobeItem(id)
    showDetail.value = true
  } catch (e) {
    statusError.value = e.message || '保存失败'
  } finally {
    savingStatus.value = false
  }
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
      message: `把「${src.name}」并到「${dst.name}」？\n穿着记录会合到一起，源单品作废。撤销合并只恢复标记，穿着记录不会自动拆回。`,
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
  try {
    await showConfirmDialog({
      title: '撤销合并',
      message: '撤销合并只恢复“已合并”标记，穿着记录不会自动拆回。如需还原请手动调整。确定撤销？',
    })
  } catch {
    return
  }
  await api.unmergeWardrobeItem(detail.value.id)
  showToast('已撤销合并（穿着记录未拆回）')
  showDetail.value = false
  await load()
}

watch(effectivePersonId, () => load())

onMounted(async () => {
  await store.ensureLoaded()
  await load()
})
</script>

<style scoped>
.item-summary {display:grid;grid-template-columns:60px 1fr;gap:10px;font-size:14px}.item-summary dt{color:var(--muted)}.item-summary dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
@media(min-width:1000px){.wardrobe-detail{width:48%!important;left:auto!important;right:0;top:var(--topbar-h);bottom:0;height:calc(100% - var(--topbar-h))!important;border-radius:var(--radius) 0 0 0!important}}
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
.video-ph {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  background: #f2f3f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #969799;
  font-size: 22px;
  text-decoration: none;
}
.picker {
  width: 100%;
  padding: 6px;
  border: 1px solid #ebedf0;
  border-radius: 6px;
  background: #fff;
  font-size: 14px;
}
.grid-wrap { margin-bottom: 10px; }
.grid-group h3 { font-size: 14px; margin: 8px 0; }
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
@media (min-width: 600px) {
  .grid { grid-template-columns: repeat(3, 1fr); }
}
.grid-card {
  background: #fff;
  border-radius: 10px;
  padding: 6px;
  cursor: pointer;
}
.thumb {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: #f7f8fa;
  display: flex;
  align-items: center;
  justify-content: center;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.thumb-ph { color: #969799; font-size: 20px; }
.grid-meta { display: flex; flex-direction: column; gap: 2px; margin-top: 6px; }
.list-thumb { width: 32px; height: 32px; border-radius: 6px; object-fit: cover; }
.list-thumb.ph { background:#f2f3f5; display:inline-flex; align-items:center; justify-content:center; color:#969799; font-size:12px; }
</style>
