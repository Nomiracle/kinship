<template>
  <div>
    <section class="quick-actions" aria-label="快捷新增">
      <router-link :to="scopedLink('/new')">✎ 记一件事</router-link>
      <router-link :to="scopedLink('/wardrobe/items/new')">＋ 添加衣物</router-link>
      <router-link :to="scopedLink('/wardrobe/new')">◷ 记穿搭</router-link>
      <router-link :to="scopedLink('/todos')">☑ 待办</router-link>
    </section>
    <section class="card" v-if="recent.length">
      <h3>近期记录</h3>
      <router-link v-for="r in recent" :key="r.id" class="recent-row" :to="scopedLink('/timeline')">
        <span><strong>{{ maskedTitle(r) }}</strong><small>{{ personName(r.person_id) }}</small></span>
        <time>{{ fmtWhen(r) }}</time>
      </router-link>
    </section>

    <!-- 1) 日期 -->
    <div class="card" v-if="today">
      <div class="day">
        <div class="day-num">{{ fmtDate(today.date) }}</div>
        <div class="day-sub">{{ today.weekday }} · 农历 {{ today.lunar }}</div>
      </div>
      <div v-if="today.is_special" class="chips" style="margin-top: 8px">
        <van-tag v-for="(n, i) in today.special_notes" :key="i" type="danger">{{ n }}</van-tag>
      </div>
    </div>

    <!-- 2) 要留意的事：纪念日 + 未来 N 天合并去重 -->
    <div class="card" v-if="reminders.length">
      <h3>要留意的事</h3>
      <div class="row" v-for="(r, i) in reminders" :key="i">
        <span>
          {{ r.title }}
          <span class="muted" v-if="r.person_name && !r.title.includes(r.person_name)">
            （{{ r.person_name }}）
          </span>
        </span>
        <span class="muted" style="text-align: right">
          <template v-if="r.kind === 'anniversary'">
            <template v-if="r.days_since !== null && r.days_since >= 0">
              已 <strong class="warn">{{ r.days_since }}</strong> 天
            </template>
            <template v-else-if="r.days_since !== null">
              还有 <strong class="warn">{{ -r.days_since }}</strong> 天
            </template>
            <template v-if="r.days_to_next !== null">
              · {{ r.days_to_next === 0 ? '就是今天' : '距下次 ' + r.days_to_next + ' 天' }}
            </template>
          </template>
          <template v-else>
            <span :class="r.days_left <= 3 ? 'warn' : ''">
              {{ r.days_left === 0 ? '就是今天' : r.days_left + ' 天后' }}
            </span>
            <span v-if="r.date"> · {{ fmtDate(r.date) }}</span>
            <van-tag v-if="r.lunar" plain style="margin-left: 4px">农历</van-tag>
          </template>
        </span>
      </div>
    </div>

    <!-- 2.5) 待办：逾期 / 今天到期可一键完成（不只是数字），近期待办给个提示 -->
    <div class="card" v-if="actionableTodos.length || todoBuckets.soon.length">
      <h3>待办</h3>
      <div class="row" v-for="t in actionableTodos" :key="t.id">
        <label class="todo-line">
          <input type="checkbox" :checked="false" :disabled="completingIds.has(t.id)" @change="completeTodo(t, $event)" />
          <span>
            {{ t.title }}
            <span class="muted" v-if="t.person_name"> · {{ t.person_name }}</span>
          </span>
        </label>
        <span class="muted" :class="{ warn: isOverdue(t) }">{{ dueText(t) }}</span>
      </div>
      <div class="row" v-if="todoBuckets.soon.length && !actionableTodos.length">
        <span class="muted">7 天内到期 {{ todoBuckets.soon.length }} 条</span>
      </div>
      <p class="muted" style="margin: 6px 0 0">
        <router-link :to="scopedLink('/todos')" class="link">去待办池 →</router-link>
      </p>
    </div>

    <!-- 3) 大家：需要留意的人排前面，其余折叠 -->
    <div class="card" v-if="today && today.persons.length">
      <h3>大家</h3>
      <div class="row" v-for="p in attention" :key="p.id">
        <div>
          <router-link :to="'/person/' + p.id" class="name">
            <strong>{{ store.displayName(p) }}</strong>
          </router-link>
          <span class="muted" style="margin-left: 6px">{{ store.relationLabel(p.relation_type) }}</span>
          <div class="muted">
            <template v-if="p.last_seen">距上次见面 {{ p.days_since_last_seen }} 天</template>
            <template v-else>还没有见面记录</template>
            <template v-if="p.open_todos"> · {{ p.open_todos }} 条待办</template>
          </div>
          <div class="muted" v-if="p.birthday_text">
            <span :class="birthdaySoon(p) ? 'warn' : ''">{{ birthdayLine(p) }}</span>
          </div>
        </div>
        <div style="text-align: right">
          <van-tag v-if="p.no_contact" type="warning">久未联系</van-tag>
          <!-- ★ 标签必须带语义：以前这里只有「约 24 天后」，跟生日的 28 天撞在一起，
               谁也看不出这是生理期预测（下次经期），不是生日 -->
          <van-tag v-if="p.cycle && p.cycle.in_window" type="danger">生理期窗口</van-tag>
          <van-tag v-else-if="p.cycle && p.cycle.next_in_days !== null" plain>
            生理期 · 约 {{ p.cycle.next_in_days }} 天后
          </van-tag>
        </div>
      </div>
      <p v-if="attention.length && !others.length" class="muted">以上是需要留意的。</p>
      <p v-if="!attention.length" class="muted">暂时没有需要特别留意的人。</p>

      <div v-if="others.length" style="margin-top: 4px">
        <div class="row" style="border-top: 1px solid #f2f3f5" @click="othersOpen = !othersOpen">
          <span class="muted">其他人（{{ others.length }}）</span>
          <span class="muted">{{ othersOpen ? '收起 ▲' : '展开 ▼' }}</span>
        </div>
        <template v-if="othersOpen">
          <div class="row" v-for="p in others" :key="p.id">
            <div>
              <router-link :to="'/person/' + p.id" class="name">
                <strong>{{ store.displayName(p) }}</strong>
              </router-link>
              <span class="muted" style="margin-left: 6px">{{ store.relationLabel(p.relation_type) }}</span>
              <div class="muted" v-if="p.birthday_text">{{ birthdayLine(p) }}</div>
            </div>
            <span class="muted">
              <template v-if="p.last_seen">距上次 {{ p.days_since_last_seen }} 天</template>
              <template v-else>无见面记录</template>
            </span>
          </div>
        </template>
      </div>
    </div>

    <div class="card" v-if="!personList.length">
      <h3>还没有人</h3>
      <p class="muted">
        去「人物」页添加一个人，或让我在聊天里代你建。
        <router-link to="/people" class="link">去人物页 →</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { showToast } from 'vant'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { buildReminders, splitPeopleByAttention, triageTodos } from '../lib/dashboard'
