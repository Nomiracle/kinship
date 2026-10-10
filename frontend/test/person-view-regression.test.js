import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const src = (rel) => readFileSync(join(here, '..', rel), 'utf8')

const person = src('src/views/PersonView.vue')

// 这组断言直接锁住已知的运行时 bug：解构变量名 pred 遮蔽了 const pred = ref(null)，
// 于是 `pred.value = ...` 写到了普通对象/null 上 —— 周期预测永远不显示，甚至报错。
test('PersonView 不再用 pred 作解构变量遮蔽 ref', () => {
  assert.match(person, /const pred = ref\(/)
  assert.match(person, /predData/)
  assert.ok(
    !/\[\s*[^\]]*\bpred\b\s*,\s*fetched\s*\]\s*=\s*await/.test(person),
    '解构列表里不该再出现 pred 变量'
  )
})

// 冷启动深链 /person/:id 时 persons 还没到，必须并发补拉（不能退回串行 await）
test('PersonView 冷启动仍并发补拉 person（Promise.all）', () => {
  assert.match(person, /Promise\.all\(\[/)
  assert.match(person, /cached \? Promise\.resolve\(null\) : api\.person\(id\)/)
})

// 模块门控开关仍在个人页可改（原功能不丢）
test('PersonView 仍提供模块开关（功能未丢失）', () => {
  assert.match(person, /toggleModule/)
  assert.match(person, /putModules/)
})
