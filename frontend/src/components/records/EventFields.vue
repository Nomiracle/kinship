<template>
  <div>
    <template v-if="type==='outfit'">
    </template>
    <template v-else>
      <van-field v-model="titleModel" :label="titleLabel" :placeholder="titlePlaceholder" :disabled="disabled" />
      <van-field
        v-if="showBody"
        v-model="bodyModel"
        type="textarea"
        rows="3"
        autosize
        label="详细"
        placeholder="她说过的、穿过的、发生的事…"
        :disabled="disabled"
      />
      <template v-if="type==='period'">
        <p class="muted" style="margin:6px 0">只记录开始日期。会同时落一条生理期明细，用于周期统计与提醒（预测误差约 ±3 天，仅作关怀提醒）。</p>
      </template>
      <template v-if="type==='meeting'">
        <van-field v-model="locationModel" label="地点" placeholder="在哪里" :disabled="disabled" />
        <!-- 跨日：像「周五去、周日回」这种，一条记录表达跨度，不用拆成三条 -->
        <van-cell title="跨天" :label="spans ? spanText : '打开后可填结束日期（多日相处记成一条）'">
          <template #right-icon><van-switch :model-value="spans" size="20" :disabled="disabled" @update:model-value="toggleSpan" /></template>
        </van-cell>
        <template v-if="spans">
          <div class="span-row">
            <label>结束日期<input :value="endedOnModel" type="date" class="picker" :disabled="disabled" :min="eventDate || undefined" @change="onEndChange" /></label>
            <span v-if="spanErr" class="danger" role="alert">{{ spanErr }}</span>
          </div>
          <p class="muted" style="margin:6px 0">跨日自动记为过夜，时长不再手填（多日折成小时没有意义）。</p>
        </template>
        <template v-else>
          <van-field v-model="hoursModel" type="number" label="时长(小时)" placeholder="可留空" :disabled="disabled" />
          <van-cell title="过夜">
            <template #right-icon><van-switch v-model="overnightModel" size="20" :disabled="disabled" /></template>
          </van-cell>
        </template>
      </template>
      <van-field v-if="type==='text'" v-model="tagsModel" label="标签" placeholder="逗号分隔，便于以后检索" :disabled="disabled" />
      <van-field v-if="type!=='text' && type!=='meeting' && type!=='period'" v-model="tagsModel" label="标签" placeholder="逗号分隔" :disabled="disabled" />
    </template>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { addDays, spanInfo, spanError } from '../../lib/meeting-span.js'
const props = defineProps({
  type: { type: String, default: 'text' },
  title: { type: String, default: '' },
  body: { type: String, default: '' },
  tags: { type: String, default: '' },
  location: { type: String, default: '' },
  hours: { type: String, default: '' },
  overnight: { type: Boolean, default: false },
  endedOn: { type: String, default: '' },
  eventDate: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:title','update:body','update:tags','update:location','update:hours','update:overnight','update:endedOn'])
const titleModel = computed({ get:()=>props.title, set:v=>emit('update:title',v) })
const bodyModel = computed({ get:()=>props.body, set:v=>emit('update:body',v) })
const tagsModel = computed({ get:()=>props.tags, set:v=>emit('update:tags',v) })
const locationModel = computed({ get:()=>props.location, set:v=>emit('update:location',v) })
const hoursModel = computed({ get:()=>props.hours, set:v=>emit('update:hours',v) })
const overnightModel = computed({ get:()=>props.overnight, set:v=>emit('update:overnight',v) })
const endedOnModel = computed(()=>props.endedOn || '')
const span = computed(()=>spanInfo(props.eventDate, props.endedOn))
const spans = computed(()=>span.value.spans)
const spanText = computed(()=>span.value.text)
const spanErr = computed(()=>spanError(props.eventDate, props.endedOn))
function toggleSpan(on){
  if(props.disabled) return
  // 打开时默认「到今天 +1 天」：结束日 = 开始日 + 1（没有开始日就留空，让用户自己填）
  emit('update:endedOn', on ? addDays(props.eventDate, 1) : '')
}
function onEndChange(event){ emit('update:endedOn', event.target.value || '') }
const showBody = computed(()=> ['text','health','mood'].includes(props.type))
const titleLabel = computed(()=> ({ text:'标题', period:'备注', meeting:'做了什么' }[props.type] || '标题'))
const titlePlaceholder = computed(()=> ({ text:'一句话概括', period:'可留空', meeting:'如：一起吃饭、双人开黑' }[props.type] || ''))
</script>
<style scoped>
.span-row { display:flex; flex-direction:column; gap:4px; padding:8px 16px }
.span-row label { display:flex; align-items:center; justify-content:space-between; gap:8px; font-size:14px }
</style>
