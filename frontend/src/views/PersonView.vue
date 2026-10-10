<template>
  <div v-if="person">
    <!-- 身份（内容优先，默认只读） -->
    <div class="card">
      <div class="row" style="padding: 0">
        <h3 style="margin: 0">{{ person.is_self ? '我' : person.display_name }}</h3>
        <span class="link" @click="toggleEdit">{{ editing ? '收起' : '编辑资料' }}</span>
      </div>
      <div class="muted" style="margin-top: 4px">
        {{ store.relationLabel(person.relation_type) }} · {{ store.genderLabel(person.gender) }}
        <!-- ★ 生日一定给「明确写法 + 还有几天 + 满几岁」：
             只给天数会被误读成别的倒计时（生理期预测的「约 N 天后」就撞过） -->
        <template v-if="person.birthday_text"> · {{ birthdayLine(person) }}</template>
        <template v-else> · 生日未录入</template>
      </div>
      <div class="muted" v-if="person.aliases">别名：{{ person.aliases }}</div>
      <div style="margin-top: 6px">
        <van-tag plain>{{ store.circleLabel(person.circle) }}</van-tag>
        <van-tag plain style="margin-left: 4px">{{ store.familiarityLabel(person.familiarity) }}</van-tag>
        <span class="muted" v-if="person.via_name"> · 通过 {{ person.via_name }} 认识</span>
      </div>
      <div class="muted" v-if="person.notes" style="margin-top: 6px">备注：{{ person.notes }}</div>

      <!-- 编辑资料（点「编辑资料」展开） -->
      <div v-if="editing" style="margin-top: 10px; border-top: 1px solid #f2f3f5; padding-top: 8px">
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
        <van-field label="性别">
          <template #input>
            <select v-model="form.gender" class="picker">
              <option :value="null">未知（不自动开生理期）</option>
              <option v-for="g in store.genders" :key="g.key" :value="g.key">{{ g.label }}</option>
            </select>
          </template>
        </van-field>
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
    </div>

    <!-- 内容快捷入口（带 ?person=，落到下游页只显示这个人，不改全局 scope） -->
    <div class="card">
      <div class="chips">
        <router-link class="pill" :to="{ path: '/timeline', query: scopeQuery(person.id) }">时间轴</router-link>
        <router-link class="pill" :to="{ path: '/gallery', query: scopeQuery(person.id) }">相册</router-link>
        <router-link
          v-if="enabledModules.includes('outfit')"
          class="pill"
          :to="{ path: '/wardrobe', query: scopeQuery(person.id) }"
        >
          衣橱
        </router-link>
        <router-link
          v-if="cycleUsable"
          class="pill"
          :to="{ path: '/cycle', query: scopeQuery(person.id) }"
        >
          生理期
        </router-link>
      </div>
    </div>

    <!-- 属性（关键信息前置到最近记录之前） -->
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
      <!-- 新增属性：原生 select 选分类 + 输入值 + 添加按钮（此前只有输入框、没有入口） -->
      <div class="attr-add">
        <select v-model="pickedCategory" class="picker">
          <option v-for="cat in store.attributeCategories" :key="cat.key" :value="cat.key">
            {{ cat.label }}
          </option>
        </select>
        <van-field
          v-model="newAttrValue"
          class="attr-input"
          placeholder="值，如：喜欢猫 / 忌口香菜"
          @keyup.enter="addAttr"
        />
        <van-button size="small" type="primary" @click="addAttr">添加</van-button>
      </div>
    </div>

    <!-- 生理期（模块开启 + 性别允许才显示；易孕期参考是它的子段） -->
    <div class="card" v-if="cycleUsable && pred">
      <h3>生理期</h3>
      <div class="row"><span>最近一次</span><span>{{ pred.last_start || '无记录' }}</span></div>
      <div class="row"><span>平均周期</span><span>{{ pred.avg_cycle_days ?? '—' }} 天</span></div>
      <div class="row">
        <span>预测下次</span>
        <span>
          {{ pred.predicted_next || '—' }}
          <van-tag v-if="pred.in_window" type="danger" style="margin-left: 4px">窗口内</van-tag>
        </span>
      </div>

      <!-- 易孕期 / 相对安全期参考（config 的 show_fertility_window 关掉就没有这段） -->
      <template v-if="pred.fertility">
        <div class="row"><span>预测排卵日</span><span>{{ pred.fertility.ovulation }}</span></div>
        <div class="row">
          <span>易孕窗口</span>
          <span class="warn">{{ pred.fertility.fertile_window[0] }} ~ {{ pred.fertility.fertile_window[1] }}</span>
        </div>
        <div class="row" v-if="pred.fertility.phase_today"><span>今天</span><span>{{ pred.fertility.phase_today }}</span></div>
        <div class="row"><span>规律性</span><span>{{ pred.fertility.regularity.text }}</span></div>
        <p class="muted">{{ pred.fertility_note }}</p>
      </template>

      <p class="muted">{{ pred.note }}</p>
      <router-link :to="{ path: '/cycle', query: scopeQuery(person.id) }">去记录 →</router-link>
    </div>

    <!-- 关系摘要（只读速览，点「管理」展开增删）——不必进管理面板也能看到关系 -->
    <div class="card">
      <div class="row" style="padding: 0">
        <h3 style="margin: 0">关系</h3>
        <span class="link" @click="openManagement()">管理</span>
      </div>
      <template v-if="relations.length">
        <div class="row edge" v-for="r in relations.slice(0, 3)" :key="r.id">
          <span>{{ r.from_name }} <span class="warn">—{{ r.label }}→</span> {{ r.to_name }}</span>
        </div>
        <p v-if="relations.length > 3" class="muted">共 {{ relations.length }} 条，点「管理」查看全部</p>
      </template>
      <p v-else class="muted">还没有关系记录，点「管理」添加。</p>
    </div>

    <!-- 最近记录 -->
    <div class="card">
      <h3>最近记录</h3>
      <div class="row" v-for="e in events" :key="e.id">
        <span><van-tag plain>{{ typeLabel(e.type_key) }}</van-tag> {{ e.title || (e.body || '').slice(0, 16) }}</span>
        <span class="muted">{{ e.event_date }}</span>
      </div>
      <van-empty v-if="!events.length" description="还没有记录" />
    </div>

    <!-- 服装 / 图片 -->
    <div class="card" v-if="photos.length">
      <h3>服装 / 图片（最近 {{ photos.length }} 张）</h3>
      <div class="thumbs">
        <template v-for="m in photos" :key="m.id">
          <img v-if="m.kind !== 'video'" :src="api.mediaUrl(m)" loading="lazy" @click="openFull(m)" />
          <div v-else class="vthumb" @click="openFull(m)">▶</div>
        </template>
      </div>
      <router-link :to="{ path: '/gallery', query: scopeQuery(person.id) }">去相册 →</router-link>
    </div>

    <!-- 管理（默认收起：模块开关 / 关系 / 删除） -->
    <div class="card">
      <div class="row" style="padding: 0" @click="mgmtOpen = !mgmtOpen">
        <h3 style="margin: 0">管理</h3>
        <span class="muted">{{ mgmtOpen ? '收起 ▲' : '模块 · 关系 · 删除 ▼' }}</span>
      </div>

      <template v-if="mgmtOpen">
        <!-- 模块开关：只列「这个性别允许的」模块（男性看不到生理期） -->
        <h4 class="mgt-title">模块开关</h4>
        <p class="muted">同一套代码，靠开关决定这个人有哪些功能。</p>
        <van-cell v-for="k in modulesAvailable" :key="k" :title="store.moduleLabel(k)">
          <template #right-icon>
            <van-switch
              :model-value="enabledModules.includes(k)"
              size="20"
              @update:model-value="(v) => toggleModule(k, v)"
            />
          </template>
        </van-cell>
        <p class="muted" v-if="blockedModules.length">
          以下模块已启用但当前性别不适用，已自动隐藏：{{ blockedText }}
        </p>

        <!-- 关系边 -->
        <h4 class="mgt-title">关系</h4>
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

        <!-- 删除 -->
        <h4 class="mgt-title">删除</h4>
        <van-button
          v-if="!person.is_self"
          size="small"
          type="danger"
          plain
          @click="removePerson"
        >
          删除这个人及其全部记录
        </van-button>
      </template>
    </div>
  </div>

  <van-empty v-else description="加载中…" />
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { scopeQuery } from '../lib/scope'
import { birthdayLine } from '../lib/birthday'

