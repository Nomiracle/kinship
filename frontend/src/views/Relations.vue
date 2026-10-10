<template>
  <div>
    <div class="card">
      <h3>关系网</h3>
      <p class="muted">
        按「谁的圈子」分组 —— 伴侣的家人朋友你未必熟，但对她来说很重要。
        点人名进个人页；这里可以加/删人与人之间的关系。
      </p>
      <div class="chips">
        <van-tag
          v-for="c in CIRCLES"
          :key="c.key"
          :type="filter === c.key ? 'primary' : 'default'"
          size="large"
          @click="filter = filter === c.key ? null : c.key"
        >
          {{ c.label }}（{{ store.byCircle(c.key).length }}）
        </van-tag>
      </div>
      <p class="muted" style="margin-top: 6px">
        共 {{ relations.length }} 条关系边 · 当前显示 {{ visibleGroups.length }} 组
      </p>
    </div>

    <div class="card" v-for="g in visibleGroups" :key="g.key">
      <h3>{{ g.label }}（{{ g.people.length }}）</h3>
      <div v-for="p in g.people" :key="p.id" class="person">
        <div class="row">
          <router-link :to="'/person/' + p.id" style="text-decoration: none; color: inherit">
            <strong>{{ store.displayName(p) }}</strong>
          </router-link>
          <span class="muted">
            {{ store.relationLabel(p.relation_type) }}
            <van-tag plain style="margin-left: 4px">{{ store.familiarityLabel(p.familiarity) }}</van-tag>
            <van-tag v-if="p.sensitivity === 'sensitive'" type="warning" plain style="margin-left: 4px">敏感</van-tag>
          </span>
        </div>
        <div class="muted" v-if="p.via_name">通过 {{ p.via_name }} 认识</div>
        <div class="muted" v-if="p.notes">{{ p.notes }}</div>
        <div v-if="edgesOf(p.id).length" style="margin-top: 6px">
          <div v-for="e in edgesOf(p.id)" :key="e.id" class="row edge">
            <span>{{ e.from_name }} <span class="warn">—{{ e.label }}→</span> {{ e.to_name }}</span>
            <span class="danger" @click="removeEdge(e)">删</span>
          </div>
        </div>
        <p v-else class="muted" style="margin-top: 4px">（还没有关系记录）</p>
      </div>
      <p v-if="!g.people.length" class="muted">（空）</p>
    </div>

    <div class="card">
      <h3>添加关系</h3>
      <van-field label="从">
        <template #input>
          <select v-model="form.from" class="picker">
            <option :value="null">选择…</option>
            <option v-for="p in store.persons" :key="p.id" :value="p.id">
              {{ store.displayName(p) }}
            </option>
          </select>
        </template>
      </van-field>
      <van-field
        v-model="form.label"
        label="关系"
        maxlength="32"
        placeholder="如：闺蜜 / 姐妹 / 父女 / 同事"
      />
      <van-field label="到">
        <template #input>
          <select v-model="form.to" class="picker">
            <option :value="null">选择…</option>
            <option v-for="p in store.persons" :key="p.id" :value="p.id">
              {{ store.displayName(p) }}
            </option>
          </select>
        </template>
      </van-field>
      <van-button
        block
        type="primary"
        style="margin-top: 12px"
        :loading="saving"
        @click="addEdge"
      >
        添加
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'

const CIRCLES = [
  { key: 'self', label: '我这边' },
  { key: 'shared', label: '共同' },
  { key: 'partner', label: '她那边' },
]

const store = useArchiveStore()
const relations = ref([])
const filter = ref(null)
const saving = ref(false)
const form = reactive({ from: null, label: '', to: null })

const visibleGroups = computed(() =>
  CIRCLES.filter((c) => !filter.value || c.key === filter.value).map((c) => ({
    ...c,
    people: store.byCircle(c.key),
  }))
)

function edgesOf(personId) {
  return relations.value.filter((r) => r.from_person_id === personId || r.to_person_id === personId)
}

async function load() {
  relations.value = await api.relations()
  if (!store.persons.length) await store.loadPersons()
}

async function addEdge() {
  if (!form.from || !form.to) {
    showToast('请选择两端的人')
    return
  }
  if (form.from === form.to) {
    showToast('两端不能是同一个人')
    return
  }
  if (!form.label.trim()) {
    showToast('请填关系名称')
    return
  }
  saving.value = true
  try {
    await api.createRelation({
      from_person_id: form.from,
      to_person_id: form.to,
      label: form.label.trim(),
    })
    form.label = ''
    form.to = null
    await load()
    showToast('已添加')
  } catch (e) {
    showToast('添加失败：' + e.message)
  } finally {
    saving.value = false
  }
}

async function removeEdge(e) {
  try {
    await showConfirmDialog({ title: '删除关系', message: `${e.from_name} —${e.label}→ ${e.to_name}？` })
  } catch {
    return
  }
  await api.deleteRelation(e.id)
  await load()
  showToast('已删除')
}

onMounted(load)
</script>

<style scoped>
.person {
  padding: 8px 0;
  border-bottom: 1px solid var(--line, #eee);
}
.person:last-child {
  border-bottom: none;
}
.edge {
  font-size: 13px;
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
</style>
