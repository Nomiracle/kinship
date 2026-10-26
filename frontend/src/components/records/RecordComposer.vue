<template>
  <div class="record-composer">
    <fieldset :disabled="frozen" class="composer-fields">
      <section class="card">
        <h3>记录谁</h3>
        <select :value="draft.personId ?? ''" class="picker" aria-label="记录归属人" :disabled="isEdit || frozen || switching" @change="pickPerson">
          <option value="" disabled>请选择人物</option><option v-for="p in store.persons" :key="p.id" :value="p.id">{{ store.displayName(p) }}</option>
        </select>
        <template v-if="!isEdit"><p class="muted">同时关联其他人（可选）</p><div class="chips"><van-tag v-for="p in store.persons.filter(p=>p.id!==draft.personId)" :key="p.id" :type="draft.extraIds.includes(p.id)?'primary':'default'" @click="toggleExtra(p.id)">{{ store.displayName(p) }}</van-tag></div></template>
      </section>
      <section class="card">
        <h3>记什么</h3><div class="chips"><button v-for="t in availableTypes" :key="t.key" class="type-chip" :class="{active:draft.type===t.key}" :disabled="isEdit || frozen || switching" @click="draft.type=t.key">{{ t.label }}</button></div>
        <p v-if="isEdit" class="muted">编辑时保留原人物与类型</p>
      </section>
      <p v-if="draft.type==='outfit' && outfitUnavailable" class="card warn">此人物尚未开启服装模块。请先到人物管理开启。</p>
      <OutfitFields v-if="draft.type==='outfit'" type="outfit" :picked="draft.picked" :note="draft.note" :tags="draft.tags" :manual-text="draft.manualText" :title="draft.title" :body="draft.body" :disabled="frozen || switching || outfitUnavailable" @update:picked="draft.picked=$event" @update:note="draft.note=$event" @update:tags="draft.tags=$event" @update:manualText="draft.manualText=$event" @update:title="draft.title=$event" @update:body="draft.body=$event" @open-picker="openPicker" />
      <section class="card">
        <h3>哪一天</h3><div class="chips"><van-button size="small" @click="setToday">今天</van-button><van-button size="small" @click="shiftDate(-1)">昨天</van-button><van-button size="small" @click="shiftDate(-2)">前天</van-button></div>
        <div class="date-fields"><label>日期<input v-model="draft.eventDate" type="date" class="picker" aria-label="发生日期" /></label><label>时间（可选）<input v-model="draft.eventTime" type="time" step="1" class="picker" aria-label="发生时间" /></label></div>
        <div class="chips"><van-button size="small" plain @click="draft.eventTime=nowLocalTime()">此刻</van-button><van-button v-if="draft.eventTime" size="small" plain @click="draft.eventTime=''">只记到日（清掉时间）</van-button></div>
        <p class="muted">发生：{{ draft.eventDate }} {{ draft.eventTime || '仅记日期，不代表凌晨' }}</p>
      </section>
      <section class="card"><h3>内容</h3><EventFields v-if="draft.type!=='outfit'" :type="draft.type" :title="draft.title" :body="draft.body" :tags="draft.tags" :location="draft.location" :hours="draft.hours" :overnight="draft.overnight" :ended-on="draft.endedOn" :event-date="draft.eventDate" :disabled="frozen" @update:title="draft.title=$event" @update:body="draft.body=$event" @update:tags="draft.tags=$event" @update:location="draft.location=$event" @update:hours="draft.hours=$event" @update:overnight="draft.overnight=$event" @update:ended-on="draft.endedOn=$event" />
        <RecordAttachments :media-enabled="mediaEnabled" :file-tasks="draft.fileTasks" :existing-media="existingMedia" :disabled="frozen" @update:fileTasks="draft.fileTasks=$event" @preview="openPreview" @remove="removeMedia" />
      </section>
    </fieldset>
    <section class="card composer-actions" role="status">
      <p v-if="submission.status==='partial'" class="warn">记录已保存，图片待重试（{{ submission.fileTasks.length }} 张）。只重传失败项，不再创建记录。</p>
      <p v-else-if="submission.status==='uncertain'" class="warn">网络不确定：保存结果未确认，重试将使用原幂等键和原内容。</p>
      <p v-else-if="submission.status==='success'">✓ 全部成功</p>
      <p v-if="error" class="danger" role="alert">{{ error }}</p>
      <van-button block type="primary" :loading="busy" :disabled="switching || initializing" @click="submit">{{ submission.status==='partial' ? '重试上传' : submission.status==='uncertain' ? '重试保存' : '保存' }}</van-button>
      <van-button block plain :disabled="busy" style="margin-top:8px" @click="cancel">取消</van-button>
    </section>
    <section v-if="!isEdit && recent.length" class="card"><h3>刚记的</h3><div v-for="r in recent" :key="r.id" class="recent"><strong>{{ privateRecord(r)?'●●●':r.title||r.body?.slice(0,30)||'（无内容）' }}</strong><p class="muted">{{ store.displayName(store.persons.find(p=>p.id===r.person_id)) }} · {{ fmtWhen(r) }}</p></div></section>
    <van-popup v-model:show="showPicker" position="bottom" round :style="{height:'86%'}" :close-on-click-overlay="false"><div v-if="showPicker" class="pick-wrap"><h3>选择衣物 · {{ personLabel }}</h3><OutfitForm mode="pick" :person-id="draft.personId" :initial="draft.picked" @confirm="confirmPick" @cancel="showPicker=false" /></div></van-popup>
    <van-image-preview v-model:show="preview.show" :images="preview.images" :start-position="preview.index" />
  </div>
