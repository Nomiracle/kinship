<template>
  <div>
    <!-- 圈子筛选 + 添加入口 -->
    <div class="card">
      <div class="row" style="padding: 0">
        <span class="muted">按「谁的圈子」分组</span>
        <van-button size="small" type="primary" @click="showAdd = !showAdd">
          {{ showAdd ? '收起' : '＋ 添加人物' }}
        </van-button>
      </div>
      <div class="chips" style="margin-top: 8px">
        <van-tag
          :type="circle === null ? 'primary' : 'default'"
          size="large"
          @click="circle = null"
        >
          全部（{{ store.persons.length }}）
        </van-tag>
        <van-tag
          v-for="c in CIRCLES"
          :key="c.key"
          :type="circle === c.key ? 'primary' : 'default'"
          size="large"
          @click="circle = circle === c.key ? null : c.key"
        >
          {{ c.label }}（{{ countOf(c.key) }}）
        </van-tag>
      </div>
    </div>

    <!-- 添加一个人（默认收起，点「＋ 添加人物」展开） -->
    <div class="card" v-if="showAdd">
      <h3>添加一个人</h3>
      <van-field v-model="form.display_name" label="称呼" placeholder="如：妈妈 / 阿明" />
      <div class="row">
        <span class="muted">关系</span>
        <select v-model="form.relation_type" class="picker">
          <option v-for="r in relationTypes" :key="r.key" :value="r.key">{{ r.label }}</option>
        </select>
      </div>
      <div class="row">
        <span class="muted">性别</span>
        <select v-model="form.gender" class="picker">
          <option value="">未知（不自动开生理期）</option>
          <option v-for="g in store.genders" :key="g.key" :value="g.key">{{ g.label }}</option>
        </select>
      </div>
      <van-field v-model="form.birthday" type="date" label="生日" placeholder="可留空" />
      <van-cell title="农历生日">
        <template #right-icon><van-switch v-model="form.birthday_lunar" size="20" /></template>
      </van-cell>
      <template v-if="form.birthday_lunar">
        <van-field v-model.number="form.lunar_month" type="digit" label="农历月" />
        <van-field v-model.number="form.lunar_day" type="digit" label="农历日" />
      </template>
      <van-button block type="primary" style="margin-top: 10px" @click="addPerson">添加</van-button>
      <p class="muted">模块会按关系类型自动开好，之后可在个人页调整。</p>
    </div>

    <!-- 人物列表（删除只走个人页的「管理」，列表里不直接给删除） -->
    <div class="card" v-for="g in visibleGroups" :key="g.key">
      <h3>{{ g.label }}（{{ g.people.length }}）</h3>
      <div class="row" v-for="p in g.people" :key="p.id">
        <router-link :to="'/person/' + p.id" class="name">
          <strong>{{ store.displayName(p) }}</strong>
          <span class="muted" style="margin-left: 6px">{{ store.relationLabel(p.relation_type) }}</span>
          <span class="muted" style="margin-left: 6px">{{ store.genderLabel(p.gender) }}</span>
          <span class="muted" v-if="p.via_name" style="margin-left: 4px">· 通过 {{ p.via_name }}</span>
          <!-- ★ 生日一定要「明确写法 + 还有几天」一起给：只给天数会被误读成别的倒计时 -->
          <span class="muted" style="margin-left: 6px" v-if="p.birthday_text">
            {{ birthdayLine(p, { withAge: false }) }}
          </span>
        </router-link>
        <router-link :to="'/person/' + p.id" class="muted manage-link">管理 →</router-link>
      </div>
      <p v-if="!g.people.length" class="muted">（空）</p>
    </div>

    <div class="card" v-if="!store.persons.length">
      <van-empty description="还没有人，点上面的「＋ 添加人物」">
        <van-button size="small" type="primary" @click="showAdd = true">＋ 添加人物</van-button>
      </van-empty>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { showToast } from 'vant'
import { api } from '../api'
import { useArchiveStore } from '../store'
import { birthdayLine } from '../lib/birthday'

const CIRCLES = [
  { key: 'self', label: '我这边' },
  { key: 'shared', label: '共同' },
  { key: 'partner', label: '她那边' },
]

const store = useArchiveStore()
const circle = ref(null)
const showAdd = ref(false)

const relationTypes = computed(
  () => (store.config?.relation_types || []).filter((r) => r.key !== 'self')
)

function countOf(key) {
  return store.byCircle(key).length
}

const visibleGroups = computed(() => {
  if (circle.value) {
    const c = CIRCLES.find((x) => x.key === circle.value)
    return [{ key: circle.value, label: c ? c.label : circle.value, people: store.byCircle(circle.value) }]
  }
  return CIRCLES.map((c) => ({ ...c, people: store.byCircle(c.key) }))
})

const form = reactive({
  display_name: '',
  relation_type: 'family',
  gender: '',
  birthday: '',
  birthday_lunar: false,
  lunar_month: null,
  lunar_day: null,
})

async function addPerson() {
  if (!form.display_name.trim()) return
  const payload = {
    display_name: form.display_name.trim(),
    relation_type: form.relation_type,
    gender: form.gender || null,
    birthday: form.birthday || null,
    birthday_lunar: form.birthday_lunar,
  }
  if (form.birthday_lunar) {
    payload.lunar_month = form.lunar_month
    payload.lunar_day = form.lunar_day
  }
  try {
    await api.createPerson(payload)
    showToast('已添加')
    Object.assign(form, {
      display_name: '',
      gender: '',
      birthday: '',
      birthday_lunar: false,
      lunar_month: null,
      lunar_day: null,
    })
    await store.loadPersons()
    showAdd.value = false
  } catch (e) {
    showToast(e.message || '添加失败')
  }
}

onMounted(async () => {
  await store.ensureLoaded()
  if (store.persons.length && !store.config) await store.loadConfig()
})
</script>

<style scoped>
.name {
  text-decoration: none;
  color: inherit;
  min-width: 0;
}
.manage-link {
  text-decoration: none;
  flex: 0 0 auto;
}
.picker {
  padding: 6px;
  border: 1px solid #ebedf0;
  border-radius: 6px;
  font-size: 13px;
}
</style>
