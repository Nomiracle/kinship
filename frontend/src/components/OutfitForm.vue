<template>
  <div>
    <div v-if="personId && outfitState===false">
      <div class="card">
        <h3>这次穿了什么</h3>
        <p class="muted">请选择已有的衣物，或临时添加新单品（保存时才建档）。</p>
        <div class="chips" style="margin-bottom:6px">
          <van-tag v-for="c in store.wardrobeCategories" :key="c.key" :type="pickCategory===c.key?'primary':'default'" @click="pickCategory=c.key">{{ c.label }}</van-tag>
        </div>
        <div class="chips" style="margin-bottom:8px">
          <van-tag v-for="it in itemsOfCategory" :key="it.id" :type="isPicked(it)?'primary':'default'" size="large" @click="togglePick(it)">{{ it.name }}<span class="muted"> · 穿{{ it.wear_count }}</span></van-tag>
          <span v-if="!itemsOfCategory.length" class="muted">这个类别还没有单品 —— 在下面直接新建</span>
        </div>
        <van-field v-model="newName" label="新单品" :placeholder="'名称，如：' + pickCategoryLabel + '一件'" />
        <van-field v-model="newColor" label="颜色" placeholder="可空" />
        <van-button size="small" plain style="margin-top:6px" @click="addNew">＋ 加进来</van-button>
        <div v-if="pickedAll" class="picked-row">
          <div class="muted">已选 {{ pickedAll }} 件（点一下取消）：</div>
          <div class="chips" style="margin-top:4px">
            <van-tag v-for="p in picked" :key="'i'+p.item_id" closable size="large" @click="unpick(p.item_id)">{{ nameOf(p.item_id) }}</van-tag>
            <van-tag v-for="(n,i) in newItems" :key="'n'+i" closable size="large" @click="newItems.splice(i,1)">{{ n.name }}<span v-if="n.color">（{{ n.color }}）</span></van-tag>
          </div>
        </div>
        <p class="muted" style="margin:6px 0 0">本次选了 {{ pickedAll }} 件 —— 保存后只生成 1 条穿搭记录；同名单品会复用已有的，不会重复建。</p>
        <p class="muted" style="margin:10px 0 0">选好点「确定」回到上层 —— 这时还<strong>没有</strong>记下来，上层点「保存」才算真记。</p>
        <div style="display:flex;gap:8px;margin-top:10px">
          <van-button block plain @click="cancelPick">取消</van-button>
          <van-button block type="primary" @click="confirmPick">确定（已选 {{ pickedAll }} 件）</van-button>
        </div>
      </div>
    </div>
    <div v-else>
      <div class="card">
        <h3>这次穿了什么</h3>
        <div class="chips" style="margin-bottom:6px">
          <van-tag v-for="c in store.wardrobeCategories" :key="c.key" :type="pickCategory===c.key?'primary':'default'" @click="pickCategory=c.key">{{ c.label }}</van-tag>
        </div>
        <div class="chips" style="margin-bottom:8px">
          <van-tag v-for="it in itemsOfCategory" :key="it.id" :type="isPicked(it)?'primary':'default'" size="large" @click="togglePick(it)">{{ it.name }}<span class="muted"> · 穿{{ it.wear_count }}</span></van-tag>
          <span v-if="!itemsOfCategory.length" class="muted">这个类别还没有单品 —— 在下面直接新建</span>
        </div>
        <van-field v-model="newName" label="新单品" :placeholder="'名称，如：' + pickCategoryLabel + '一件'" />
        <van-field v-model="newColor" label="颜色" placeholder="可空" />
        <van-button size="small" plain style="margin-top:6px" @click="addNew">＋ 加进来</van-button>
        <div v-if="pickedAll" class="picked-row">
          <div class="muted">已选 {{ pickedAll }} 件（点一下取消）：</div>
          <div class="chips" style="margin-top:4px">
            <van-tag v-for="p in picked" :key="'i'+p.item_id" closable size="large" @click="unpick(p.item_id)">{{ nameOf(p.item_id) }}</van-tag>
            <van-tag v-for="(n,i) in newItems" :key="'n'+i" closable size="large" @click="newItems.splice(i,1)">{{ n.name }}<span v-if="n.color">（{{ n.color }}）</span></van-tag>
          </div>
        </div>
        <p class="muted" style="margin:6px 0 0">本次选了 {{ pickedAll }} 件 —— 保存后只生成 1 条穿搭记录；同名单品会复用已有的，不会重复建。</p>
        <p class="muted" style="margin:10px 0 0">选好点「确定」回到上层 —— 这时还<strong>没有</strong>记下来，上层点「保存」才算真记。</p>
        <div style="display:flex;gap:8px;margin-top:10px">
          <van-button block plain @click="cancelPick">取消</van-button>
          <van-button block type="primary" @click="confirmPick">确定（已选 {{ pickedAll }} 件）</van-button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { showToast } from 'vant'
