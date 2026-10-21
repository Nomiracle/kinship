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

// 空闲时把各页面的 chunk 预取下来：手机经 Tailscale 时单程 RTT ~400ms，
// 预取之后「点导航」就不必再等一次往返去取 chunk（详见 router.js 的注释）。
// Safari 没有 requestIdleCallback → 退化成挂载 1.5s 后触发。
const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 1500))
idle(() => prefetchViews())
