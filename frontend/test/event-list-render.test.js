import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createPinia } from 'pinia'
import { fileURLToPath } from 'node:url'

test('真实日卡渲染：敏感标题/图片遮罩且不改原记录，默认折叠', async () => {
  const previous = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null }
  const server = await createServer({ root:fileURLToPath(new URL('..',import.meta.url)), server:{middlewareMode:true}, appType:'custom', optimizeDeps:{noDiscovery:true,include:[]} })
  try {
    const { default: DayList } = await server.ssrLoadModule('/src/components/EventDayList.vue')
    const { useArchiveStore } = await server.ssrLoadModule('/src/store.js')
    const pinia = createPinia()
    const store = useArchiveStore(pinia)
    store.privacyMode = true
    store.persons = [{ id:1,display_name:'Synthetic secret person',sensitivity:'sensitive' }]
    const row = { id:7,person_id:1,person_name:'Synthetic secret person',type_key:'text',event_date:'2026-10-21',title:'Synthetic private title',body:'Synthetic private body',sensitivity:'sensitive',media:[{id:3,path:'synthetic-private.png',kind:'image'}] }
    const app = createSSRApp(DayList,{ items:[row] })
    app.use(pinia)
    app.config.warnHandler = () => {} // Vant components are irrelevant to folded text privacy.
    const html = await renderToString(app)
    assert.ok(html.includes('●●●'))
    assert.ok(!html.includes('Synthetic private title'))
    assert.ok(!html.includes('Synthetic private body'))
    assert.ok(!html.includes('synthetic-private.png'))
    assert.equal(row.title,'Synthetic private title')
    assert.equal(row.media.length,1)
    store.privacyMode = false
    const publicApp = createSSRApp(DayList,{items:[row]})
    publicApp.use(pinia)
    publicApp.config.warnHandler = () => {}
    const visible = await renderToString(publicApp)
    assert.ok(visible.includes('Synthetic private title'))
    assert.ok(visible.includes('synthetic-private.png'))
  } finally { await server.close(); globalThis.localStorage=previous }
})
