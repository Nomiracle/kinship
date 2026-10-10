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
  person: () => import('./views/PersonView.vue'),
  cycle: () => import('./views/CycleView.vue'),
  todos: () => import('./views/Todos.vue'),
  search: () => import('./views/SearchView.vue'),
  settings: () => import('./views/SettingsView.vue'),
}

const routes = [
  { path: '/', name: 'dashboard', component: views.dashboard },
  { path: '/new', name: 'new', component: views.new },
  { path: '/timeline', name: 'timeline', component: views.timeline },
  { path: '/wardrobe', name: 'wardrobe', component: views.wardrobe },
  { path: '/relations', name: 'relations', component: views.relations },
  { path: '/gallery', name: 'gallery', component: views.gallery },
  { path: '/person/:id', name: 'person', component: views.person },
  { path: '/cycle', name: 'cycle', component: views.cycle },
  { path: '/todos', name: 'todos', component: views.todos },
  { path: '/search', name: 'search', component: views.search },
  { path: '/settings', name: 'settings', component: views.settings },
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
