<template>
  <div>
    <section class="card"><h3>待办 · {{ open.length }} 条未完成</h3><p class="muted">范围可在顶部切换，仅影响本页。</p></section>
    <section class="card">
      <label>归属人 <select v-model="ownerId" class="picker" aria-label="待办归属人"><option :value="null" disabled>请选择人物</option><option v-for="p in store.persons" :value="p.id" :key="p.id">{{ store.displayName(p) }}</option></select></label>
      <van-field v-model="form.title" label="事项" placeholder="需要做什么" />
      <van-field v-model="form.due_date" type="date" label="截止" />
      <div class="row"><span class="muted">类型</span><select v-model="form.kind" class="picker"><option value="missing_info">待补信息</option><option value="return_gift">待回礼</option><option value="observe">待观察</option><option value="other">其它</option></select></div>
      <van-button block type="primary" :loading="saving" @click="add">添加待办</van-button>
    </section>
    <section class="card">
      <div class="row" v-for="t in all" :key="t.id">
        <label class="todo"><input type="checkbox" :checked="t.done" :disabled="busy.has(t.id)" @change="toggle(t,$event)" /><span :class="{ done:t.done }">{{ t.title }}<small class="muted">{{ t.due_date || '无截止日期' }} · {{ store.displayName(store.persons.find(p => p.id === t.person_id)) || '未指定' }}</small></span></label>
        <button class="danger remove" :disabled="busy.has(t.id)" @click="remove(t)">删除</button>
      </div>
      <van-empty v-if="!all.length" description="这个范围暂无待办" />
    </section>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { resolveScopedPerson } from '../lib/scope'
import { api } from '../api'
import { useArchiveStore } from '../store'
const store = useArchiveStore()
const route = useRoute()
const effectivePersonId = computed(() => resolveScopedPerson(route.query.person, store.currentPersonId))
const ownerId = ref(effectivePersonId.value)
const saving = ref(false)
const busy = reactive(new Set())
const all = ref([])
const form = reactive({ title:'',due_date:'',kind:'missing_info' })
const open = computed(() => all.value.filter(t => !t.done))
let loadVersion = 0
async function load() {
  const version = ++loadVersion
  try { const rows = await api.todos(effectivePersonId.value || undefined,true); if(version === loadVersion) all.value = rows }
  catch(e) { showToast(e.message || '加载待办失败') }
}
async function add() {
  if(saving.value) return
  if(!ownerId.value) return showToast('请选择待办归属人物')
  if(!form.title.trim()) return showToast('请填写事项')
  saving.value = true
  try { await api.createTodo({ person_id:Number(ownerId.value),kind:form.kind,title:form.title.trim(),due_date:form.due_date || null }); form.title=''; form.due_date=''; await load() }
  catch(e) { showToast(e.message || '添加失败') }
  finally { saving.value=false }
}
async function toggle(t,event) {
  if(busy.has(t.id)) return
  busy.add(t.id)
  try { await api.patchTodo(t.id,{done:!t.done}); await load() }
  catch(e) { event.target.checked=t.done; showToast(e.message || '更新失败') }
  finally { busy.delete(t.id) }
}
async function remove(t) {
  try { await showConfirmDialog({title:'删除待办',message:'确定删除这条待办？'}) } catch { return }
  busy.add(t.id)
  try { await api.deleteTodo(t.id); await load() } catch(e) { showToast(e.message || '删除失败') } finally { busy.delete(t.id) }
}
watch(effectivePersonId, (id) => {
  if (!saving.value && !form.title && !form.due_date) ownerId.value = id
  load()
})
onMounted(async () => { await store.ensureLoaded(); await load() })
</script>
<style scoped>
.picker { padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--surface); max-width:100%; }
.todo { display:flex; align-items:center; gap:12px; }
.todo small { display:block; margin-top:4px; }
.done { text-decoration:line-through; color:var(--muted); }
.remove { border:0; background:none; min-height:44px; cursor:pointer; }
</style>
