<template>
  <div>
    <div class="card">
      <div class="chips">
        <van-tag v-for="t in filters" :key="t.key" :type="type===t.key?'primary':'default'" @click="setType(t.key)">{{ t.label }}</van-tag>
      </div>
      <van-field v-model="q" placeholder="搜索标题/正文/标签" clearable label="搜索" />
      <van-field v-model="from" type="date" label="从" />
      <van-field v-model="to" type="date" label="到" />
      <p class="muted" style="margin:6px 0 0">显示：{{ scopeLabelText }}（可在顶部切换，仅影响本页）</p>
    </div>
    <EventDayList :items="filteredItems" :hide-person="singlePerson" :label-of="typeLabel" :item-label="itemLabel" @edit="openEdit" @delete="remove" @preview="onPreview" />
    <div v-if="hasMore" class="muted" style="text-align:center;padding-bottom:8px">
      <van-button size="small" plain :loading="loadingMore" @click="loadMore">加载更多（共 {{ total }} 条，已显示 {{ items.length }} 条）</van-button>
    </div>
    <van-popup v-model:show="showEdit" position="bottom" round :style="{ height:'86%' }" :close-on-click-overlay="false">
      <div class="edit" v-if="form">
        <div class="row"><h3 style="margin:0">编辑记录 · {{ typeLabel(form.type_key) }}</h3><span class="muted" @click="handleEditClose">关闭</span></div>
        <RecordComposer ref="composerRef" :key="form.id" :initial="form" :initialType="form.type_key" @saved="onEditSaved" @cancel="handleEditCancel" />
      </div>
    </van-popup>
    <van-image-preview v-model:show="preview.show" :images="preview.images" :start-position="preview.index" />
  </div>
</template>
<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api.js'
import { useArchiveStore } from '../store.js'
import { resolveScopedPerson } from '../lib/scope.js'
import { previewUrls } from '../lib/media-preview'
import EventDayList from '../components/EventDayList.vue'
import RecordComposer from '../components/records/RecordComposer.vue'

const store = useArchiveStore()
const route = useRoute()
const type = ref('')
const from = ref('')
const to = ref('')
const q = ref('')
const items = ref([])
const total = ref(0)
const hasMore = ref(false)
const loadingMore = ref(false)
const PAGE = 200
const scopedFromQuery = computed(()=> !!resolveScopedPerson(route.query.person, null))
const effectivePersonId = computed(()=> resolveScopedPerson(route.query.person, store.currentPersonId))
const scopeLabelText = computed(()=>{
  const id=effectivePersonId.value
  if(!id) return '全部'
  const p=store.persons.find(x=>x.id===id)
  return p? store.displayName(p) : '全部'
})
const singlePerson = computed(()=> !!effectivePersonId.value)
const filters = computed(()=> [{ key:'', label:'全部' }, ...store.eventTypes])

const filteredItems = computed(()=>items.value)

const showEdit = ref(false)
const form = ref(null)
const composerRef = ref(null)
let pendingClose = false

function typeLabel(key){ const t=store.eventTypes.find(x=>x.key===key); return t? t.label: key }
function itemLabel(it){ return store.privacyMode && it.sensitivity==='sensitive' ? '●●●' : it.name }

let loadVersion=0
async function load(offset=0, append=false){
  const version=++loadVersion
  try {
  const res = await api.events({
    person_id: effectivePersonId.value || undefined,
    type_key: type.value || undefined,
    date_from: from.value || undefined,
    date_to: to.value || undefined,
    q: q.value.trim() || undefined,
    group: 'day',
    limit: PAGE,
    offset: offset || undefined,
  })
  if(version!==loadVersion)return
  const rows=res.items||[]
  items.value = append ? [...items.value, ...rows] : rows
  total.value=res.total||0
  hasMore.value=!!res.has_more
  }catch(e){showToast(e.message||'加载记录失败')}
}
async function loadMore(){ loadingMore.value=true; try{ await load(items.value.length,true) }finally{ loadingMore.value=false } }
function setType(k){ type.value=k }

async function openEdit(e){
  if(e.type_key==='meeting') {
    try {
      const interactions=await api.interactions(e.person_id)
      const row=interactions.find(r=>r.event_id===e.id)
      if(row)e={...e,location:row.location,hours:row.hours,overnight:row.overnight,meetingLoaded:true}
    }catch { showToast('未能读取相处明细，本次保留原有地点和时长') }
  }
  form.value = { ...e, media: (e.media||[]).map(m=>({ ...m })) }
  store.loadModulesFor(e.person_id)
  showEdit.value=true
  pendingClose=false
}
function onEditSaved(){ showEdit.value=false; form.value=null; load() }

async function remove(e){
  try{ await showConfirmDialog({ title:'删除记录', message:`删除「${e.title||e.type_key}」？` }) }catch{ return }
  await api.deleteEvent(e.id)
  showToast('已删除')
  await load()
}

const preview = reactive({ show:false, images:[], index:0 })
function openFull(m, list){
  if (m && m.kind === 'video') { window.open(api.mediaUrl(m,false),'_blank'); return }
  const p=previewUrls(list && list.length ? list : [m], m, api.mediaUrl)
  preview.images=p.images; preview.index=p.index; preview.show=true
}
function onPreview({ media, list }) { openFull(media, list) }

function handleEditCancel(){
  showEdit.value=false
  form.value=null
}
async function handleEditClose(){
  if (pendingClose) return
  pendingClose=true
  try{
    if(await composerRef.value?.requestClose()) handleEditCancel()
  }finally{ pendingClose=false }
}

watch([type, from, to, q, effectivePersonId], () => load())
watch(showEdit, (v) => store.setEditingRecord(v))
onUnmounted(() => store.setEditingRecord(false))
onMounted(load)
</script>
<style scoped>
.edit{ padding:14px; height:100%; overflow-y:auto }
</style>
