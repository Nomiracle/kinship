import { createRouter, createWebHistory } from 'vue-router'

// 页面 chunk 的加载器集中在这里：路由用它懒加载，main.js 用它做空闲预取。
// ★ 为什么预取：手机经 Tailscale 访问时单程 RTT ~400ms，「点一下导航」等于
//   再等一次往返去取 4-16KB 的 chunk。登录后空闲时把这些 chunk 全拿下来，
//   之后点击就是本地切换（浏览器模块表已缓存，不会重复请求）。
const views = {
  dashboard: () => import('./views/Dashboard.vue'),
  new: () => import('./views/NewRecord.vue'),
  timeline: () => import('./views/Timeline.vue'),
  wardrobe: () => import('./views/Wardrobe.vue'),
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
  { path: '/', name: 'dashboard', component: views.dashboard, meta: { title: '今天', tab: 'today' } },
  { path: '/new', name: 'new', component: views.new, meta: { title: '记录', back: true, backTo: '/', hideTabbar: true } },
  { path: '/timeline', name: 'timeline', component: views.timeline, meta: { title: '时间轴', tab: 'timeline', group: 'timeline', scoped: true } },
  { path: '/wardrobe', name: 'wardrobe', component: views.wardrobe, meta: { title: '时间轴', tab: 'timeline', group: 'timeline', scoped: true } },
  { path: '/gallery', name: 'gallery', component: views.gallery, meta: { title: '时间轴', tab: 'timeline', group: 'timeline', scoped: true } },
  { path: '/people', name: 'people', component: views.people, meta: { title: '人物', tab: 'people', group: 'people' } },
  { path: '/relations', name: 'relations', component: views.relations, meta: { title: '人物', tab: 'people', group: 'people' } },
  { path: '/person/:id', name: 'person', component: views.person, meta: { title: '人物', tab: 'people', back: true, backTo: '/people', scoped: true } },
  { path: '/cycle', name: 'cycle', component: views.cycle, meta: { title: '生理期', back: true, backTo: '/people', scoped: true } },
  { path: '/todos', name: 'todos', component: views.todos, meta: { title: '待办', tab: 'todos', scoped: true } },
  { path: '/search', name: 'search', component: views.search, meta: { title: '搜索', back: true, backTo: '/' } },
  { path: '/settings', name: 'settings', component: views.settings, meta: { title: '设置', back: true, backTo: '/' } },
]

export function prefetchViews() {
  // 失败无所谓（断网时下次点击再拉），所以用 allSettled 吞掉错误
  return Promise.allSettled(Object.values(views).map((load) => load()))
}

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
