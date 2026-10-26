import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'

// 页面 chunk 的加载器集中在这里：路由用它懒加载，main.js 用它做延迟预取。
// ★ 为什么预取：每开一个新页面都要为 4–16KB 的 chunk 付一次往返（手机链路上 400ms 级）。
//   预取之后「点导航」就是本地切换（浏览器模块表已缓存，不会重复请求）。
// ★ 首页（/）例外：它永远是最先要画的页面。懒加载意味着「入口 JS 跑完 → 再要一次 Dashboard
//   chunk」，在慢链路上就是白等一整趟往返（实测首屏 API 被推后 ~470ms）。所以 Dashboard
//   静态引入、并进入口包（约 +4KB gzip），用体积换首屏的一个往返。
const views = {
  dashboard: () => Promise.resolve(Dashboard),
  new: () => import('./views/NewRecord.vue'),
  timeline: () => import('./views/Timeline.vue'),
  wardrobe: () => import('./views/Wardrobe.vue'),
  wardrobeNew: () => import('./views/WardrobeNew.vue'),
  wardrobeItemEditor: () => import('./views/WardrobeItemEditor.vue'),
  relations: () => import('./views/Relations.vue'),
  gallery: () => import('./views/Gallery.vue'),
  people: () => import('./views/PeopleView.vue'),
  person: () => import('./views/PersonView.vue'),
  cycle: () => import('./views/CycleView.vue'),
  todos: () => import('./views/Todos.vue'),
  search: () => import('./views/SearchView.vue'),
  settings: () => import('./views/SettingsView.vue'),
}

// meta 说明：
//   title     顶栏标题
//   tab       所属底部主 tab（子页继承父 tab，父导航高亮才准确）
//   group     所属二级分组（渲染分组分段条）；无则不分段
//   back      是否显示「返回」按钮（子页 / 编辑页）
//   backTo    无历史可退时的兜底落地页（深链冷启动）
//   hideTabbar 是否隐藏底部 tabbar（录入/编辑路由）
//   scoped    该页只读显示「某个人/全部」的范围（顶栏范围指示器据此显示，不改全局）
const routes = [
  { path: '/', name: 'dashboard', component: views.dashboard, meta: { title: '概览', tab: 'today', scoped: true } },
  { path: '/new', name: 'new', component: views.new, meta: { title: '记录', back: true, backTo: '/', hideTabbar: true } },
  { path: '/timeline', name: 'timeline', component: views.timeline, meta: { title: '记录', tab: 'timeline', group: 'timeline', scoped: true } },
  { path: '/wardrobe', name: 'wardrobe', component: views.wardrobe, meta: { title: '衣橱', tab: 'wardrobe', scoped: true } },
  { path: '/wardrobe/items/new', name: 'wardrobe-item-new', component: views.wardrobeItemEditor, meta: { title: '添加衣物', tab: 'wardrobe', back: true, backTo: '/wardrobe', hideTabbar: true } },
  { path: '/wardrobe/items/:id/edit', name: 'wardrobe-item-edit', component: views.wardrobeItemEditor, meta: { title: '编辑衣物', tab: 'wardrobe', back: true, backTo: '/wardrobe', hideTabbar: true } },
  // 服装的专有记录页：不在通用「记录页」里记（那里只记事件，不管单品目录）。
  // 不加 group → 不渲染二级分段条（录入页只要返回按钮）。
  { path: '/wardrobe/new', name: 'wardrobe-new', component: views.wardrobeNew, meta: { title: '记穿搭', tab: 'wardrobe', back: true, backTo: '/wardrobe', hideTabbar: true, scoped: true } },
  { path: '/gallery', name: 'gallery', component: views.gallery, meta: { title: '相册', tab: 'timeline', group: 'timeline', scoped: true } },
  { path: '/people', name: 'people', component: views.people, meta: { title: '人物', tab: 'people', group: 'people' } },
  { path: '/relations', name: 'relations', component: views.relations, meta: { title: '人物', tab: 'people', group: 'people' } },
  { path: '/person/:id', name: 'person', component: views.person, meta: { title: '人物', tab: 'people', back: true, backTo: '/people', scoped: true } },
  { path: '/cycle', name: 'cycle', component: views.cycle, meta: { title: '生理期', back: true, backTo: '/people', scoped: true } },
  { path: '/todos', name: 'todos', component: views.todos, meta: { title: '待办', tab: 'today', back: true, backTo: '/', scoped: true } },
  { path: '/search', name: 'search', component: views.search, meta: { title: '搜索', back: true, backTo: '/' } },
  { path: '/settings', name: 'settings', component: views.settings, meta: { title: '设置', back: true, backTo: '/' } },
]

// ★ 预取必须限并发：13 个 chunk 同时发会把首屏和 /api 请求挤在同一条连接后面
//   （实测反而更慢）。固定 2 路并发，按上面的声明顺序一条一条拿。
export function prefetchViews(concurrency = 2) {
  const queue = Object.values(views)
  const worker = async () => {
    while (queue.length) {
      const load = queue.shift()
      // 失败无所谓（断网/慢网时下次点击再拉），不能让它冒泡成未处理拒绝
      try {
        await load()
      } catch {
        /* noop */
      }
    }
  }
  const n = Math.max(1, Math.min(concurrency, queue.length))
  return Promise.allSettled(Array.from({ length: n }, () => worker()))
}

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