import { api } from '../api.js'
import { useArchiveStore } from '../store.js'

const props = defineProps({
  personId: { type: Number, required: true },
  preselect: { type: Array, default: ()=>[] },
  mode: { type: String, default: 'save' },
  initial: { type: Array, default: ()=>[] },
})
const pickMode = computed(() => props.mode === 'pick')
const emit = defineEmits(['confirm','cancel'])

const store = useArchiveStore()
const wardrobeItems = ref([])
const pickCategory = ref('top')
const picked = ref([])
const newItems = ref([])
const newName = ref('')
const newColor = ref('')

const pickCategoryLabel = computed(()=> store.wardrobeCategoryLabel(pickCategory.value))
// 可选清单只出「在手」的；已卖出/送人的仍留在 wardrobeItems 里，供历史穿搭回显名字与照片
const itemsOfCategory = computed(()=> wardrobeItems.value.filter(i=> i.category===pickCategory.value && !i.merged_into_id && (i.status==='in_use'||i.status==='idle')))
const pickedAll = computed(()=> picked.value.length + newItems.value.length)

function nameOf(itemId){ const it=wardrobeItems.value.find(x=>x.id===itemId); return it? it.name : '#'+itemId }
function isPicked(it){ return picked.value.some(p=>p.item_id===it.id) }
function togglePick(it){
  const i=picked.value.findIndex(p=>p.item_id===it.id)
  if(i>=0) picked.value.splice(i,1)
  else picked.value.push({ item_id:it.id, category:it.category, name:it.name, color:it.color, media: it.media||[] })
}
function unpick(itemId){ const i=picked.value.findIndex(p=>p.item_id===itemId); if(i>=0) picked.value.splice(i,1) }
function addNew(){
  const name=newName.value.trim()
  if(!name){ showToast('先填名称'); return }
  newItems.value.push({ category: pickCategory.value, name, color: newColor.value||null })
  newName.value=''; newColor.value=''
}
async function loadItems(){
  try{ const res=await api.wardrobeItems({ person_id: props.personId, include_offhand: true }); wardrobeItems.value=res.items||[] }catch{ wardrobeItems.value=[] }
  applyPreselect()
  applyInitial()
}
function pushItem(it){
  if(picked.value.some(p=>p.item_id===it.id)) return
  picked.value.push({ item_id:it.id, category:it.category, name:it.name, color:it.color, media: it.media||[] })
}
function applyPreselect(){
  const ids=(props.preselect||[]).map(Number).filter(Boolean)
  for(const id of ids){ const it=wardrobeItems.value.find(x=>x.id===id && !x.merged_into_id); if(it){ pushItem(it); pickCategory.value=it.category } }
}
function applyInitial(){
  for(const p of props.initial||[]){
    if(p && p.item_id){ const it=wardrobeItems.value.find(x=>x.id===p.item_id && !x.merged_into_id); if(it) pushItem(it); else if(!picked.value.some(x=>x.item_id===p.item_id)) picked.value.push({ item_id:p.item_id, category:p.category||'other', name:p.name||'', color:p.color||null, media:p.media||[] }); continue }
    if(p && p.name){ if(!newItems.value.some(n=>n.name===p.name && n.category===(p.category||'other'))) newItems.value.push({ category:p.category||'other', name:p.name, color:p.color||null }) }
  }
}
function selection(){
  return [
    ...picked.value.map(p=>({ item_id:p.item_id, category:p.category, name:p.name, color:p.color||null, media:p.media||[] })),
    ...newItems.value.map(n=>({ category:n.category, name:n.name, color:n.color||null, media:[] })),
  ]
}
function confirmPick(){ emit('confirm', { items: selection() }) }
function cancelPick(){ emit('cancel') }

onMounted(()=>{ if(store.persons.length===0) store.ensureLoaded(); loadItems() })
watch([()=>props.personId, ()=>(props.preselect||[]).join(',')], async ()=>{ picked.value=[]; newItems.value=[]; newName.value=''; newColor.value=''; await loadItems() }, { flush:'post' })
</script>
<style scoped>
.picked-row{ margin:10px 0; padding:8px; background:#f7f8fa; border-radius:8px }
</style>
