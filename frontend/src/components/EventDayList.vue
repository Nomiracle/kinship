<template>
  <div>
    <!-- 顶部一键：几十条记录先看「哪天发生了什么」，要细节再展开 -->
    <!-- 只有一天时不必给「全部展开/收起」 -->
    <div class="day-tools" v-if="days.length > 1">
      <span class="muted">{{ days.length }} 天 · {{ items.length }} 条</span>
      <span class="link" @click="toggleAll">{{ allExpanded ? '全部收起' : '全部展开' }}</span>
    </div>

    <div :class="['day', bare ? 'bare' : 'card']" v-for="d in days" :key="d.date">
      <!-- 日头：日期 + 星期 + 当天条数 + 类型分布；点一下展开/收起 -->
      <div class="row day-head" @click="toggle(d.date)">
        <span class="head-main">
          <strong class="day-date">{{ d.date }}</strong>
          <span class="muted"> {{ d.weekday }}</span>
          <span class="day-count">{{ d.count }} 条</span>
          <span class="muted day-types">{{ typeSummary(d, labelOf) }}</span>
        </span>
        <span class="acts">
          <span class="muted">{{ isOpen(d.date) ? '收起 ▲' : '展开 ▼' }}</span>
        </span>
      </div>

      <!-- 折叠态：给一条标题预览 + 那天的小图，不用展开也知道发生了什么 -->
      <div v-if="!isOpen(d.date)" class="preview" @click="toggle(d.date)">
        <span class="preview-text">{{ dayHeadline(d) || '（无标题）' }}</span>
        <span class="thumbs" v-if="dayThumbs(d, 2).length">
          <img v-for="m in dayThumbs(d, 2)" :key="m.id" :src="api.mediaUrl(m)" loading="lazy" />
        </span>
      </div>

      <!-- 展开：当天的明细（顺序就是后端给的：时刻倒序，无时刻的落末尾） -->
      <template v-else>
        <!-- 紧凑模式（个人页「最近记录」）：一行一条 -->
        <template v-if="compact">
          <div class="row day-item" v-for="e in d.items" :key="e.id">
            <span class="one-line">
              <van-tag plain>{{ labelOf(e.type_key) }}</van-tag>
              <span class="item-title">{{ e.title || (e.body || '').slice(0, 16) }}</span>
              <span v-if="fmtTime(e)" class="muted item-time">{{ fmtTime(e) }}</span>
            </span>
            <span class="acts" v-if="editable">
              <span class="link" @click="$emit('edit', original(e))">编辑</span>
              <span class="danger" @click="$emit('delete', e)">删除</span>
            </span>
          </div>
        </template>

        <!-- 卡片模式（时间轴）：一条一张记录卡 -->
        <template v-else>
          <div class="item" v-for="e in d.items" :key="e.id">
            <div class="row" style="padding: 0">
              <span>
                <van-tag plain>{{ labelOf(e.type_key) }}</van-tag>
                <!-- 只记到日的记录不显示 00:00（那会看起来像凌晨记的） -->
                <span v-if="fmtTime(e)" class="muted item-time">{{ fmtTime(e) }}</span>
                <span class="muted" v-if="!hidePerson"> · {{ nameOf(e) }}</span>
              </span>
              <span class="acts" v-if="editable">
                <span class="link" @click="$emit('edit', original(e))">编辑</span>
                <span class="danger" @click="$emit('delete', e)">删除</span>
              </span>
            </div>
            <div v-if="e.title"><strong>{{ e.title }}</strong></div>
            <div v-if="e.items && e.items.length" class="chips" style="margin-top: 6px">
              <van-tag v-for="it in e.items" :key="it.item_id" size="medium" plain>
                {{ itemLabel(it) }}<span v-if="it.color" class="muted"> · {{ it.color }}</span>
              </van-tag>
            </div>
            <div v-if="e.body" class="item-body">{{ e.body }}</div>
            <div v-if="e.media && e.media.length" class="thumbs">
              <template v-for="m in e.media" :key="m.id">
                <img
                  v-if="m.kind !== 'video'"
                  :src="api.mediaUrl(m)"
                  loading="lazy"
                  @click="$emit('preview', { media: m, list: e.media })"
                />
                <!-- 视频没有页面内预览：给个带 ▶ 的方块，点开看原片 -->
                <div v-else class="vthumb" @click="$emit('preview', { media: m, list: e.media })">▶</div>
              </template>
            </div>
            <div v-if="e.tags" class="chips" style="margin-top: 6px">
              <van-tag v-for="(t, i) in e.tags.split(',')" :key="i" plain>{{ t.trim() }}</van-tag>
            </div>
            <p class="muted record-times">发生：{{ e.event_date }}{{ fmtTime(e) ? ' ' + fmtTime(e) : ' · 仅日期' }} · 录入：{{ createdAt(e.created_at) }}</p>
          </div>
        </template>
      </template>
    </div>

    <van-empty v-if="!days.length" description="还没有记录" />
  </div>
