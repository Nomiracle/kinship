<template>
  <div class="card" v-if="type==='outfit'">
    <h3>穿搭 · 选了哪几件</h3>
    <p class="muted" style="margin:0 0 8px">先点「选择衣物」在弹层里勾（单品挂在人名下，记谁就选谁的衣橱）。选好回到这里，底部点「保存」才真记下来。</p>
    <div v-if="picked.length" class="picked-grid">
      <div v-for="p in picked" :key="pickKey(p)" class="picked-item">
        <img v-if="thumbOf(p)" :src="thumbOf(p)" :alt="p.name" />
        <span v-else class="picked-ph">{{ categoryLabel(p.category) }}</span>
        <div class="picked-name">{{ pickLabel(p) }}</div>
      </div>
    </div>
    <p v-else class="muted" style="margin:0 0 8px">还没选衣物 —— 点下面按钮打开衣橱勾选</p>
    <div style="display:flex;gap:8px">
      <van-button size="small" type="primary" :disabled="disabled" @click="$emit('open-picker')">选择衣物</van-button>
      <van-button v-if="picked.length" size="small" plain :disabled="disabled" @click="$emit('update:picked', [])">清空</van-button>
    </div>
    <p class="muted" style="margin:8px 0 0">已选 {{ picked.length }} 件 —— 保存后只生成 1 条穿搭记录；同名单品会复用已有的，不会重复建。</p>
    <van-field v-model="noteModel" label="备注" placeholder="这次穿搭的备注（可空）" :disabled="disabled" />
    <van-field v-model="tagsModel" label="标签" placeholder="逗号分隔，便于以后检索" :disabled="disabled" />
    <van-cell title="手改标题 / 正文"><template #right-icon><van-switch v-model="manualModel" size="20" :disabled="disabled" /></template></van-cell>
    <template v-if="manualText">
      <van-field v-model="titleModel" label="标题" placeholder="留空则按单品自动生成" :disabled="disabled" />
      <van-field v-model="bodyModel" type="textarea" rows="3" autosize label="正文" placeholder="留空则按单品自动生成" :disabled="disabled" />
    </template>
    <p class="muted">不手改时，标题/正文按勾选的单品自动生成（单品才是真源）。</p>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { pickKey, pickLabel, itemThumb } from '../../lib/outfit-pick.js'
import { useArchiveStore } from '../../store.js'
import { api } from '../../api.js'
const props = defineProps({
  type: String,
  picked: { type: Array, default: ()=>[] },
  note: { type: String, default: '' },
  tags: { type: String, default: '' },
  manualText: { type: Boolean, default: false },
  title: { type: String, default: '' },
  body: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:picked','update:note','update:tags','update:manualText','update:title','update:body','open-picker'])
const store = useArchiveStore()
const noteModel = computed({ get:()=>props.note, set:v=>emit('update:note',v) })
const tagsModel = computed({ get:()=>props.tags, set:v=>emit('update:tags',v) })
const manualModel = computed({ get:()=>props.manualText, set:v=>emit('update:manualText',v) })
const titleModel = computed({ get:()=>props.title, set:v=>emit('update:title',v) })
const bodyModel = computed({ get:()=>props.body, set:v=>emit('update:body',v) })
function thumbOf(p){ return itemThumb(p, api.mediaUrl) }
function categoryLabel(k){ return store.wardrobeCategoryLabel(k) }
</script>
<style scoped>
.picked-grid{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:8px }
.picked-item{ width:72px }
.picked-item img,.picked-ph{ width:72px; height:72px; border-radius:8px; display:block; background:#f2f3f5; object-fit:cover }
.picked-ph{ color:#969799; font-size:12px; display:flex; align-items:center; justify-content:center }
.picked-name{ font-size:12px; color:#323233; margin-top:2px; word-break:break-all }
</style>