</template>
<script setup>
import {computed,reactive,ref,onMounted,onBeforeUnmount,watch,nextTick} from 'vue'
import {useRoute,onBeforeRouteLeave,onBeforeRouteUpdate} from 'vue-router'
import {showConfirmDialog,showToast} from 'vant'
import {api} from '../../api.js'
import {useArchiveStore} from '../../store.js'
import {resolveScopedPerson,normalizePersonId} from '../../lib/scope.js'
import {availableEventTypes} from '../../lib/modules.js'
import {todayStr,nowLocalTime,fmtWhen} from '../../lib/event-day.js'
import {createInitialState,snapshotDraft,isDirty,saveSessionDraft,loadSessionDraft,clearSessionDraft} from '../../lib/record-draft.js'
import {spanError} from '../../lib/meeting-span.js'
import {buildEventPayload,buildOutfitPayload,buildEditPayload,createSubmissionManager} from '../../lib/record-submit.js'
import {previewUrls} from '../../lib/media-preview.js'
import OutfitForm from '../OutfitForm.vue'
import EventFields from './EventFields.vue'
import OutfitFields from './OutfitFields.vue'
import RecordAttachments from './RecordAttachments.vue'
const props=defineProps({initial:{type:Object,default:null},initialType:{type:String,default:'text'},preselect:{type:Array,default:()=>[]},sessionKey:{type:String,default:''}})
const emit=defineEmits(['saved','cancel'])
const route=useRoute(),store=useArchiveStore()
const isEdit=computed(()=>!!props.initial?.id)
const draft=reactive(createInitialState({initial:props.initial,initialType:props.initialType,preselect:props.preselect}))
const submission=reactive(createSubmissionManager())
const initializing=ref(true),switching=ref(false),confirming=ref(false),error=ref(''),modules=ref(null),recent=ref([]),showPicker=ref(false),existingMedia=ref([...(props.initial?.media||[])])
const baseline=ref(''),preview=reactive({show:false,images:[],index:0})
const busy=computed(()=>submission.locked||confirming.value)
const frozen=computed(()=>busy.value||!!submission.snapshot)
const dirty=computed(()=>!!submission.snapshot||isDirty(draft,baseline.value))
const mediaEnabled=computed(()=>modules.value===null||modules.value.includes('media'))
const outfitUnavailable=computed(()=>modules.value!==null&&!modules.value.includes('outfit'))
const personLabel=computed(()=>store.displayName(store.persons.find(p=>p.id===draft.personId)))
const draftKey=computed(()=>`${props.sessionKey}:${route.query.person??'default'}:${route.query.item??''}`)
const availableTypes=computed(()=>{
  if(isEdit.value) return [store.eventTypes.find(t=>t.key===draft.type)||{key:draft.type,label:draft.type}]
  const types=availableEventTypes(store.eventTypes,modules.value||[])
  if(props.initialType==='outfit'&&!types.some(t=>t.key==='outfit')) return [{key:'outfit',label:'穿搭'},...types]
  return types
})
let moduleVersion=0
async function loadModules(){const version=++moduleVersion;modules.value=null;if(!draft.personId){modules.value=[];return}try{const r=await api.modules(draft.personId);if(version===moduleVersion)modules.value=r.enabled||[]}catch(e){if(version===moduleVersion)error.value=e.message}}
async function loadRecent(){try{const r=await api.events({person_id:draft.personId||undefined,order:'created',limit:5});recent.value=r.items||[]}catch{}}
function privateRecord(r){return store.privacyMode&&r.sensitivity==='sensitive'}
function toggleExtra(id){if(frozen.value)return;const i=draft.extraIds.indexOf(id);if(i<0)draft.extraIds.push(id);else draft.extraIds.splice(i,1)}
async function pickPerson(event){
  const id=normalizePersonId(event.target.value),old=draft.personId
  event.target.value=old??''
  if(id===old||frozen.value||isEdit.value||switching.value)return
  switching.value=true
  try{if(draft.picked.length){await showConfirmDialog({title:'切换人物',message:'换人会丢弃已选衣物，确定换人吗？',confirmButtonText:'丢弃并换人',cancelButtonText:'留在这个人'});draft.picked=[]}draft.personId=id;draft.extraIds=draft.extraIds.filter(x=>x!==id);await loadModules();await loadRecent()}
  catch{}finally{switching.value=false;await nextTick();event.target.value=draft.personId??''}
}
function setToday(){if(frozen.value)return;draft.eventDate=todayStr();draft.eventTime=nowLocalTime()}
function shiftDate(days){if(frozen.value)return;const d=new Date();d.setDate(d.getDate()+days);draft.eventDate=todayStr(d);draft.eventTime=''}
function openPicker(){if(frozen.value||switching.value)return;if(!draft.personId)return showToast('先选一个人');showPicker.value=true}
function confirmPick(p){draft.picked=p.items||[];showPicker.value=false}
async function submit(){
  if(busy.value||switching.value||initializing.value)return
  if(!draft.personId)return showToast('先选一个人')
  if(!draft.eventDate)return showToast('先选日期')
  if(draft.type==='meeting'){const spanIssue=spanError(draft.eventDate,draft.endedOn);if(spanIssue)return showToast(spanIssue)}
  if(draft.type==='outfit'&&outfitUnavailable.value&&!isEdit.value)return showToast('请先开启服装模块')
  error.value=''
  if(!submission.snapshot){
    confirming.value=true
    try{
      if(draft.eventDate!==todayStr())await showConfirmDialog({title:'确认日期',message:`确定记到 ${draft.eventDate} 吗？`,confirmButtonText:'就是这天',cancelButtonText:'返回修改'})
      if(draft.type==='outfit'&&!draft.picked.length)await showConfirmDialog({title:'这次没有勾单品',message:'仅保存事件，不增加任何单品穿着次数。',confirmButtonText:'就这样保存',cancelButtonText:'去选衣物'})
      const payload=isEdit.value?buildEditPayload(draft):draft.type==='outfit'?buildOutfitPayload(draft):buildEventPayload(draft)
      submission.begin({payload,typeKey:draft.type,tasks:draft.fileTasks,personId:draft.personId,capturedOn:draft.eventDate,editId:props.initial?.id})
    }catch{return}finally{confirming.value=false}
  }
  try{
    const result=await submission.run(api)
    if(!result)return
    if(result.status==='partial'){draft.fileTasks=submission.fileTasks;showToast('记录已保存，图片待重试');return}
    showToast(isEdit.value?'已保存':'已记录')
    draft.fileTasks=[]
    if(!isEdit.value){draft.title='';draft.body='';draft.tags='';draft.location='';draft.hours='';draft.overnight=false;draft.endedOn='';draft.note='';draft.picked=[];draft.manualText=false;draft.extraIds=[];setToday()}
    baseline.value=snapshotDraft(draft)
    if(props.sessionKey)clearSessionDraft(draftKey.value)
    emit('saved',result.record)
    await loadRecent()
  }catch(e){error.value=e.message||'保存失败';showToast(error.value)}
}
let closeApproved=false
async function requestClose(){
  if(closeApproved)return true
  if(busy.value)return false
  if(dirty.value){try{await showConfirmDialog({title:'放弃编辑？',message:submission.status==='partial'?'记录已保存，离开将丢失失败照片的重试上下文。确定？':submission.status==='uncertain'?'保存结果未确认，离开将丢失原幂等键。请优先重试确认。仍要离开？':'有未保存的改动，确定离开吗？',confirmButtonText:'放弃',cancelButtonText:'继续编辑'})}catch{return false}}
  if(props.sessionKey)clearSessionDraft(draftKey.value)
  closeApproved=true
  return true
}
async function cancel(){if(await requestClose())emit('cancel')}
onBeforeRouteLeave(requestClose)
onBeforeRouteUpdate(async(to)=>{if(to.query.person!==route.query.person||to.query.item!==route.query.item)return requestClose();return true})
function unload(e){if(dirty.value||busy.value){e.preventDefault();e.returnValue=''}}

