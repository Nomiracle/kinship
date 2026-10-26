<template>
  <div>
    <section class="card"><h3>{{ isEdit?'编辑单品':'添加衣物' }}</h3><p class="muted">衣物是无日期的长期档案；仅后续保存穿搭才增加穿着次数。</p><p v-if="isEdit && initial" class="muted">归属：{{ store.displayName(store.persons.find(p=>p.id===initial.person_id)) }}</p></section>
    <WardrobeItemForm v-if="ready" ref="formRef" :key="formKey" :initial="initial" :persons="store.persons" :categories="store.wardrobeCategories" :effective-person-id="isEdit?initial?.person_id:effectivePersonId" :replace-candidates="replaceCandidates" :saving="saving" :uncertain="!!submissionPayload || !!createdItem" :partial="failedFiles.length>0" :error="error" :upload-error="uploadError" :duplicate="duplicate" :failed-files="failedFiles" :is-edit="isEdit" @submit="onSubmit" @cancel="onCancel" @openDuplicate="openDuplicate" @retry="retryFailed" />
    <section v-if="duplicate" class="card"><h3>同名同色已存在</h3><img v-if="duplicate.media?.[0]" :src="api.mediaUrl(duplicate.media[0])" alt="已有单品" style="width:96px;height:96px;object-fit:cover" /><p>{{ duplicate.name }} · {{ duplicate.color || '未记颜色' }} · {{ duplicate.wear_count ?? 0 }} 条穿着记录</p><van-button size="small" @click="openDuplicate">查看已有</van-button><van-button size="small" plain @click="duplicate=null">返回修改</van-button><p class="muted">不会自动合并。可打开已有单品复用，或修改名称后重试。</p></section>
    <section v-if="submissionPayload || createdItem" class="card" role="status">
      <h3 v-if="createdItem">{{ isEdit?'已保存：':'已创建：' }}{{ createdItem.name }}</h3><p v-if="createdItem" class="muted">{{ createdItem.wear_count }} 条穿着记录 · {{ createdItem.last_worn_on || '暂无穿着记录' }}</p>
      <p v-if="uncertain" class="warn">保存结果未确认；重试只使用原内容和原幂等键。</p><p v-if="failedFiles.length" class="warn">有 {{ failedFiles.length }} 张上传失败；重试不会重复创建衣物。</p>
      <van-button v-if="uncertain" block type="primary" :loading="saving" @click="performSave">重试保存</van-button>
      <van-button v-if="failedFiles.length" block type="primary" :loading="saving" @click="retryFailed">重试上传</van-button>
      <div v-if="createdItem && !failedFiles.length && !uncertain && !saving" class="chips"><van-button v-if="!isEdit" size="small" @click="continueAdd">继续添加</van-button><van-button size="small" @click="goOutfit">去记一次穿搭</van-button><van-button size="small" plain @click="goWardrobe">回衣橱</van-button></div>
    </section>
  </div>