import { birthdayLine, birthdaySoon } from '../lib/birthday'
import { resolveScopedPerson } from '../lib/scope'
import { fmtWhen } from '../lib/event-day'

const store = useArchiveStore()
const route = useRoute()
const effectivePersonId = computed(() => resolveScopedPerson(route.query.person, store.currentPersonId))
const recent = ref([])
function scopedLink(path) { return { path, query: { person: effectivePersonId.value || 'all' } } }
function personName(id) { return store.displayName(store.persons.find(p => p.id === id)) }
function maskedTitle(r) { return store.privacyMode && r.sensitivity === 'sensitive' ? '●●●' : r.title || r.body?.slice(0,40) || '（无内容）' }
const today = ref(null)
const personList = computed(() => store.persons)

const othersOpen = ref(false)
const todos = ref([])
const completingIds = ref(new Set())
const todayStr = computed(() => today.value?.date || new Date().toLocaleDateString('sv-SE'))

const reminders = computed(() =>
  buildReminders(today.value?.anniversaries || [], today.value?.upcoming || [])
)
const attention = computed(() => splitPeopleByAttention(today.value?.persons || []).attention)
const others = computed(() => splitPeopleByAttention(today.value?.persons || []).others)
// 逾期 + 今天到期 = 需要马上动手的；近期待办只给个数量提示
const todoBuckets = computed(() => triageTodos(todos.value, todayStr.value))
const actionableTodos = computed(() => [...todoBuckets.value.overdue, ...todoBuckets.value.due])

function isOverdue(t) {
  return !!t.due_date && t.due_date < todayStr.value
}
function dueText(t) {
  if (!t.due_date) return ''
  if (t.due_date === todayStr.value) return '今天到期'
  const days = Math.round(
    (new Date(todayStr.value + 'T00:00:00') - new Date(t.due_date + 'T00:00:00')) / 86400000
  )
  return days > 0 ? `逾期 ${days} 天` : `${-days} 天后`
}

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s + 'T00:00:00')
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

let loadVersion = 0
async function load() {
  const version = ++loadVersion
  const pid = effectivePersonId.value
  // 并发：今天卡片 + 未完成待办互不依赖（慢链路上少一个往返）
  const [t, td, records] = await Promise.all([
    api.today(pid || undefined),
    api.todos(pid || undefined).catch(() => []),
    api.events({ person_id: pid || undefined, limit: 5 }),
  ])
  if (version !== loadVersion) return
  today.value = t
  todos.value = Array.isArray(td) ? td : []
  recent.value = records.items || []
}

// 完成失败时撤回勾选并提示，不能让 UI 假装已经保存。
async function completeTodo(t, event) {
  if (completingIds.value.has(t.id)) return
  completingIds.value.add(t.id)
  try {
    await api.patchTodo(t.id, { done: true })
    todos.value = todos.value.filter((item) => item.id !== t.id)
  } catch (e) {
    if (event?.target) event.target.checked = false
    showToast(e.message || '完成失败，请重试')
  } finally {
    completingIds.value.delete(t.id)
  }
}

watch(effectivePersonId, () => load().catch(() => showToast('加载失败，请重试')))
onMounted(async () => {
  await store.ensureLoaded()
  await load()
})
</script>

<style scoped>
.quick-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-bottom:18px; }
.quick-actions a { padding:18px 12px; background:var(--accent-soft); border-radius:var(--radius); text-decoration:none; color:var(--accent); font-weight:600; }
.recent-row { display:flex; align-items:center; justify-content:space-between; padding:12px 0; gap:12px; text-decoration:none; color:var(--ink); border-top:1px solid var(--line); }
.recent-row span { min-width:0; overflow-wrap:anywhere; }
.recent-row small { display:block; color:var(--muted); margin-top:4px; }
.recent-row time { flex-shrink:0; font-size:12px; color:var(--muted); }
@media(min-width:800px) { .quick-actions { grid-template-columns:repeat(4,minmax(0,1fr)); } }
.scope-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.todo-line {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.name {
  text-decoration: none;
  color: inherit;
}
.day {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.day-num {
  font-size: 20px;
  font-weight: 700;
}
.day-sub {
  font-size: 12px;
  color: #969799;
}
</style>
