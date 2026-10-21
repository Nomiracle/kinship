<template><RecordComposer :key="route.fullPath" initial-type="outfit" :preselect="preselect" session-key="wardrobe-new" @cancel="cancel" /></template>
<script setup>
import {computed} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {normalizePersonId} from '../lib/scope.js'
import RecordComposer from '../components/records/RecordComposer.vue'
const route=useRoute(),router=useRouter()
const preselect=computed(()=>[normalizePersonId(route.query.item)].filter(Boolean))
function cancel(){router.push({path:'/wardrobe',query:{person:route.query.person||'all'}})}
</script>
