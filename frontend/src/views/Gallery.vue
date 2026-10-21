<template>
  <div>
    <section class="card">
      <div class="row"><h3>相册 · {{ items.length }} 张</h3><van-button size="small" plain @click="showUpload = !showUpload">上传照片</van-button></div>
      <p class="muted">按拍摄日期浏览。人物范围可在顶部切换，不改变其他页面。</p>
      <div v-if="showUpload">
        <label class="upload-owner">照片归属
          <select v-model="uploadPersonId" :disabled="uploading || retryPending" aria-label="照片归属"><option :value="null" disabled>请选择人物</option><option v-for="p in store.persons" :key="p.id" :value="p.id">{{ store.displayName(p) }}</option></select>
        </label>
        <van-field v-model="capturedOn" :disabled="uploading || retryPending" type="date" label="拍摄日期" />
        <van-uploader v-model="fileList" :disabled="uploading || retryPending" multiple :max-count="9" :preview-size="72" />
        <p v-if="retryPending" role="status" class="warn">部分照片待重试，已保留原归属和失败项；成功项不会重复上传。</p>
        <van-button block type="primary" :loading="uploading" @click="upload">{{ retryPending ? '重试失败照片' : '上传照片' }}</van-button>
      </div>
    </section>
    <div class="gallery-grid">
      <article v-for="m in items" :key="m.id" class="tile">
        <img v-if="m.kind === 'image'" :src="api.mediaUrl(m)" loading="lazy" alt="档案照片" @click="preview(m)" />
        <video v-else :src="api.mediaUrl(m, false)" controls playsinline />
        <div class="meta"><span>{{ m.captured_on || '未记拍摄日' }} · {{ ownerName(m) }}</span><button class="danger" @click.stop="remove(m)" aria-label="删除照片">删除</button></div>
      </article>
    </div>
    <van-image-preview v-model:show="showPreview" :images="previewImages" :start-position="previewIndex" />
    <van-empty v-if="!items.length" description="这个范围暂无照片" />
  </div>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { resolveScopedPerson } from '../lib/scope'
const store = useArchiveStore()
const route = useRoute()
const personId = computed(() => resolveScopedPerson(route.query.person, store.currentPersonId))
const items = ref([])
const uploadPersonId = ref(null)
const retryPending = ref(false)
const showUpload = ref(false)
const fileList = ref([])
const uploading = ref(false)
const capturedOn = ref(new Date().toLocaleDateString('sv-SE'))
const showPreview = ref(false)
const previewIndex = ref(0)
const imageItems = computed(() => items.value.filter(m => m.kind === 'image'))
const previewImages = computed(() => imageItems.value.map(m => api.mediaUrl(m, false)))
let uploadTarget = null
const uploadKeys = new WeakMap()
let loadVersion = 0
function ownerName(m) { return store.displayName(store.persons.find(p => p.id === m.person_id)) || '—' }
async function load() {
  const version = ++loadVersion
  try { const result = await api.media({ person_id: personId.value || undefined }); if(version === loadVersion) items.value = result }
  catch(e) { showToast(e.message || '加载照片失败') }
}
async function upload() {
  if (uploading.value) return
  if (!uploadPersonId.value) return showToast('请选择照片归属人物')
  if (!fileList.value.length) return showToast('先选图片')
  uploading.value = true
  uploadTarget ||= { person_id: Number(uploadPersonId.value), captured_on: capturedOn.value || undefined }
  const failed = []
  let ok = 0
  try {
    for (const item of fileList.value) {
      const raw = item.file || item
      try {
        if (!uploadKeys.has(raw)) uploadKeys.set(raw, crypto.randomUUID())
        await api.uploadMedia(raw, { ...uploadTarget, idempotency_key: uploadKeys.get(raw) })
        ok++
      } catch(e) { failed.push(item); showToast(`${raw.name || '文件'}：${e.message}`) }
    }
    fileList.value = failed
    retryPending.value = failed.length > 0
    if (!failed.length) uploadTarget = null
    if(ok) { showToast(`已上传 ${ok} 张`); await load() }
  } finally { uploading.value = false }
}
function preview(m) { previewIndex.value = imageItems.value.findIndex(x => x.id === m.id); showPreview.value = true }
async function remove(m) {
  try { await showConfirmDialog({ title:'删除照片', message:'将移除该照片引用；不再被其他档案使用的文件也会删除。确定？' }) }
  catch { return }
  try { await api.deleteMedia(m.id); await load() } catch(e) { showToast(e.message || '删除失败') }
}
watch(personId, () => { if(!retryPending.value && !uploading.value) uploadPersonId.value = personId.value; load() })
onMounted(async () => { await store.ensureLoaded(); uploadPersonId.value = personId.value; await load() })
</script>
<style scoped>
.gallery-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.tile { border-radius:var(--radius); overflow:hidden; background:var(--surface); border:1px solid var(--line); }
.tile img,.tile video { width:100%; aspect-ratio:1; object-fit:cover; display:block; }
.meta { display:flex; align-items:center; justify-content:space-between; padding:8px; gap:8px; color:var(--muted); font-size:11px; }
.meta button { border:0; background:none; min-height:40px; cursor:pointer; }
.upload-owner { display:flex; align-items:center; gap:12px; padding:12px 0; }
.upload-owner select { min-width:0; flex:1; padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--surface); }
@media(min-width:760px) { .gallery-grid { grid-template-columns:repeat(4,minmax(0,1fr)); } }
</style>
