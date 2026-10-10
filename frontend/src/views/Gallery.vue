<template>
  <div>
    <div class="card">
      <h3>相册（{{ items.length }} 张）</h3>
      <div class="chips" style="margin-bottom: 8px">
        <van-tag
          :type="personId ? 'default' : 'primary'"
          size="large"
          @click="setPerson(null)"
        >
          全部
        </van-tag>
        <van-tag
          v-for="p in store.others"
          :key="p.id"
          :type="personId === p.id ? 'primary' : 'default'"
          size="large"
          @click="setPerson(p.id)"
        >
          {{ p.display_name }}
        </van-tag>
      </div>
      <p class="muted">
        图片存在部署目录的 media/ 下（仓库之外），按年月分目录，缩略图 800px。拍摄日期 {{ capturedOn || '（用今天）' }}
      </p>
      <van-field v-model="capturedOn" type="date" label="拍摄日期" />
      <van-uploader v-model="fileList" multiple :max-count="9" :preview-size="72" />
      <van-button
        block
        type="primary"
        style="margin-top: 10px"
        :loading="uploading"
        @click="upload"
      >
        上传{{ fileList.length ? ` (${fileList.length})` : '' }}
      </van-button>
    </div>

    <div class="grid">
      <div v-for="m in items" :key="m.id" class="tile">
        <img
          v-if="m.kind === 'image'"
          :src="api.mediaUrl(m)"
          loading="lazy"
          @click="preview(m)"
        />
        <video v-else :src="api.mediaUrl(m, false)" muted playsinline />
        <div class="meta">
          <span class="muted">{{ (m.captured_on || '').slice(5) }}</span>
          <span class="danger" @click.stop="remove(m)">删</span>
        </div>
        <div class="muted who">{{ m.person_name || '—' }}</div>
      </div>
    </div>

    <van-image-preview v-model:show="showPreview" :images="previewImages" :start-position="previewIndex" />
    <van-empty v-if="!items.length" description="还没有图片" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
const items = ref([])
const personId = ref(null)
const fileList = ref([])
const uploading = ref(false)
const capturedOn = ref(new Date().toLocaleDateString('sv-SE'))
const showPreview = ref(false)
const previewIndex = ref(0)

const previewImages = computed(() => items.value.map((m) => api.mediaUrl(m, false)))

async function load() {
  items.value = await api.media({ person_id: personId.value || undefined })
}

function setPerson(id) {
  personId.value = id
  load()
}

async function upload() {
  if (!fileList.value.length) {
    showToast('先选图片')
    return
  }
  uploading.value = true
  let ok = 0
  try {
    for (const item of fileList.value) {
      const raw = item.file || item
      try {
        await api.uploadMedia(raw, {
          person_id: personId.value || store.currentPersonId || undefined,
          captured_on: capturedOn.value || undefined,
        })
        ok += 1
      } catch (e) {
        showToast(`${raw.name || '文件'} 上传失败：${e.message}`)
      }
    }
    if (ok) {
      showToast(`已上传 ${ok} 张`)
      fileList.value = []
      await load()
    }
  } finally {
    uploading.value = false
  }
}

function preview(m) {
  previewIndex.value = items.value.findIndex((x) => x.id === m.id)
  showPreview.value = true
}

async function remove(m) {
  try {
    await showConfirmDialog({ title: '删除图片', message: '同时删除磁盘文件，确定？' })
  } catch {
    return
  }
  await api.deleteMedia(m.id)
  showToast('已删除')
  await load()
}

onMounted(() => {
  // 相册保留自己的筛选（含「全部」），但默认跟随首页选的当前人物
  personId.value = store.currentPersonId
  load()
})
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.tile {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.tile img,
.tile video {
  width: 100%;
  height: 96px;
  object-fit: cover;
  display: block;
}
.meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  padding: 2px 6px 0;
}
.who {
  font-size: 11px;
  padding: 0 6px 4px;
}
</style>
