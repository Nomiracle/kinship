import { defineStore } from 'pinia'
import { api } from './api'

// ★ 冷启动 SWR 缓存：手机经 Tailscale 时每个请求是一次 ~400ms 的往返，
//   把上次的 config/persons 先摆上屏幕（0 往返），再在后台回源刷新。
//   只缓存这两份「全局且体积小」的数据；记录类数据不缓存（会看到过期内容）。
const CACHE_CONFIG = 'kinship_cache_config'
const CACHE_PERSONS = 'kinship_cache_persons'

function readCache(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeCache(key, val) {
  try {
    localStorage.setItem(key, JSON.stringify(val))
  } catch {
    // 隐私模式/配额满 → 静默降级成「没有缓存」，不该影响功能
  }
}

// 全局状态：配置（关系类型/模块/属性分类）、人物列表、当前选中的人
export const useArchiveStore = defineStore('archive', {
  state: () => ({
    config: null,
    persons: [],
    // null = 全部（时间轴/待办/相册看所有人）；localStorage 里存 'all' 表示全部
    currentPersonId: (() => {
      const raw = localStorage.getItem('kinship_person')
      return !raw || raw === 'all' ? null : Number(raw) || null
    })(),
    // 是否已由用户明确选过 —— 用来区分「没选过」（自动挑一个）和「主动选了全部」
    personChosen: localStorage.getItem('kinship_person') !== null,
    loading: false,
    error: '',
    // 隐私模式：列表/下拉里的敏感人物打码。默认关（安全默认），
    // 打开后写进 localStorage —— 否则每次刷新都被重置，等于没用
    privacyMode: localStorage.getItem('kinship_privacy') === '1',
  }),

  getters: {
    currentPerson(state) {
      return state.persons.find((p) => p.id === state.currentPersonId) || null
    },
    // 非「我」的对象才是记录主体
    others(state) {
      return state.persons.filter((p) => !p.is_self)
    },
    // 当前是不是「全部」——首页切换器与各页只读标签用
    isAll(state) {
      return !state.currentPersonId
    },
    scopeLabel(state) {
      if (!state.currentPersonId) return '全部'
      const p = state.persons.find((x) => x.id === state.currentPersonId)
      if (!p) return '全部'
      if (p.is_self) return '我'
      // 隐私模式下敏感人物打码，跟列表口径一致
      return state.privacyMode && p.sensitivity === 'sensitive' ? '●●●' : p.display_name
    },
    displayName(state) {
      // 列表/下拉统一走这里：隐私模式下敏感人物显示 ●●●。
      // 个人详情页不调用它 —— 你都已经点进去了，还打码是自找麻烦。
      return (p) => {
        if (!p) return ''
        if (p.is_self) return '我'
        return state.privacyMode && p.sensitivity === 'sensitive' ? '●●●' : p.display_name
      }
    },
    circleLabel() {
      const map = { self: '我这边', partner: '她那边', shared: '共同' }
      return (key) => map[key] || key
    },
    familiarityLabel() {
      const map = { 1: '只闻其名', 2: '见过', 3: '常见', 4: '很熟' }
      return (n) => map[n] || '—'
    },
    byCircle(state) {
      // 按圈子分组，关系页用
      return (key) => state.persons.filter((p) => p.circle === key)
    },
    relationLabel(state) {
      return (key) => {
        const rt = (state.config?.relation_types || []).find((r) => r.key === key)
        return rt ? rt.label : key
      }
    },
    moduleLabel(state) {
      return (key) => {
        const m = (state.config?.modules || []).find((x) => x.key === key)
        return m ? m.label : key
      }
    },
    attributeCategories(state) {
      return state.config?.attribute_categories || []
    },
    eventTypes(state) {
      return state.config?.event_types || []
    },
    wardrobeCategories(state) {
      return state.config?.wardrobe?.categories || []
    },
    wardrobeCategoryLabel(state) {
      return (key) => {
        const c = (state.config?.wardrobe?.categories || []).find((x) => x.key === key)
        return c ? c.label : key
      }
    },
  },

  actions: {
    async loadConfig() {
      this.config = await api.config()
      if (this.config?.app_title) document.title = this.config.app_title
      writeCache(CACHE_CONFIG, this.config)
    },
    async loadPersons() {
      this.persons = await api.persons()
      // 只有"从没选过"才自动挑一个；主动选了「全部」就不能被覆盖（否则刷新又跳回某个人）
      if (!this.personChosen && this.persons.length) {
        const favourite = this.persons.find((p) => !p.is_self) || this.persons[0]
        this.setCurrentPerson(favourite.id)
      }
      writeCache(CACHE_PERSONS, this.persons)
    },
    // 先把上次的 config/persons 摆上屏幕（同步、0 往返），后面 bootstrap 会回源刷新。
    // 没网/慢网时页面立刻有内容，而不是白屏等两个往返。
    hydrateFromCache() {
      if (!this.config) {
        const cfg = readCache(CACHE_CONFIG)
        if (cfg) {
          this.config = cfg
          if (cfg.app_title) document.title = cfg.app_title
        }
      }
      if (!this.persons.length) {
        const ps = readCache(CACHE_PERSONS)
        if (Array.isArray(ps)) this.persons = ps
      }
    },
    // 硬刷新直接落在某个子页时用：那时 App 的 bootstrap 可能还没跑完，
    // persons/eventTypes 是空的 —— 页面自己补一次，否则会显示成"没人可选"
    async ensureLoaded() {
      if (!this.persons.length || !this.config) this.hydrateFromCache()
      // 缓存命中就够本页用了（回源交给 App 的 bootstrap），省掉一次往返
      if (this.persons.length && this.config) return
      try {
        if (!this.config) await this.loadConfig()
        await this.loadPersons()
      } catch (e) {
        this.error = e.message || String(e)
      }
    },
    // id 传 null/'' 表示「全部」
    setCurrentPerson(id) {
      this.currentPersonId = id ? Number(id) : null
      this.personChosen = true
      localStorage.setItem('kinship_person', id ? String(id) : 'all')
    },
    setPrivacyMode(v) {
      this.privacyMode = !!v
      localStorage.setItem('kinship_privacy', v ? '1' : '0')
    },
    async bootstrap() {
      this.loading = true
      this.error = ''
      try {
        // 并发而不是串行：慢链路上少一个往返（两者互不依赖）
        await Promise.all([this.loadConfig(), this.loadPersons()])
      } catch (e) {
        this.error = e.message || String(e)
        throw e
      } finally {
        this.loading = false
      }
    },
  },
})