function openPreview(m){if(m.kind==='video'){window.open(api.mediaUrl(m,false),'_blank','noopener');return}const p=previewUrls(existingMedia.value,m,api.mediaUrl);preview.images=p.images;preview.index=p.index;preview.show=true}
async function removeMedia(m){if(frozen.value||!mediaEnabled.value)return;try{await showConfirmDialog({title:'删除图片',message:'删除立即生效，取消编辑不能撤销。确定？'});await api.deleteMedia(m.id);existingMedia.value=existingMedia.value.filter(x=>x.id!==m.id)}catch(e){if(e?.message)showToast(e.message)}}
watch(()=>snapshotDraft(draft),()=>{if(!initializing.value&&props.sessionKey&&!submission.snapshot)saveSessionDraft(draftKey.value,draft)})
onMounted(async()=>{
  await store.ensureLoaded()
  if(!isEdit.value){
    const saved=props.sessionKey?loadSessionDraft(draftKey.value):null
    if(saved)Object.assign(draft,saved)
    if(!saved)draft.personId=resolveScopedPerson(route.query.person,store.currentPersonId)
    if(!draft.eventDate)setToday()
  }
  await loadModules()
  // Validate and hydrate old person/item deep links. Foreign/missing items never
  // enter the draft, but existing historical edit refs remain untouched.
  if(!isEdit.value&&draft.picked.length){const r=await api.wardrobeItems({person_id:draft.personId||undefined});draft.picked=draft.picked.flatMap(p=>{const item=r.items.find(i=>i.id===p.item_id&&i.person_id===draft.personId);return p.item_id?(item?[{...item,item_id:item.id}]:[]):[p]})}
  baseline.value=snapshotDraft(draft)
  initializing.value=false
  await loadRecent()
  window.addEventListener('beforeunload',unload)
})
onBeforeUnmount(()=>window.removeEventListener('beforeunload',unload))
defineExpose({requestClose,dirty})
</script>
<style scoped>
.composer-fields{padding:0;margin:0;border:0;min-width:0}.picker{width:100%;min-width:0;border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--surface)}.date-fields{display:flex;gap:10px;margin:14px 0}.date-fields label{flex:1;min-width:0;font-size:12px;color:var(--muted)}.type-chip{padding:8px 12px;min-height:40px;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--ink)}.type-chip.active{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}.pick-wrap{height:100%;padding:16px;overflow:auto}.recent{padding:10px 0;border-top:1px solid var(--line)}.composer-actions{padding-bottom:calc(16px + var(--safe-bottom))}
</style>
