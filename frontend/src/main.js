import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Vant from 'vant'
import App from './App.vue'
import router, { prefetchViews } from './router'

// ★ 按需引入样式：全量 `vant/lib/index.css` 是 198KB（gzip 53KB），而本项目只用到
//   下面 9 个组件 + showToast/showConfirmDialog。逐个引 style 入口即可 —— 这些入口
//   会自己带上依赖组件的样式（cell/icon/overlay/loading…），构建后 CSS 约 85KB（gzip ~22KB）。
//   ⚠️ 以后在模板里新增 van-* 组件（或 showDialog/showNotify/showImagePreview 这类方法）
//   时，必须在这里补一行 import，否则组件「能用但没样式」。
// 顶栏的搜索/返回/设置图标与若干组件用到 icon 样式；按需入口会带依赖样式，
// 这里仍显式引一次（幂等），避免将来新增图标类组件时「能用但没样式」。
import 'vant/es/icon/style'
import 'vant/es/button/style'
import 'vant/es/cell/style'
import 'vant/es/dialog/style'
import 'vant/es/empty/style'
import 'vant/es/field/style'
import 'vant/es/image-preview/style'
import 'vant/es/popup/style'
import 'vant/es/switch/style'
import 'vant/es/tag/style'
import 'vant/es/toast/style'
import 'vant/es/uploader/style'
import './styles/tokens.css'

createApp(App).use(createPinia()).use(router).use(Vant).mount('#app')

// 页面 chunk 的预取（只影响「点导航快不快」，不影响首屏）。
// ★ 不能挂载后就立刻抓：13 个 chunk 会和首屏的 CSS/JS 与 /api 请求抢同一条连接，
//   在手机链路（每往返 400ms 级）上反而把首屏拖慢 —— 实测冷启动有 20+ 个 chunk 请求
//   挤在 2.3s 之后。改成「load 事件之后再等 3s」：首屏该拿的都拿完了才轮到预取。
// 之后点击导航仍然命中浏览器模块表（不会重复请求）。
function schedulePrefetch() {
  const run = () => setTimeout(() => prefetchViews(), 3000)
  if (document.readyState === 'complete') run()
  else window.addEventListener('load', run, { once: true })
}
schedulePrefetch()
