<template>
  <div v-if="person">
    <div class="card">
      <h3>{{ person.is_self ? '我' : person.display_name }}</h3>
      <div class="muted">
        {{ store.relationLabel(person.relation_type) }}
        <template v-if="person.birthday_lunar && person.lunar_month">
          · 农历 {{ person.lunar_month }}月{{ person.lunar_day }}日
        </template>
        <template v-else-if="person.birthday"> · 生日 {{ person.birthday }}</template>
      </div>
      <div class="muted" v-if="person.aliases">别名：{{ person.aliases }}</div>
      <div style="margin-top: 6px">
        <van-tag plain>{{ store.circleLabel(person.circle) }}</van-tag>
        <van-tag plain style="margin-left: 4px">{{ store.familiarityLabel(person.familiarity) }}</van-tag>
        <span class="muted" v-if="person.via_name"> · 通过 {{ person.via_name }} 认识</span>
      </div>
      <div class="muted" v-if="person.notes" style="margin-top: 6px">备注：{{ person.notes }}</div>
      <van-button size="small" plain style="margin-top: 10px" @click="startEdit">编辑资料</van-button>
    </div>

    <div class="card">
      <h3>关系</h3>
      <p class="muted">这个人和其他人的关系（如「她的闺蜜」「她的姐姐」）。</p>
      <div v-for="r in relations" :key="r.id" class="row edge">
        <span>{{ r.from_name }} <span class="warn">—{{ r.label }}→</span> {{ r.to_name }}</span>
        <span class="danger" @click="removeRelation(r)">删</span>
      </div>
      <p v-if="!relations.length" class="muted">（还没有关系记录）</p>
      <van-field v-model="newRel.label" label="新增" maxlength="32" placeholder="关系名，如 闺蜜 / 姐妹" />
      <van-field label="对方">
        <template #input>
          <select v-model="newRel.to" class="picker">
            <option :value="null">选择对方…</option>
            <option v-for="p in otherPersons" :key="p.id" :value="p.id">
              {{ store.displayName(p) }}
            </option>
          </select>
        </template>
      </van-field>
      <van-button size="small" type="primary" style="margin-top: 8px" @click="addRelation">
        加为「{{ person.is_self ? '我' : person.display_name }} → 对方」
      </van-button>
    </div>

    <div class="card" v-if="editing">
      <h3>编辑资料</h3>
      <van-field v-model="form.name" label="名称" maxlength="64" placeholder="必填" />
      <van-field label="关系类型">
        <template #input>
          <select v-model="form.relation" class="picker">
            <option v-for="r in store.config?.relation_types || []" :key="r.key" :value="r.key">
              {{ r.label }}
            </option>
          </select>
        </template>
      </van-field>
      <van-field v-model="form.aliases" label="别名" placeholder="逗号分隔，便于搜索" />
      <van-field label="谁的圈子">
        <template #input>
          <select v-model="form.circle" class="picker">
            <option value="self">我这边</option>
            <option value="shared">共同</option>
            <option value="partner">她那边</option>
          </select>
        </template>
      </van-field>
      <van-field label="熟悉度">
        <template #input>
          <select v-model.number="form.familiarity" class="picker">
            <option :value="1">只闻其名</option>
            <option :value="2">见过</option>
            <option :value="3">常见</option>
            <option :value="4">很熟</option>
          </select>
        </template>
      </van-field>
      <van-field label="通过谁认识">
        <template #input>
          <select v-model="form.via" class="picker">
            <option :value="null">—</option>
            <option v-for="p in otherPersons" :key="p.id" :value="p.id">
              {{ store.displayName(p) }}
            </option>
          </select>
        </template>
      </van-field>
      <van-field
        v-model="form.notes"
        label="备注"
        type="textarea"
        rows="3"
        autosize
        maxlength="500"
        show-word-limit
        placeholder="自由备注：称呼、纪念日、注意事项…"
      />
      <div style="display: flex; gap: 8px; margin-top: 12px">
        <van-button block type="primary" :loading="savingPerson" @click="savePerson">保存</van-button>
        <van-button block plain @click="editing = false">取消</van-button>
      </div>
    </div>

    <div class="card">
      <h3>模块开关</h3>
      <p class="muted">同一套代码，靠开关决定这个人有哪些功能。</p>
      <van-cell v-for="k in allModules" :key="k" :title="store.moduleLabel(k)">
        <template #right-icon>
          <van-switch
            :model-value="enabledModules.includes(k)"
            size="20"
            @update:model-value="(v) => toggleModule(k, v)"
          />
        </template>
      </van-cell>
    </div>

    <div class="card" v-if="enabledModules.includes('cycle')">
      <h3>生理期</h3>
      <div class="row">
        <span>最近一次</span><span>{{ pred?.last_start || '无记录' }}</span>
      </div>
      <div class="row">
        <span>平均周期</span><span>{{ pred?.avg_cycle_days ?? '—' }} 天</span>
      </div>
      <div class="row">
        <span>预测下次</span>
        <span>
          {{ pred?.predicted_next || '—' }}
          <van-tag v-if="pred?.in_window" type="danger" style="margin-left: 4px">窗口内</van-tag>
        </span>
      </div>
      <p class="muted">{{ pred?.note }}</p>
      <router-link :to="'/cycle?person=' + person.id">去记录 →</router-link>
    </div>

    <div class="card">
      <h3>属性</h3>
      <div v-for="cat in store.attributeCategories" :key="cat.key" style="margin-bottom: 8px">
        <div class="muted">{{ cat.label }}</div>
        <div class="chips">
          <van-tag
            v-for="a in attrsOf(cat.key)"
            :key="a.id"
            :type="a.sensitivity === 'sensitive' ? 'warning' : 'primary'"
            closeable
            @close="removeAttr(a)"
          >
            {{ a.value }}
          </van-tag>
          <span v-if="!attrsOf(cat.key).length" class="muted">还没有</span>
        </div>
      </div>
      <van-field v-model="newAttrValue" label="新增" :placeholder="attrPlaceholder" />
      <p class="muted">{{ attrPlaceholder }}</p>
    </div>

    <div class="card" v-if="photos.length">
      <h3>服装 / 图片（最近 {{ photos.length }} 张）</h3>
      <div class="thumbs">
        <template v-for="m in photos" :key="m.id">
          <img v-if="m.kind !== 'video'" :src="api.mediaUrl(m)" loading="lazy" @click="openFull(m)" />
          <div v-else class="vthumb" @click="openFull(m)">▶</div>
        </template>
      </div>
      <router-link to="/gallery">去相册 →</router-link>
    </div>

    <div class="card">
      <h3>最近记录</h3>
      <div class="row" v-for="e in events" :key="e.id">
        <span><van-tag plain>{{ e.type_key }}</van-tag> {{ e.title || (e.body || '').slice(0, 16) }}</span>
        <span class="muted">{{ e.event_date }}</span>
      </div>
      <van-empty v-if="!events.length" description="还没有记录" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
