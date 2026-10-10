<template>
  <div>
    <div class="card">
      <h3>待办池（{{ open.length }} 条未完成）</h3>
      <p class="muted">待补信息、待回礼、要观察的事 —— 散在正文里最容易丢。</p>
      <p class="muted" style="margin: 6px 0 0">显示：{{ store.scopeLabel }}（换人在首页）</p>
    </div>

    <div class="card">
      <van-field v-model="form.title" label="事项" placeholder="如：问她新工作找得怎么样" />
      <van-field v-model="form.due_date" type="date" label="截止" placeholder="可留空" />
      <div class="row">
        <span class="muted">类型</span>
        <select v-model="form.kind" class="picker">
          <option value="missing_info">待补信息</option>
          <option value="return_gift">待回礼</option>
          <option value="observe">待观察</option>
          <option value="other">其它</option>
        </select>
      </div>
      <van-button block type="primary" style="margin-top: 10px" @click="add">添加</van-button>
    </div>

    <div class="card">
      <div class="row" v-for="t in all" :key="t.id">
        <label style="display: flex; gap: 8px; align-items: center">
          <input type="checkbox" :checked="t.done" @change="toggle(t)" />
          <span :style="t.done ? 'text-decoration: line-through; color: #969799' : ''">
            {{ t.title }}
            <span class="muted" v-if="t.due_date"> · {{ t.due_date }}</span>
            <span class="muted" v-if="t.person_name"> · {{ t.person_name }}</span>
          </span>
        </label>
        <span class="danger" @click="remove(t)">删除</span>
      </div>
      <van-empty v-if="!all.length" description="没有待办" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
const includeDone = ref(false)
const all = ref([])
const form = reactive({ title: '', due_date: '', kind: 'missing_info' })

const open = computed(() => all.value.filter((t) => !t.done))

async function load() {
  all.value = await api.todos(undefined, true)
}

async function add() {
  if (!form.title.trim()) return
  await api.createTodo({
    person_id: store.currentPersonId || null,
    kind: form.kind,
    title: form.title.trim(),
    due_date: form.due_date || null,
  })
  form.title = ''
  form.due_date = ''
  await load()
}

async function toggle(t) {
  await api.patchTodo(t.id, { done: !t.done })
  await load()
}

async function remove(t) {
  await api.deleteTodo(t.id)
  await load()
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
