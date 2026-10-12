<template>
  <div>
    <div class="card">
      <h3>给谁记</h3>
      <select v-model="personId" class="picker">
        <option :value="null" disabled>请选一个人…</option>
        <option v-for="p in store.persons" :key="p.id" :value="p.id">
          {{ store.displayName(p) }}
        </option>
      </select>
      <p class="muted" style="margin: 8px 0 0">
        单品是挂在人下面的，所以记穿搭必须选一个人（换人不影响首页的全局选择）。
      </p>
    </div>

    <!-- 这个人没开「服装」模块：不给他记（与记录页的类型可用性同一套规则） -->
    <div class="card" v-if="personId && outfitState === false">
      <h3>「{{ store.displayName(selected) }}」没开服装模块</h3>
      <p class="muted">
        服装是模块开关：去个人页打开「服装」就能记（开关只影响入口，不会动已有数据）。
      </p>
      <router-link :to="'/person/' + personId" class="link">去个人页开启</router-link>
    </div>

    <OutfitForm
      v-else-if="personId"
      :key="personId"
      :person-id="personId"
      :preselect="preselect"
      @saved="onSaved"
    />

    <van-empty v-else description="先选一个人，再记这次穿搭" />

    <div class="card" v-if="lastSaved">
      <h3>刚记的</h3>
      <div class="row">
        <span>
          <van-tag plain>{{ fmtWhen(lastSaved) }}</van-tag>
          {{ lastSaved.title || '（没有关联单品）' }}
        </span>
        <span class="muted">{{ (lastSaved.items || []).length }} 件单品</span>
      </div>
      <router-link :to="{ path: '/wardrobe', query: scopeQuery(personId) }" class="link">
        去衣橱看这件衣服的穿次数
      </router-link>
    </div>
  </div>
</template>

<script setup>
// 衣橱的专有记录页：服装有了自己的流程（勾单品 → 1 条穿搭 → 累加穿次数），
// 不再混在通用「记录页」的类型列表里（那边只记事件，不管目录）。
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { normalizePersonId, scopeQuery } from '../lib/scope'
import { fmtWhen } from '../lib/event-day'
import OutfitForm from '../components/OutfitForm.vue'

const store = useArchiveStore()
const route = useRoute()

const personId = ref(null)
const preselect = ref([])
const lastSaved = ref(null)

const selected = computed(() => store.persons.find((p) => p.id === personId.value) || null)
// 三态：true 已开 / false 已知未开 / null 未知（加载中）—— 未知时不拦，避免闪一下「没开」
const outfitState = computed(() => (personId.value ? store.hasModule(personId.value, 'outfit') : null))

async function loadModules() {
  if (personId.value) await store.ensureModules([personId.value])
}

function onSaved(created) {
  lastSaved.value = created
}

onMounted(async () => {
  // 硬刷新直链时 persons / 模块可能还没加载完 —— 先补一次再定人
  await store.ensureLoaded()
  personId.value =
    normalizePersonId(route.query.person) || normalizePersonId(store.currentPersonId) || null
  preselect.value = [normalizePersonId(route.query.item)].filter(Boolean)
  await loadModules()
})

// 值得记的一处细节：本页**不写回全局 scope**（下游页约定），
// 换人只影响这一页记给谁。
</script>

<style scoped>
.picker {
  width: 100%;
  padding: 8px;
  border: 1px solid #ebedf0;
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
}
.link {
  color: #1989fa;
  font-size: 13px;
}
</style>