const route = useRoute()
const person = ref(null)
const enabledModules = ref([])
const attrs = ref([])
const events = ref([])
const pred = ref(null)
const photos = ref([])
const newAttrValue = ref('')
const pickedCategory = ref('like')

const allModules = computed(() => (store.config?.modules || []).map((m) => m.key))
const attrPlaceholder = computed(() => {
  const cat = store.attributeCategories.find((c) => c.key === pickedCategory.value)
  return `分类：${cat ? cat.label : pickedCategory.value}（点上面的分类标签切换）`
})

function attrsOf(catKey) {
  return attrs.value.filter((a) => a.category === catKey)
}

async function load() {
  const id = Number(route.params.id)
  const cached = store.persons.find((p) => p.id === id) || null
  // ★ 全部并发：手机经 Tailscale 时单程 RTT ~400ms，原来 6 个 await 串行
  //   = 6 个往返（~2.4s），并发后只要 1 个往返。
  //   冷启动直接打开 /person/:id 时 store 还没这个人 —— 顺手并发补拉一次，
  //   别让它变成第 7 个串行往返（旧版这里是 await api.person(id)）。
  const [m, a, ev, ph, rel, pred, fetched] = await Promise.all([
    api.modules(id),
    api.attributes(id),
    api.events({ person_id: id, limit: 10 }),
    api.media({ person_id: id, limit: 12 }),
    api.relations(id),
    api.cyclePrediction(id).catch(() => null),
    cached ? Promise.resolve(null) : api.person(id).catch(() => null),
  ])
  person.value = cached || fetched
  enabledModules.value = m?.enabled || []
  attrs.value = a || []
  events.value = ev?.items || []
  photos.value = ph || []
  relations.value = rel || []
  // cycle 模块没开就不显示预测（接口很轻，白拉一次比再等一个往返划算）
  pred.value = enabledModules.value.includes('cycle') ? pred : null
}

