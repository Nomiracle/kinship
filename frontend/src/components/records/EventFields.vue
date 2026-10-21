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
        <van-field v-model="hoursModel" type="number" label="时长(小时)" placeholder="可留空" :disabled="disabled" />
        <van-cell title="过夜">
          <template #right-icon><van-switch v-model="overnightModel" size="20" :disabled="disabled" /></template>
        </van-cell>
      </template>
      <van-field v-if="type==='text'" v-model="tagsModel" label="标签" placeholder="逗号分隔，便于以后检索" :disabled="disabled" />
      <van-field v-if="type!=='text' && type!=='meeting' && type!=='period'" v-model="tagsModel" label="标签" placeholder="逗号分隔" :disabled="disabled" />
    </template>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({
  type: { type: String, default: 'text' },
  title: { type: String, default: '' },
  body: { type: String, default: '' },
  tags: { type: String, default: '' },
  location: { type: String, default: '' },
  hours: { type: String, default: '' },
  overnight: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:title','update:body','update:tags','update:location','update:hours','update:overnight'])
const titleModel = computed({ get:()=>props.title, set:v=>emit('update:title',v) })
const bodyModel = computed({ get:()=>props.body, set:v=>emit('update:body',v) })
const tagsModel = computed({ get:()=>props.tags, set:v=>emit('update:tags',v) })
const locationModel = computed({ get:()=>props.location, set:v=>emit('update:location',v) })
const hoursModel = computed({ get:()=>props.hours, set:v=>emit('update:hours',v) })
const overnightModel = computed({ get:()=>props.overnight, set:v=>emit('update:overnight',v) })
const showBody = computed(()=> ['text','health','mood'].includes(props.type))
const titleLabel = computed(()=> ({ text:'标题', period:'备注', meeting:'做了什么' }[props.type] || '标题'))
const titlePlaceholder = computed(()=> ({ text:'一句话概括', period:'可留空', meeting:'如：一起吃饭、双人开黑' }[props.type] || ''))
</script>
