<template>
  <RecordComposer :key="route.fullPath" :initial="null" :initialType="initialType" :preselect="preselect" sessionKey="new-record" @cancel="onCancel" />
</template>
<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { normalizePersonId } from '../lib/scope.js'
import RecordComposer from '../components/records/RecordComposer.vue'
const route = useRoute()
const router = useRouter()
const initialType = computed(()=>{
  const t = route.query.type
  return typeof t==='string' && t ? t : 'text'
})
const preselect = computed(()=>{
  const v = normalizePersonId(route.query.item)
  return v ? [v] : []
})
function onCancel(){ router.push({path:'/timeline',query:{person:route.query.person||'all'}}) }
</script>