function openFull(m) {
  window.open(api.mediaUrl(m, false), '_blank')
}

async function toggleModule(key, value) {
  const next = new Set(enabledModules.value)
  if (value) next.add(key)
  else next.delete(key)
  const res = await api.putModules(Number(route.params.id), [...next])
  enabledModules.value = res.enabled || []
  if (key === 'cycle') {
    pred.value = enabledModules.value.includes('cycle')
      ? await api.cyclePrediction(Number(route.params.id))
      : null
  }
}

async function removeAttr(a) {
  await api.deleteAttribute(a.id)
  attrs.value = await api.attributes(Number(route.params.id))
}

async function addAttr() {
  if (!newAttrValue.value.trim()) return
  await api.createAttribute({
    person_id: Number(route.params.id),
    category: pickedCategory.value,
    value: newAttrValue.value.trim(),
  })
  newAttrValue.value = ''
  attrs.value = await api.attributes(Number(route.params.id))
  showToast('已添加')
}

watch(
  () => route.params.id,
  () => load()
)
// store 的人到齐后补一次（冷启动竞态的另一半）
watch(
  () => store.persons.length,
  () => {
    const id = Number(route.params.id)
    if (!person.value) person.value = store.persons.find((p) => p.id === id) || null
  }
)
const editing = ref(false)
const savingPerson = ref(false)
const form = reactive({ name: '', relation: '', aliases: '', notes: '', circle: 'self', familiarity: 1, via: null })

// ---- 关系边（人与人）----
const relations = ref([])
const newRel = reactive({ to: null, label: '' })
const otherPersons = computed(() =>
  store.persons.filter((p) => p.id !== person.value?.id)
)

function startEdit() {
  const p = person.value
  if (!p) return
  form.name = p.is_self ? '我' : p.display_name
  form.relation = p.relation_type
  form.aliases = p.aliases || ''
  form.notes = p.notes || ''
  form.circle = p.circle || 'self'
  form.familiarity = p.familiarity || 1
  form.via = p.via_person_id || null
  editing.value = true
}

async function savePerson() {
  const name = form.name.trim()
  if (!name) {
    showToast('名称不能为空')
    return
  }
  savingPerson.value = true
  try {
    const updated = await api.patchPerson(person.value.id, {
      display_name: name,
      relation_type: form.relation,
      aliases: form.aliases.trim() || null,
      notes: form.notes.trim() || null,
      circle: form.circle,
      familiarity: Number(form.familiarity) || 1,
      via_person_id: form.via || null,
    })
    person.value = updated
    await store.loadPersons() // 顶部切换器的名字也要跟着变
    editing.value = false
    showToast('已保存')
  } catch (e) {
    showToast('保存失败：' + e.message)
  } finally {
    savingPerson.value = false
  }
}

async function loadRelations() {
  if (!person.value) return
  relations.value = await api.relations(person.value.id)
}

async function addRelation() {
  if (!newRel.to) {
    showToast('请选择对方')
    return
  }
  if (!newRel.label.trim()) {
    showToast('请填关系名称')
    return
  }
  try {
    await api.createRelation({
      from_person_id: person.value.id,
      to_person_id: newRel.to,
      label: newRel.label.trim(),
    })
    newRel.label = ''
    newRel.to = null
    await loadRelations()
    showToast('已添加')
  } catch (e) {
    showToast('添加失败：' + e.message)
  }
}

async function removeRelation(r) {
  await api.deleteRelation(r.id)
  await loadRelations()
  showToast('已删除')
}

onMounted(load)
</script>

<style scoped>
.thumbs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
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
.picker {
  width: 100%;
  border: none;
  background: transparent;
  color: inherit;
  font-size: 14px;
  padding: 0;
  outline: none;
}
.edge {
  font-size: 13px;
}
</style>
