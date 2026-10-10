<template>
  <div>
    <!-- 全站唯一的人物切换点：其余页面只跟随，不再放控件 -->
    <div class="card" v-if="persons.length">
      <h3>看谁的</h3>
      <div class="chips">
        <van-tag :type="store.isAll ? 'primary' : 'default'" size="large" @click="pick(null)">
          全部
        </van-tag>
        <van-tag
          v-for="p in persons"
          :key="p.id"
          :type="store.currentPersonId === p.id ? 'primary' : 'default'"
          size="large"
          @click="pick(p.id)"
        >
          {{ store.displayName(p) }}
        </van-tag>
      </div>
      <p class="muted" style="margin: 8px 0 0">
        <template v-if="store.isAll">当前「全部」：时间轴 / 待办 / 相册都显示所有人</template>
        <template v-else>当前只看「{{ store.scopeLabel }}」—— 时间轴 / 待办 / 相册跟着变</template>
      </p>
    </div>

    <div class="card" v-if="today">
      <h3>{{ fmtDate(today.date) }} · {{ today.weekday }}</h3>
      <div class="muted">农历 {{ today.lunar }}</div>
      <div v-if="today.is_special" class="chips" style="margin-top: 8px">
        <van-tag v-for="(n, i) in today.special_notes" :key="i" type="danger">{{ n }}</van-tag>
      </div>
      <div v-else class="muted" style="margin-top: 6px">今天没有特殊日子</div>
    </div>

    <div class="card" v-if="today && today.persons.length">
      <h3>大家在做什么</h3>
      <div class="row" v-for="p in today.persons" :key="p.id">
        <div>
          <router-link :to="'/person/' + p.id" style="text-decoration: none; color: inherit">
            <strong>{{ p.is_self ? '我' : p.display_name }}</strong>
          </router-link>
          <span class="muted" style="margin-left: 6px">{{ store.relationLabel(p.relation_type) }}</span>
          <div class="muted">
            <template v-if="p.last_seen">距上次见面 {{ p.days_since_last_seen }} 天</template>
            <template v-else>还没有见面记录</template>
            <template v-if="p.open_todos"> · {{ p.open_todos }} 条待办</template>
          </div>
        </div>
        <div style="text-align: right">
          <van-tag v-if="p.no_contact" type="warning">久未联系</van-tag>
          <van-tag v-if="p.cycle && p.cycle.in_window" type="danger">生理期窗口</van-tag>
          <van-tag v-else-if="p.cycle && p.cycle.next_in_days !== null" plain>
            约 {{ p.cycle.next_in_days }} 天后
          </van-tag>
        </div>
      </div>
    </div>

    <div class="card" v-if="today && today.anniversaries && today.anniversaries.length">
      <h3>纪念日</h3>
      <div class="row" v-for="a in today.anniversaries" :key="a.id">
        <span>
          {{ a.title }}
          <span class="muted" v-if="a.person_name && !a.title.includes(a.person_name)">
            （{{ a.person_name }}）
          </span>
        </span>
        <span class="muted" style="text-align: right">
          <template v-if="a.days_since !== null && a.days_since >= 0">
            已 <strong class="warn">{{ a.days_since }}</strong> 天
          </template>
          <template v-else-if="a.days_since !== null">
            还有 <strong class="warn">{{ -a.days_since }}</strong> 天
          </template>
          <template v-if="a.days_to_next !== null">
            · {{ a.days_to_next === 0 ? '就是今天' : '距下次 ' + a.days_to_next + ' 天' }}
          </template>
        </span>
      </div>
      <div class="muted" v-if="today.anniversaries[0].since_date" style="margin-top: 4px">
        起算日 {{ fmtDate(today.anniversaries[0].since_date) }}
      </div>
    </div>

    <div class="card" v-if="today && today.upcoming.length">
      <h3>未来 {{ upcomingDays }} 天</h3>
      <div class="row" v-for="(u, i) in today.upcoming" :key="i">
        <span>
          {{ u.title }}
          <span class="muted" v-if="u.person_name && u.kind === 'birthday'">（{{ u.person_name }}）</span>
        </span>
        <span :class="u.days_left <= 3 ? 'warn' : 'muted'">
          {{ u.days_left === 0 ? '就是今天' : u.days_left + ' 天后' }} · {{ fmtDate(u.date) }}
          <van-tag v-if="u.lunar" plain style="margin-left: 4px">农历</van-tag>
        </span>
      </div>
    </div>

    <div class="card" v-if="today && today.todos_open">
      <router-link to="/todos" style="text-decoration: none; color: inherit">
        <div class="row"><span>待办池</span><span class="warn">{{ today.todos_open }} 条未完成 →</span></div>
      </router-link>
    </div>

    <div class="card" v-if="!persons.length">
      <h3>还没有人</h3>
      <p class="muted">先去「设置 → 人物管理」添加一个人，或让我在聊天里代你建。</p>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useArchiveStore } from '../store'

const store = useArchiveStore()
const today = ref(null)
const persons = computed(() => store.persons)
const upcomingDays = computed(() => store.config?.reminder?.upcoming_days ?? 10)

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s + 'T00:00:00')
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

async function load() {
  const pid = store.currentPersonId
  today.value = await api.today(pid || undefined)
}

// 首页是唯一的切换点：切完立刻重载总览
function pick(id) {
  store.setCurrentPerson(id)
  load()
}

onMounted(load)
</script>