</template>

<script setup>
// 时间轴 / 个人页共用的「按日合并」列表。
//
// 卡片的粒度是「天」：日头显示日期/星期/条数与类型分布，默认折叠（一眼看完一段时间），
// 点日头展开当天明细；顶部有「全部展开 / 全部收起」。
// 折叠状态下给一条标题预览 + 最多 2 张缩略图，避免「折叠之后什么都看不到」。
import { computed, ref } from 'vue'
import { api } from '../api'
import { useArchiveStore } from '../store'
import {
  dayHeadline,
  dayThumbs,
  fmtTime,
  groupByDay,
  typeSummary,
} from '../lib/event-day'

const props = defineProps({
  // 后端 GET /api/events?group=day 的 items（扁平、已按日期倒序）
  items: { type: Array, default: () => [] },
  // compact = 个人页那种一行一条；默认是时间轴的记录卡
  compact: { type: Boolean, default: false },
  // 不显示人名（只看某个人时）
  hidePerson: { type: Boolean, default: false },
  // 折叠态要不要显示编辑/删除（个人页只读）
  editable: { type: Boolean, default: true },
  // 不要卡片底色（嵌在别的卡片里时用，避免卡中卡）
  bare: { type: Boolean, default: false },
  // type_key → 中文标签
  labelOf: { type: Function, default: (k) => k },
  // 单品 chip 的文案（敏感单品打码在调用方决定）
  itemLabel: { type: Function, default: (it) => it.name },
})

defineEmits(['edit', 'delete', 'preview'])

const store = useArchiveStore()
function original(e) { return props.items.find(row => row.id === e.id) || e }
function nameOf(e) { const p = store.persons.find(p => p.id === e.person_id); return p ? store.displayName(p) : e.person_name || '—' }
function createdAt(value) { return value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString() : '未记录' }
const days = computed(() => groupByDay(props.items.map(e => store.privacyMode && e.sensitivity === 'sensitive' ? { ...e, title:'●●●', body:null, tags:null, media:[], items:[] } : e)))
// 展开哪几天：默认全折叠（boss 的默认口径），点日头单独展开
const open = ref([])
const isOpen = (date) => open.value.includes(date)
function toggle(date) {
  open.value = isOpen(date) ? open.value.filter((d) => d !== date) : [...open.value, date]
}
const allExpanded = computed(
  () => days.value.length > 0 && days.value.every((d) => isOpen(d.date))
)
function toggleAll() {
  open.value = allExpanded.value ? [] : days.value.map((d) => d.date)
}
</script>

<style scoped>
.day-tools {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 2px 8px;
}
.day {
  padding: 10px 12px;
}
.day.bare {
  padding: 0;
}
.day-head {
  cursor: pointer;
  padding: 0;
  align-items: flex-start;
}
.head-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.day-date {
  font-size: 14px;
}
.day-count {
  font-size: 12px;
  color: #1989fa;
  background: #ecf5ff;
  border-radius: 8px;
  padding: 1px 6px;
}
.day-types {
  font-size: 12px;
}
.preview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  cursor: pointer;
}
.preview-text {
  font-size: 13px;
  color: #646566;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item {
  border-top: 1px solid #f2f3f5;
  margin-top: 10px;
  padding-top: 8px;
}
.item:first-of-type {
  border-top: none;
}
.item-time {
  margin-left: 6px;
}
.item-body {
  font-size: 13px;
  margin-top: 4px;
  white-space: pre-wrap;
}
.one-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.day-item {
  border-top: 1px solid #f2f3f5;
}
.day-item:first-of-type {
  border-top: none;
}
.acts {
  display: flex;
  gap: 12px;
  flex: 0 0 auto;
}
.link {
  color: #1989fa;
  cursor: pointer;
}
.thumbs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.thumbs img {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 6px;
}
.item .thumbs img {
  width: 72px;
  height: 72px;
}
.vthumb {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  background: #ebedf0;
  color: #646566;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
