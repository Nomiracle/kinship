<template>
  <div class="wardrobe-form">
    <div v-if="showPersonSelect" class="card" style="margin-bottom: 10px">
      <h3>归属人 <span style="color:#ee0a24">*</span></h3>
      <select v-model="form.person_id" class="picker" aria-label="衣物归属人" :disabled="isLocked || isEdit">
        <option :value="null" disabled>请选择归属人…</option>
        <option v-for="p in persons" :key="p.id" :value="p.id">{{ displayName(p) }}</option>
      </select>
      <p class="muted" style="margin:6px 0 0">衣物归属一人，“全部”浏览时需显式选择，不自动选第一个人。</p>
    </div>

    <fieldset :disabled="isLocked" style="border:0;padding:0;margin:0">
      <div class="card">
        <van-field v-model="form.name" label="名称" placeholder="如：黑色阔腿裤" maxlength="128" :disabled="isLocked" />
        <van-field v-model="form.color" label="颜色" placeholder="如：黑色（可空）" :disabled="isLocked" />
        <van-field label="类别">
          <template #input>
            <select v-model="form.category" class="picker" :disabled="isLocked">
              <option v-for="c in categories" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
          </template>
        </van-field>
        <van-field v-model="form.tags" label="标签" placeholder="逗号分隔，如：露肩,格子（可空）" :disabled="isLocked" />
        <van-field v-model="form.notes" label="备注" type="textarea" rows="2" autosize placeholder="可空" :disabled="isLocked" />
        <p v-if="error" class="danger" style="margin:6px 0 0">{{ error }}</p>
        <p v-if="duplicate" class="warn" style="margin:6px 0 0">
          已有同名同色单品：<strong>{{ duplicate.name }}</strong>（{{ duplicate.category }}<span v-if="duplicate.color"> · {{ duplicate.color }}</span>）
          <span class="link" @click="$emit('openDuplicate', duplicate)">查看</span>
        </p>
        <div style="display:flex;gap:8px;margin-top:10px">
          <van-button block plain @click="$emit('cancel')" :disabled="isLocked">取消</van-button>
          <van-button block type="primary" :loading="saving" :disabled="isLocked" @click="submit">{{ isEdit ? '保存修改' : '创建' }}</van-button>
        </div>
        <p class="muted" style="margin:6px 0 0">衣物为长期档案，不含日期；穿着次数由穿搭记录聚合。</p>
        <p v-if="uncertain" class="danger" style="margin:6px 0 0">保存结果未确认，请勿重复提交，可稍后重试（已保留幂等键）。</p>
        <p v-if="partial" class="danger" style="margin:6px 0 0">部分照片未上传完成，请重试失败项；不会重复创建衣物。</p>
      </div>

      <div v-if="!isEdit" class="card" style="margin-top:10px">
        <h3>照片（可选）</h3>
        <p class="muted">可先创建后再上传；照片挂在单品上，不需要穿搭日期。</p>
        <van-uploader v-model="fileList" multiple :max-count="5" :preview-size="72" :disabled="isLocked" :after-read="onAfterRead" />
        <p v-if="uploadError" class="danger" style="margin:6px 0 0">{{ uploadError }}</p>
        <div v-if="failedFiles.length" class="muted" style="margin-top:6px">
          {{ failedFiles.length }} 张上传失败
          <span class="link" @click="$emit('retry', failedFiles)">重试失败项</span>
        </div>
      </div>
      <div v-else class="card" style="margin-top:10px">
        <h3>照片（可选）</h3>
        <p class="muted">编辑时可追加照片，上传挂到同一单品（不会新建）。</p>
        <van-uploader v-model="fileList" multiple :max-count="5" :preview-size="72" :disabled="isLocked" :after-read="onAfterRead" />
        <p v-if="uploadError" class="danger" style="margin:6px 0 0">{{ uploadError }}</p>
        <div v-if="failedFiles.length" class="muted" style="margin-top:6px">
          {{ failedFiles.length }} 张上传失败
          <span class="link" @click="$emit('retry', failedFiles)">重试失败项</span>
        </div>
      </div>
    </fieldset>
  </div>
</template>

<script setup>
import { reactive, ref, watch, computed } from 'vue'
import { ensureFileStableKeys } from '../lib/wardrobe-create.js'
import { useArchiveStore } from '../store.js'

const props = defineProps({
  initial: { type: Object, default: null },
  persons: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  effectivePersonId: { type: Number, default: null },
  saving: { type: Boolean, default: false },
  error: { type: String, default: '' },
  uploadError: { type: String, default: '' },
  duplicate: { type: Object, default: null },
  failedFiles: { type: Array, default: () => [] },
  isEdit: { type: Boolean, default: false },
  uncertain: { type: Boolean, default: false },
  partial: { type: Boolean, default: false },
})

const emit = defineEmits(['submit', 'cancel', 'openDuplicate', 'retry'])

const store = useArchiveStore()
function displayName(p) { return store.displayName(p) }

const form = reactive({
  person_id: null,
  name: '',
  color: '',
  category: 'other',
  tags: '',
  notes: '',
})

const fileList = ref([])

const showPersonSelect = computed(() => true)

const isLocked = computed(() => props.saving || props.uncertain || props.partial)

watch(
  () => props.initial,
  (v) => {
    if (v) {
      form.person_id = v.person_id ?? props.effectivePersonId ?? null
      form.name = v.name || ''
      form.color = v.color || ''
      form.category = v.category || 'other'
      form.tags = v.tags || ''
      form.notes = v.notes || ''
    } else {
      form.person_id = props.effectivePersonId ?? null
      form.name = ''
      form.color = ''
      form.category = 'other'
      form.tags = ''
      form.notes = ''
    }
    // 不在编辑初始化时清空 fileList（保留用户已选），仅新建时清空
    if (!v) {
      // 新建草稿：保留 fileList 交由父级 explicit new draft 控制
    }
  },
  { immediate: true }
)

watch(
  () => props.effectivePersonId,
  (id) => {
    if (!props.initial && id) form.person_id = id
  }
)

function onAfterRead() {
  // 为新增文件捕获一次稳定 UUID（与 index/name 无关）
  ensureFileStableKeys(fileList.value)
}

watch(fileList, (val) => {
  if (val && val.length) ensureFileStableKeys(val)
}, { deep: true })

function submit() {
  if (isLocked.value) return
  const payload = {
    person_id: props.initial?.person_id || form.person_id,
    category: form.category,
    name: form.name?.trim(),
    color: form.color?.trim() || null,
    tags: form.tags?.trim() || null,
    notes: form.notes?.trim() || null,
  }
  emit('submit', payload, fileList.value)
}

// expose fileList for parent to read/clear (never clear during upload — parent must guard)
defineExpose({ form, fileList })
</script>

<style scoped>
.picker {
  width: 100%;
  padding: 6px;
  border: 1px solid #ebedf0;
  border-radius: 6px;
  background: #fff;
  font-size: 14px;
}
.link {
  color: #1989fa;
  cursor: pointer;
  font-size: 12px;
}
</style>
