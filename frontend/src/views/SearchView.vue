<template>
  <div>
    <div class="card">
      <van-field v-model="q" label="搜索" placeholder="搜关键词（≥3 字走全文索引）" @keyup.enter="doSearch" />
      <van-button block type="primary" style="margin-top: 10px" @click="doSearch">搜索</van-button>
      <p class="muted" v-if="mode">
        检索方式：{{ mode }}
        <span v-if="mode.includes('like')">（中文单/双字无法用 ngram 全文索引，自动回退）</span>
      </p>
    </div>

    <div class="card" v-for="h in results" :key="h.id">
      <div class="row">
        <span>
          <van-tag plain>{{ h.type_key }}</van-tag>
          <span class="muted" style="margin-left: 6px">{{ h.event_date }}</span>
          <span class="muted" v-if="h.person_name"> · {{ h.person_name }}</span>
        </span>
      </div>
      <div v-if="h.title"><strong>{{ h.title }}</strong></div>
      <div class="muted" v-if="h.snippet" style="white-space: pre-wrap">{{ h.snippet }}</div>
    </div>

    <van-empty v-if="searched && !results.length" description="没有匹配的记录" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { showToast } from 'vant'
import { api } from '../api'

const q = ref('')
const results = ref([])
const mode = ref('')
const searched = ref(false)

async function doSearch() {
  if (!q.value.trim()) return
  try {
    const res = await api.search(q.value.trim())
    results.value = res.items || []
    mode.value = res.mode || ''
    searched.value = true
  } catch (e) {
    showToast(e.message || '搜索失败')
  }
}
</script>
