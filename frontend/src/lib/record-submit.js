import { normalizeTime } from './event-day.js'
import { normalizeEndedOn } from './meeting-span.js'
export function generateIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}
export function buildEventPayload(s) {
  const p = {person_id:Number(s.personId),type_key:s.type,event_date:s.eventDate,event_time:normalizeTime(s.eventTime),title:s.title||null,body:s.body||null,tags:s.tags||null,sensitivity:s.sensitivity||'normal'}
  if(s.extraIds?.length) p.person_ids=[...new Set([Number(s.personId),...s.extraIds.map(Number)])]
  else if(s.person_ids?.length) p.person_ids=[...s.person_ids]
  if(s.type==='meeting'){
    // 跨日：结束日送后端，过夜由后端派生，hours 不手填（多日折小时只会误导统计）
    const endedOn=normalizeEndedOn(s.eventDate,s.endedOn)
    Object.assign(p,{location:s.location||null,ended_on:endedOn})
    if(endedOn) Object.assign(p,{hours:null,overnight:true})
    else Object.assign(p,{hours:s.hours===''||s.hours==null?null:Number(s.hours),overnight:!!s.overnight})
  }
  return p
}
export function buildOutfitPayload(s) {
  const base=buildEventPayload(s)
  return {person_id:base.person_id,event_date:base.event_date,event_time:base.event_time,items:(s.picked||[]).map(p=>p.item_id?{item_id:p.item_id}:{category:p.category||'other',name:p.name,color:p.color||null}),note:s.note||null,tags:s.tags||null,sensitivity:s.sensitivity||'normal',location:s.location||null,person_ids:base.person_ids||null,title:s.manualText?s.title||null:null,body:s.manualText?s.body||null:null}
}
export function buildEditPayload(s) {
  const p=s.type==='outfit'?buildOutfitPayload(s):buildEventPayload(s)
  delete p.person_id; delete p.type_key; delete p.person_ids
  if(s.type==='outfit') {
    delete p.note; delete p.location
    if(!s.manualText) { delete p.title; delete p.body }
  }
  // Meeting details absent from older API responses must not be erased.
  if(s.type==='meeting' && !s.meetingLoaded) { delete p.location; delete p.hours; delete p.overnight; delete p.ended_on }
  return p
}
export function snapshotPayload(p) { return JSON.parse(JSON.stringify(p)) }
export function createAttachmentTasks(files) { return (files||[]).map(f=>{const id=generateIdempotencyKey();return {id,key:id,file:f.file||f,name:(f.file||f).name,status:'pending'}}) }
export async function uploadAttachments(api,tasks,context) {
  const failed=[]; let ok=0
  for(const task of tasks) {
    try {
      if(!task.key || !task.file) throw new Error('missing idempotency key or file')
      await api.uploadMedia(task.file,{person_id:context.person_id,event_id:context.event_id,captured_on:context.captured_on,idempotency_key:task.key})
      task.status='done'; ok++
    } catch(error) { task.status='failed'; failed.push({task,file:task.file,key:task.key,error}) }
  }
  return {ok,failed}
}
export async function submitRecord(api,payload,{isEdit,editId,isOutfit,idempotencyKey}={}) {
  return isEdit?api.patchEvent(editId,payload):isOutfit?api.createOutfit(payload,idempotencyKey):api.createEvent(payload,idempotencyKey)
}
export function createSubmissionManager() {
  return {
    snapshot:null,key:null,eventId:null,record:null,status:'idle',fileTasks:[],endpoint:null,locked:false,error:null,context:null,editId:null,
    isLocked(){return this.locked},
    begin({payload,typeKey,tasks,personId,capturedOn,editId}) {
      if(!this.snapshot) {
        this.eventId=null;this.record=null
        this.snapshot=snapshotPayload(payload);this.key=generateIdempotencyKey();this.endpoint=typeKey==='outfit'?'outfit':'event';this.fileTasks=(tasks||[]).map(t=>({...t}));this.context={person_id:Number(personId),captured_on:capturedOn};this.editId=editId||null;this.status='saving';this.error=null
      }
      return {payload:this.snapshot,key:this.key,eventId:this.eventId,fileTasks:this.fileTasks,endpoint:this.endpoint}
    },
    setEventId(id){this.eventId=id},
    retainAfterRecordSuccess(id){this.eventId=id},
    setPartial(failed){this.fileTasks=failed.map(f=>f.task||f);this.status='partial';this.locked=false},
    setUncertain(error){this.error=error;this.status='uncertain';this.locked=false},
    setValidationError(error){this.clear();this.error=error},
    setSuccess(){this.snapshot=null;this.key=null;this.fileTasks=[];this.endpoint=null;this.context=null;this.status='success';this.locked=false;this.error=null},
    clear(){Object.assign(this,{snapshot:null,key:null,eventId:null,record:null,status:'idle',fileTasks:[],endpoint:null,context:null,editId:null,locked:false,error:null})},
    isValidationError(e){return e?.status>=400 && e.status<500 && e.status!==408 && e.status!==409 && e.status!==429},
    isNetworkError(e){return !e?.status || e.status>=500 || e.status===408 || e.status===429},
    async run(api) {
      if(this.locked) return null
      if(!this.snapshot) throw new Error('No submission snapshot')
      this.locked=true
      try {
        if(!this.eventId) {
          this.record=await submitRecord(api,this.snapshot,{isEdit:!!this.editId,editId:this.editId,isOutfit:this.endpoint==='outfit',idempotencyKey:this.key})
          this.eventId=this.record?.id||this.editId
          if(!this.eventId) throw new Error('保存响应缺少记录 ID')
        }
        const result=await uploadAttachments(api,this.fileTasks,{...this.context,event_id:this.eventId})
        if(result.failed.length) this.setPartial(result.failed)
        else this.setSuccess()
        return {record:this.record,status:this.status,failed:result.failed}
      } catch(error) {
        // 409 means conflict/in-progress, never fabricated success.
        if(this.isValidationError(error)) this.setValidationError(error)
        else this.setUncertain(error)
        throw error
      } finally {this.locked=false}
    }
  }
}