const store = useArchiveStore()
const route = useRoute()
const router = useRouter()
const person = ref(null)
const enabledModules = ref([])
const attrs = ref([])
const events = ref([])
const pred = ref(null)
const photos = ref([])
const newAttrValue = ref('')
const pickedCategory = ref('like')
const editing = ref(false)
const savingPerson = ref(false)
const mgmtOpen = ref(false)
// 这个性别**能开**的模块（后端 /api/modules 的 available）+ 已启用但不适用的（blocked）
const modulesAvailable = ref((store.config?.modules || []).map((m) => m.key))
const blockedModules = ref([])

// 生理期要同时满足「已启用」和「性别允许」——只看已启用的话，
// 把性别改成男之后入口和卡片还会赖在页面上
const cycleUsable = computed(
  () => enabledModules.value.includes('cycle') && modulesAvailable.value.includes('cycle')
)
const blockedText = computed(() => blockedModules.value.map((k) => store.moduleLabel(k)).join('、'))

function attrsOf(catKey) {
  return attrs.value.filter((a) => a.category === catKey)
}

function typeLabel(key) {
  const t = store.eventTypes.find((x) => x.key === key)
  return t ? t.label : key
}

async function load() {
  const id = Number(route.params.id)
  const cached = store.persons.find((p) => p.id === id) || null
  // ★ 全部并发：手机经 Tailscale 时单程 RTT ~400ms，原来 6 个 await 串行
  //   = 6 个往返（~2.4s），并发后只要 1 个往返。
  //   冷启动直接打开 /person/:id 时 store 还没这个人 —— 顺手并发补拉一次，
  //   别让它变成第 7 个串行往返（旧版这里是 await api.person(id)）。
  // ★ 修 bug：这里曾用 `pred` 作为解构变量名，遮蔽了上面的 `pred` ref，
  //   导致 `pred.value = ...` 写到了普通对象/null 上（预测永远不显示，甚至运行时报错）。
  const [m, a, ev, ph, rel, predData, fetched] = await Promise.all([
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
  // available/blocked 由后端按性别算好（男性 → available 里没有 cycle）
  modulesAvailable.value = m?.available || (store.config?.modules || []).map((x) => x.key)
  blockedModules.value = m?.blocked || []
  attrs.value = a || []
  events.value = ev?.items || []
  photos.value = ph || []
  relations.value = rel || []
  // cycle 没开（或这个性别不允许）就不显示预测
  //（接口很轻，白拉一次比再等一个往返划算）
  pred.value = cycleUsable.value ? predData : null
}

function openFull(m) {
  window.open(api.mediaUrl(m, false), '_blank')
}

// 关系摘要里的「管理」：直接展开管理面板
function openManagement() {
  mgmtOpen.value = true
}

async function toggleModule(key, value) {
  const next = new Set(enabledModules.value)
  if (value) next.add(key)
  else next.delete(key)
  const res = await api.putModules(Number(route.params.id), [...next])
  enabledModules.value = res.enabled || []
  store.personModules[Number(route.params.id)] = [...enabledModules.value]
  if (key === 'cycle') {
    pred.value = cycleUsable.value
      ? await api.cyclePrediction(Number(route.params.id)).catch(() => null)
      : null
  }
}

async function removeAttr(a) {
  await api.deleteAttribute(a.id)
  attrs.value = await api.attributes(Number(route.params.id))
}

async function addAttr() {
  if (!newAttrValue.value.trim()) return
  if (!pickedCategory.value) {
    showToast('先选分类')
    return
  }
  try {
    await api.createAttribute({
      person_id: Number(route.params.id),
      category: pickedCategory.value,
      value: newAttrValue.value.trim(),
    })
    newAttrValue.value = ''
    attrs.value = await api.attributes(Number(route.params.id))
    showToast('已添加')
  } catch (e) {
    showToast(e.message || '添加失败')
  }
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

const form = reactive({ name: '', relation: '', gender: null, aliases: '', notes: '', circle: 'self', familiarity: 1, via: null })

// ---- 关系边（人与人）----
const relations = ref([])
const newRel = reactive({ to: null, label: '' })
const otherPersons = computed(() => store.persons.filter((p) => p.id !== person.value?.id))

function startEdit() {
  const p = person.value
  if (!p) return
  form.name = p.is_self ? '我' : p.display_name
  form.relation = p.relation_type
  form.gender = p.gender || null
  form.aliases = p.aliases || ''
  form.notes = p.notes || ''
  form.circle = p.circle || 'self'
  form.familiarity = p.familiarity || 1
  form.via = p.via_person_id || null
  editing.value = true
}

// 展开时预填表单，收起时只关闭
function toggleEdit() {
  if (editing.value) {
    editing.value = false
    return
  }
  startEdit()
}

async function savePerson() {
  const name = form.name.trim()
  if (!name) {
    showToast('名称不能为空')
    return
  }
  savingPerson.value = true
  try {
    const genderChanged = (person.value?.gender || null) !== (form.gender || null)
    const updated = await api.patchPerson(person.value.id, {
      display_name: name,
      relation_type: form.relation,
      gender: form.gender || null,
      aliases: form.aliases.trim() || null,
      notes: form.notes.trim() || null,
      circle: form.circle,
      familiarity: Number(form.familiarity) || 1,
      via_person_id: form.via || null,
    })
    person.value = updated
    await store.loadPersons() // 顶部切换器的名字也要跟着变
    // 改了性别 → 能用的模块会变（生理期对男性不适用），必须重新拉一遍，
    // 否则开关列表和生理期卡片还按旧性别显示
    if (genderChanged) {
      const m = await api.modules(person.value.id).catch(() => null)
      if (m) {
        enabledModules.value = m.enabled || enabledModules.value
        modulesAvailable.value = m.available || modulesAvailable.value
        blockedModules.value = m.blocked || []
        store.personModules[person.value.id] = [...enabledModules.value]
        if ((m.blocked || []).length) showToast('已保存；生理期模块与新性别不符，已隐藏')
      }
      if (!cycleUsable.value) pred.value = null
    }
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

async function removePerson() {
  const p = person.value
  if (!p) return
  try {
    await showConfirmDialog({ title: '删除', message: `删除「${p.display_name}」及其全部记录？` })
  } catch {
    return
  }
  try {
    await api.deletePerson(p.id)
    await store.loadPersons()
    showToast('已删除')
    router.replace('/people')
  } catch (e) {
    showToast(e.message || '删除失败')
  }
}

onMounted(async () => {
  await store.ensureLoaded()
  await load()
})
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
  border: 1px solid #ebedf0;
  border-radius: 8px;
  background: #fff;
  color: inherit;
  font-size: 14px;
  padding: 8px;
  outline: none;
}
.edge {
  font-size: 13px;
}
.mgt-title {
  margin: 14px 0 4px;
  font-size: 13px;
  border-top: 1px solid #f2f3f5;
  padding-top: 10px;
}
.pill {
  padding: 6px 12px;
  border-radius: 16px;
  background: #ecf5ff;
  color: #1989fa;
  font-size: 13px;
  text-decoration: none;
}
.attr-add {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.attr-add .picker {
  flex: 0 0 96px;
  width: auto;
}
.attr-input {
  flex: 1 1 auto;
  padding: 0;
}
</style>
