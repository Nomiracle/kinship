// 导航结构的纯数据与映射（无副作用，可被 node:test 直接导入验证）。
//
// 设计：底部只保留 4 个主 tab；原来的「衣橱 / 相册 / 关系 / 设置 / 搜索」收敛为
// 分组内的二级分段或顶栏入口，但**复用既有路由与 URL**，不新增也没有删除任何 URL。

// 底部 4 个主 tab（顺序即展示顺序）。图标用 vant 内置图标名，渲染时配文字标签。
export const TABS = [
  { key: 'today', label: '今天', to: '/', icon: 'home-o' },
  { key: 'timeline', label: '时间轴', to: '/timeline', icon: 'clock-o' },
  { key: 'people', label: '人物', to: '/people', icon: 'friends-o' },
  { key: 'todos', label: '待办', to: '/todos', icon: 'todo-list-o' },
]

// 分组内二级分段：复用既有路由，不新增页面
export const GROUP_SEGMENTS = {
  timeline: [
    { key: 'records', label: '记录', to: '/timeline' },
    { key: 'gallery', label: '相册', to: '/gallery' },
    { key: 'wardrobe', label: '衣橱', to: '/wardrobe' },
  ],
  people: [
    { key: 'people', label: '人物', to: '/people' },
    { key: 'relations', label: '关系', to: '/relations' },
  ],
}

// 路由名 → 二级分段 key（未列出的路由返回 null → 不高亮任何分段）
const SEGMENT_BY_ROUTE = {
  timeline: 'records',
  gallery: 'gallery',
  wardrobe: 'wardrobe',
  people: 'people',
  relations: 'relations',
}

// 当前应高亮的主 tab。由路由 meta.tab 决定：子页（如 /person/:id）继承所属 tab，
// 保证父级导航高亮准确（/person/:id 与 /cycle 都仍属「人物」）。
export function activeTabKey(route) {
  return route?.meta?.tab || null
}

// 当前分组的分段列表（无分组返回 null → 不渲染分段条）
export function segmentsForRoute(route) {
  return GROUP_SEGMENTS[route?.meta?.group] || null
}

// 当前高亮的二级分段 key
export function activeSegmentKey(route) {
  return SEGMENT_BY_ROUTE[route?.name] || null
}
