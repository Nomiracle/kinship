<template>
  <div>
    <div class="card">
      <h3>谁</h3>
      <p class="muted" style="margin: 0">
        生理期是按人记的 —— 当前：<strong>{{ personName() || '—' }}</strong>；换人在首页。
      </p>
      <p v-if="!personId" class="muted" style="margin: 6px 0 0">
        还没有可以记生理期的人（去个人页启用「生理期」模块）。
      </p>
    </div>

    <div class="card" v-if="pred">
      <h3>周期概览</h3>
      <div class="row"><span>记录次数</span><span>{{ pred.count }}</span></div>
      <div class="row"><span>最近一次开始</span><span>{{ pred.last_start || '—' }}</span></div>
      <div class="row"><span>距今天数</span><span>{{ pred.days_since_last ?? '—' }}</span></div>
      <div class="row"><span>平均周期（近 6 次）</span><span>{{ pred.avg_cycle_days ?? '—' }} 天</span></div>
      <div class="row">
        <span>预测下次</span>
        <span>{{ pred.predicted_next || '—' }}</span>
      </div>
      <div class="row" v-if="pred.window">
        <span>预测窗口</span>
        <span class="muted">{{ pred.window[0] }} ~ {{ pred.window[1] }}</span>
      </div>
      <van-tag v-if="pred.in_window" type="danger">今天在预测窗口内</van-tag>
      <p class="muted" style="margin-top: 8px">
        {{ pred.note }}
      </p>
    </div>

    <div class="card">
      <h3>新增一次</h3>
      <van-field v-model="form.start_date" type="date" label="开始日期" />
      <van-field v-model="form.end_date" type="date" label="结束日期" placeholder="可留空" />
      <van-field v-model="form.symptoms" label="症状" placeholder="如：肚子疼、腰酸" />
      <van-button block type="primary" style="margin-top: 10px" @click="add">保存</van-button>
      <p class="muted">只记录周期的开始日期即可，统计只需这个。</p>
    </div>

    <div class="card">
      <h3>历史记录</h3>
      <div class="row" v-for="r in pred?.records || []" :key="r.id">
        <span>
          {{ r.start_date }}
          <span class="muted" v-if="r.end_date">→ {{ r.end_date }}</span>
          <span class="muted" v-if="r.symptoms"> · {{ r.symptoms }}</span>
        </span>
        <span class="danger" @click="remove(r.id)">删除</span>
      </div>
      <van-empty v-if="!(pred?.records || []).length" description="还没有记录" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
const route = useRoute()
const personId = ref(null)
const pred = ref(null)
const form = reactive({ start_date: '', end_date: '', symptoms: '' })

async function load() {
  if (!personId.value) return
  pred.value = await api.cyclePrediction(personId.value)
}

// 只读显示当前是谁（切换已收归首页）
function personName() {
  const p = store.persons.find((x) => x.id === Number(personId.value))
  return p ? (p.is_self ? '我' : store.displayName(p)) : ''
}

async function add() {
  if (!form.start_date) {
    showToast('请选开始日期')
    return
  }
  try {
    await api.createCycle({
      person_id: Number(personId.value),
      start_date: form.start_date,
      end_date: form.end_date || null,
      symptoms: form.symptoms || null,
    })
    showToast('已记录')
    form.start_date = ''
    form.end_date = ''
    form.symptoms = ''
    await load()
  } catch (e) {
    showToast(e.message || '保存失败')
  }
}

async function remove(id) {
  await api.deleteCycle(id)
  await load()
}

onMounted(async () => {
  await store.ensureLoaded() // 硬刷新直接进本页时，别把"没人可选"当成真没人
  // 本页只从个人页进得来，所以优先用「你从谁那儿点进来的」，
  // 其次才是首页选的当前人物（否则从妈妈那儿点进来会看到别人的数据）
  const fromQuery = Number(route.query.person) || null
  const withCycle = store.others[0]
  personId.value =
    fromQuery ||
    (store.currentPersonId && !store.currentPerson?.is_self ? store.currentPersonId : withCycle?.id)
  await load()
})
</script>

<style scoped>
.picker {
  width: 100%;
  padding: 8px;
  border: 1px solid #ebedf0;
  border-radius: 8px;
  font-size: 14px;
}
</style>
