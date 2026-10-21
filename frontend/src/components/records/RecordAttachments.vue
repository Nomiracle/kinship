<template>
  <div>
    <div class="muted" style="margin-bottom:6px">{{ hint }}</div>
    <div v-if="existingMedia && existingMedia.length" class="thumbs" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">
      <div v-for="m in existingMedia" :key="m.id" style="position:relative">
        <img v-if="m.kind!=='video'" :src="api.mediaUrl(m)" style="width:72px;height:72px;object-fit:cover;border-radius:6px" @click="$emit('preview', m)" />
        <div v-else style="width:72px;height:72px;background:#ebedf0;display:flex;align-items:center;justify-content:center;border-radius:6px" @click="$emit('preview', m)">▶</div>
        <span v-if="editable && mediaEnabled && !disabled" style="position:absolute;top:-8px;right:-8px;width:24px;height:24px;border-radius:50%;background:rgba(0,0,0,0.6);color:#fff;text-align:center;line-height:24px;cursor:pointer" @click="$emit('remove', m)">×</span>
      </div>
    </div>
    <van-uploader :model-value="fileTasks" :disabled="!mediaEnabled || disabled" multiple :max-count="9" :preview-size="64" :after-read="onAfterRead" @delete="onDelete" />
    <p v-if="!mediaEnabled" class="muted" style="margin-top:6px">（这个人没开「图片」模块，附件区已隐藏）</p>
    <p v-if="uploadStatus" class="muted" style="margin-top:6px">{{ uploadStatus }}</p>
  </div>
</template>
<script setup>
import { api } from '../../api.js'
import { generateIdempotencyKey } from '../../lib/record-submit.js'
const props = defineProps({
  mediaEnabled: { type: Boolean, default: true },
  fileTasks: { type: Array, default: ()=>[] },
  existingMedia: { type: Array, default: ()=>[] },
  hint: { type: String, default: '图片（可选，可多选；iPhone 拍的 HEIC 会自动转）' },
  uploadStatus: { type: String, default: '' },
  editable: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:fileTasks','preview','remove'])
function onAfterRead(file) {
  const list = Array.isArray(file) ? file : [file]
  const tasks = list.map(f=>{
    const raw = f.file || f
    return { ...f, id: generateIdempotencyKey(), key: generateIdempotencyKey(), file: raw, name: raw.name || '', status: 'pending' }
  })
  emit('update:fileTasks', [...props.fileTasks, ...tasks])
}
function onDelete(file, detail) {
  const idx = detail.index
  const next = [...props.fileTasks]
  next.splice(idx,1)
  emit('update:fileTasks', next)
}
</script>