</template>
<script setup>
import {computed,ref,onMounted,onBeforeUnmount,nextTick} from 'vue'
import {useRoute,useRouter,onBeforeRouteLeave,onBeforeRouteUpdate} from 'vue-router'
import {showToast,showConfirmDialog} from 'vant'
import {api} from '../api.js'
import {useArchiveStore} from '../store.js'
import {resolveScopedPerson} from '../lib/scope.js'
import {buildWardrobeItemPayload,validateWardrobeItem,generateIdempotencyKey,snapshotPayload,ensureFileStableKeys,uploadWardrobePhotos,scopeQueryPreserveAll} from '../lib/wardrobe-create.js'
import WardrobeItemForm from '../components/WardrobeItemForm.vue'
const route=useRoute(),router=useRouter(),store=useArchiveStore()
const isEdit=computed(()=>!!route.params.id)
const effectivePersonId=computed(()=>resolveScopedPerson(route.query.person,store.currentPersonId))
const initial=ref(null),ready=ref(false),formKey=ref(0),formRef=ref(null),saving=ref(false),error=ref(''),uploadError=ref(''),duplicate=ref(null),createdItem=ref(null),failedFiles=ref([]),uncertain=ref(false)
const replaceCandidates=ref([])
const submissionPayload=ref(null),submissionKey=ref(null)
let fileSnapshot=[],uploadContext=null,baseline='',allowLeave=false
const formSnapshot=()=>JSON.stringify(formRef.value?.form||{})
const dirty=computed(()=>!!submissionPayload.value||failedFiles.value.length>0||(!createdItem.value&&ready.value&&(formSnapshot()!==baseline||formRef.value?.fileList?.length>0)))
function navQuery(){return scopeQueryPreserveAll(effectivePersonId.value,route.query.person)}
async function load(){ready.value=false;try{await store.ensureLoaded();initial.value=isEdit.value?await api.wardrobeItem(route.params.id):null;replaceCandidates.value=(await api.wardrobeItems({include_offhand:true})).items||[];ready.value=true;formKey.value++;await nextTick();baseline=formSnapshot()}catch(e){error.value=e.message}}
onMounted(async()=>{await load();window.addEventListener('beforeunload',unload)})
onBeforeUnmount(()=>window.removeEventListener('beforeunload',unload))
function unload(e){if(dirty.value||saving.value){e.preventDefault();e.returnValue=''}}
async function confirmLeave(){if(allowLeave)return true;if(saving.value)return false;if(dirty.value){try{await showConfirmDialog({title:'确认离开',message:uncertain.value?'保存结果未确认，离开会丢失幂等重试上下文。仍要离开？':'有未保存或待重试的照片，确定离开？'})}catch{return false}}return true}
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(async()=>{if(!await confirmLeave())return false;clear();await nextTick();setTimeout(load,0);return true})
async function onCancel(){router.push({path:'/wardrobe',query:navQuery()})}
async function openDuplicate(){if(!duplicate.value?.id)return;router.push({path:`/wardrobe/items/${duplicate.value.id}/edit`,query:navQuery()})}
async function onSubmit(payload,files){
  if(saving.value||createdItem.value||submissionPayload.value)return
  const built=buildWardrobeItemPayload({...payload, personId:isEdit.value?initial.value.person_id:payload.person_id, replacesItemId:payload.replaces_item_id})
  const validation=validateWardrobeItem(built)
  if(!validation.valid){error.value=validation.errors[0];showToast(error.value);return}
  fileSnapshot=[...(files||[])];ensureFileStableKeys(fileSnapshot)
  submissionPayload.value=snapshotPayload(built);submissionKey.value=generateIdempotencyKey()
  uploadContext={person_id:built.person_id,captured_on:new Date().toLocaleDateString('sv-SE')}
  await performSave()
}
async function performSave(){
  if(saving.value||!submissionPayload.value)return
  saving.value=true;error.value='';duplicate.value=null
  try{
    const p=submissionPayload.value
    if(!createdItem.value){
      if(isEdit.value){const patch={...p};delete patch.person_id;createdItem.value=await api.patchWardrobeItem(route.params.id,patch)}
      else createdItem.value=await api.createWardrobeItem(p,submissionKey.value)
    }
    uncertain.value=false
    uploadContext.wardrobe_item_id=createdItem.value.id
    await uploadFiles(fileSnapshot)
    submissionPayload.value=null
    showToast(isEdit.value?'已保存':'已新建')
    baseline=formSnapshot()
  }catch(e){
    error.value=e.message||'保存失败'
    if(e.status===409&&e.detail?.existing_id){duplicate.value=await api.wardrobeItem(e.detail.existing_id).catch(()=>({id:e.detail.existing_id,name:submissionPayload.value.name}));submissionPayload.value=null;submissionKey.value=null}
    else if(e.status>=400&&e.status<500&&![408,409,429].includes(e.status)){submissionPayload.value=null;submissionKey.value=null}
    else uncertain.value=true
    showToast(error.value)
  }finally{saving.value=false}
}
async function uploadFiles(files){
  const result=await uploadWardrobePhotos(api,files,uploadContext)
  failedFiles.value=result.failed
  if(formRef.value)formRef.value.fileList=[...result.failed]
  uploadError.value=result.failed.length?'照片上传失败，已保留失败项供重试':''
}
async function retryFailed(){if(saving.value||!createdItem.value||!failedFiles.value.length)return;saving.value=true;try{await uploadFiles([...failedFiles.value])}finally{saving.value=false}}
function clear(){initial.value=null;submissionPayload.value=null;submissionKey.value=null;createdItem.value=null;failedFiles.value=[];uncertain.value=false;error.value='';uploadError.value='';duplicate.value=null;fileSnapshot=[];uploadContext=null}
async function continueAdd(){if(saving.value||failedFiles.value.length||uncertain.value)return;clear();formKey.value++;await nextTick();baseline=formSnapshot()}
function goOutfit(){if(!createdItem.value)return;router.push({path:'/wardrobe/new',query:{person:createdItem.value.person_id,item:createdItem.value.id}})}
function goWardrobe(){router.push({path:'/wardrobe',query:navQuery()})}
</script>
