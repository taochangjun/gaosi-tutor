# gaosi-tutor 前端代码详解 — Vue 新手学习指南

> 面向 Vue 新手，结合 **gaosi-tutor**（小思陪练）真实代码讲解。  
> 架构思路继承自 [MES Demo](../mes) 前端，业务已换为：孩子聊天、家长设置、SSE 流式、语音、配图出题、家庭笔记 RAG。  
> 后端 Agent 见 [agent-learning-path.md](./agent-learning-path.md)；RAG 见 [agent-rag.md](./agent-rag.md)。

---

## 目录

0. [给新人：从第一性原理理解 Vue](#0-给新人从第一性原理理解-vue)
1. [项目整体结构](#1-项目整体结构)
2. [技术栈一览](#2-技术栈一览)
3. [应用是如何启动的](#3-应用是如何启动的)
4. [Vue 3 核心概念（本项目用到的）](#4-vue-3-核心概念本项目用到的)
5. [单文件组件 .vue 的结构](#5-单文件组件-vue-的结构)
6. [全局入口与布局 App.vue](#6-全局入口与布局-appvue)
7. [路由系统 router.js](#7-路由系统-routerjs)
8. [API 层 api.js（含 SSE）](#8-api-层-apijs含-sse)
9. [全局样式 style.css](#9-全局样式-stylecss)
10. [页面与组件逐一讲解](#10-页面与组件逐一讲解)
11. [Element Plus 组件速查](#11-element-plus-组件速查)
12. [如何自己添加新功能](#12-如何自己添加新功能)
13. [常见问题 FAQ](#13-常见问题-faq)

---

## 0. 给新人：从第一性原理理解 Vue

### 0.1 你的感受是对的

很多教程的套路是：「template 写 `v-for`，script 写 `ref`，调 `api.js`，好了。」

你能抄出来，但心里会空——`createApp` 是什么？数据变了界面为什么自己变？这行删了会怎样？

**学习方式：** 每看到一个 Vue API，问一句：**「如果没有 Vue，原生 JS 要怎么实现？」**

### 0.2 四层模型

```
第 4 层  Vue / Element Plus / Router     ← 少写重复代码，自动同步数据与界面
第 3 层  HTTP / JSON / SSE               ← fetch 向后端要数据或流
第 2 层  JavaScript                      ← 变量、async/await、事件
第 1 层  HTML / CSS / DOM                ← 网页显示与手动改页面
```

### 0.3 核心对照表

| 本项目里看到的 | Vue 帮你省掉的事 | 没有 Vue 时等价于… |
|---------------|-----------------|-------------------|
| `mount('#app')` | 指定渲染根节点 | 选一块 DOM，`appendChild` |
| `ref([])` + `{{ msg }}` | 数据变 → 界面变 | 每次改数据后手动改 `textContent` |
| `v-for="msg in messages"` | 列表渲染 | `forEach` + `createElement` |
| `@click="send(q)"` | 事件绑定 | `addEventListener('click', send)` |
| `v-model="input"` | 输入框双向绑定 | 监听 `input` + 回写 `value` |
| `computed(() => ...)` | 派生数据自动重算 | 依赖变了手动重算再改 DOM |
| `onMounted(loadLessons)` | 组件出现时拉数据 | `window.onload` 或插入后回调 |
| `tutorChatStream(...)` | 与 Vue 无关 | 原生 `fetch` + `ReadableStream` 也行 |

### 0.4 用原生 JS 模拟 ChildChat 发消息

**Vue 写法（本项目）：**

```javascript
messages.value.push({ role: 'user', content: text })
const done = await tutorChatStream({ question: text, ... }, onEvent)
messages.value.push({ role: 'assistant', content: done.answer })
```

**等价思路（原生 JS）：**

```javascript
messages.push({ role: 'user', content: text })
renderChat(messages)                    // 手动重绘聊天气泡

const res = await fetch('/api/chat/stream', { method: 'POST', body: ... })
const reader = res.body.getReader()       // 读 SSE 流
// ... 解析 event/data，边收边改 assistant 气泡文字
renderChat(messages)
```

Vue 帮你省掉的是：**每次 `messages` 变了自动 `renderChat`**。

### 0.5 读代码「三问法」

1. **数据在哪？** → `ref` / `reactive`（如 `messages`、`form`）
2. **谁改数据？** → 用户点击、`onEvent` 回调、`onMounted` 请求
3. **界面怎么绑数据？** → `template` 里 `{{ }}`、`v-for`、`v-model`

### 0.6 推荐学习顺序（gaosi-tutor）

| 天 | 内容 |
|----|------|
| Day 1 | 读本章 + `App.vue` + `router.js` |
| Day 2 | 读 `ChildChat.vue`：消息列表 + `send()` |
| Day 3 | 读 `api.js` 的 `tutorChatStream`（SSE 解析） |
| Day 4 | 读 `ParentPanel.vue`：表单 + 家庭笔记 + RAG |
| Day 5 | 读 `useSpeechInput.js` / `MathDiagram.vue` |
| Day 6 | 按第 12 章加一个自己的小页面 |

### 0.7 七个概念收拢全部前端

| # | 概念 | 本项目例子 |
|---|------|-----------|
| 1 | **状态** | `messages`、`settings`、`form` |
| 2 | **渲染** | `v-for` 气泡、`MathDiagram` |
| 3 | **事件** | 快捷按钮 `@click="send(q)"`、麦克风 |
| 4 | **副作用** | `onMounted(loadLessons)`、`tutorChatStream` |
| 5 | **路由** | `/` 孩子、`/parent` 家长 |
| 6 | **持久化** | `localStorage` session_id、settings |
| 7 | **组合** | `composables/useSpeechInput.js` |

**跟一条线：** 孩子点「出一道题」→ Network 看 `/api/chat/stream` → 看 SSE `tool_start` / `delta` / `done` → 看 `messages` 和 `streamDiagram` 变化。

---

## 1. 项目整体结构

```
frontend/
├── index.html              # 挂载点 <div id="app">
├── package.json
├── vite.config.js          # 开发服务器 + /api 代理
└── src/
    ├── main.js             # createApp + Element Plus + Router
    ├── App.vue             # 顶栏导航 + <router-view />
    ├── router.js           # / 与 /parent 两页
    ├── api.js              # REST + SSE 流式聊天
    ├── style.css           # 全局 CSS 变量（暖色陪学主题）
    ├── views/
    │   ├── ChildChat.vue   # 孩子模式：聊天 + 语音 + 配图
    │   └── ParentPanel.vue # 家长模式：设置 + 笔记 + RAG + 提问
    ├── components/
    │   ├── MathDiagram.vue
    │   └── ObserveMatchDiagram.vue
    └── composables/
        ├── useSpeechInput.js   # 麦克风 → 文字
        └── useSpeechOutput.js  # TTS 朗读
```

**数据流向（一次聊天）：**

```
用户点「发送」或说完话
    ↓
ChildChat.send()  push user 消息
    ↓
api.tutorChatStream()  POST /api/chat/stream
    ↓
Vite proxy → localhost:8000  FastAPI
    ↓
SSE 事件：tool_start → delta → tool_end → done
    ↓
onEvent 更新 streamBuffer / streamDiagram
    ↓
done 后 push assistant 消息，可选 TTS speak()
```

---

## 2. 技术栈一览

| 技术 | 作用 | 在本项目中的体现 |
|------|------|-----------------|
| **Vue 3** | UI 与交互 | 所有 `.vue`、`composables` |
| **Vite** | 开发服务器 + 打包 | `npm run dev`，端口 5173 |
| **Vue Router** | 双模式路由 | `/`、`/parent` |
| **Element Plus** | 家长页表单组件 | `el-form`、`el-select`、`el-button` |
| **原生 fetch** | HTTP + SSE | `api.js`（未用 axios） |
| **Web Speech API** | 语音输入/播报 | `composables/` |

与 MES 前端的差异：无侧边栏仪表盘、无 axios 全局实例、**核心难点在 SSE 流式与语音**。

---

## 3. 应用是如何启动的

### 3.1 index.html

```html
<div id="app"></div>
<script type="module" src="/src/main.js"></script>
```

### 3.2 main.js（本项目实际代码）

```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import App from './App.vue'
import router from './router.js'
import './style.css'

createApp(App)
  .use(ElementPlus, { locale: zhCn })
  .use(router)
  .mount('#app')
```

| 代码 | 含义 |
|------|------|
| `createApp(App)` | 以 `App.vue` 为根创建应用实例 |
| `.use(ElementPlus)` | 注册 `el-button` 等组件 + 中文 |
| `.use(router)` | 安装 Vue Router |
| `.mount('#app')` | 渲染到 `#app`，进入运行阶段 |

MES 版 `main.js` 会循环注册所有图标；本项目 **未全局注册图标**，孩子页用 emoji，家长页用 Element 默认按钮。

### 3.3 挂载与 `<router-view />`

```
#app
 └── App.vue（顶栏 + main）
      └── router-view
           ├── ChildChat.vue    （URL = /）
           └── ParentPanel.vue  （URL = /parent）
```

切换「孩子模式 / 家长模式」链接时，只替换 `router-view` 里的组件，顶栏不变——典型 SPA。

### 3.4 vite.config.js

```javascript
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
```

前端写 `fetch('/api/lessons')`，Vite 开发服务器转发到后端 8000，避免跨域。

---

## 4. Vue 3 核心概念（本项目用到的）

### 4.1 ref — 响应式数据

```javascript
const messages = ref([])
messages.value.push({ role: 'user', content: text })  // script 里要 .value
```

```html
<div v-for="(msg, idx) in messages" :key="idx">
```

template 里自动解包，不用写 `.value`。

### 4.2 reactive — 表单对象

`ParentPanel.vue`：

```javascript
const form = reactive({
  lesson_id: 1,
  difficulty: 'interest',
  family_notes: '',
})
```

```html
<el-select v-model="form.lesson_id">
```

多个字段绑在一起时用 `reactive`；聊天消息列表用 `ref([])` 更直观。

### 4.3 computed — 派生数据

```javascript
const lessonTitle = computed(() => {
  const found = lessons.value.find((l) => l.id === settings.value.lesson_id)
  return found?.title || '...'
})
```

`settings.lesson_id` 或 `lessons` 变时，标题自动更新。

### 4.4 watch — 监听变化

```javascript
watch(() => form.lesson_id, (id) => {
  const lesson = lessons.value.find((l) => l.id === id)
  if (lesson) form.family_notes = lesson.family_notes || ''
})
```

切换讲次时，自动切换 textarea 里的家庭笔记。

### 4.5 生命周期

```javascript
onMounted(loadLessons)   // 页面第一次显示时拉 21 讲目录
```

### 4.6 常用模板指令

| 指令 | 本项目例子 |
|------|-----------|
| `v-for` | 聊天气泡、快捷按钮 |
| `v-if` / `v-else` | 流式中显示 `streamBuffer`、语音提示 |
| `v-model` | `input`、`form.lesson_id` |
| `:disabled` | `loading \|\| listening` 时禁发送 |
| `:class` | `bubble user` / `assistant` |
| `@click` / `@keyup.enter` | 发送、麦克风 |

### 4.7 script setup

本项目全部页面使用 `<script setup>`：顶层 `ref` 自动暴露给 template，无需 `export default { setup() }`。

### 4.8 Composables — 逻辑复用

```javascript
const { listening, toggleListening } = useSpeechInput({ onFinal: (text) => send(text) })
```

`ChildChat` 与 `ParentPanel` 共用语音输入，细节封装在 `composables/useSpeechInput.js`。

---

## 5. 单文件组件 .vue 的结构

```vue
<template>
  <!-- HTML 结构 + Vue 指令 -->
</template>

<script setup>
// 逻辑：import、ref、函数
</script>

<style scoped>
/* 只作用于本组件；scoped 加唯一属性选择器 */
</style>
```

---

## 6. 全局入口与布局 App.vue

```
┌─────────────────────────────────────┐
│  🧮 小思陪练    [孩子模式] [家长模式]  │  ← topbar
├─────────────────────────────────────┤
│                                     │
│         <router-view />             │  ← ChildChat 或 ParentPanel
│                                     │
└─────────────────────────────────────┘
```

```html
<nav>
  <router-link to="/">孩子模式</router-link>
  <router-link to="/parent">家长模式</router-link>
</nav>
<main>
  <router-view />
</main>
```

- `router-link`：声明式导航，当前路由加 `router-link-active` 样式
- 无 MES 式侧边栏 `el-menu`；结构更简单

---

## 7. 路由系统 router.js

```javascript
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/ChildChat.vue'), meta: { title: '小思陪练' } },
    { path: '/parent', component: () => import('./views/ParentPanel.vue'), meta: { title: '家长设置' } },
  ],
})
```

| 概念 | 说明 |
|------|------|
| `path: '/'` | 默认孩子聊天页 |
| `() => import(...)` | 路由懒加载 |
| `meta.title` | 可给顶栏用（当前 App 未读，预留） |

**编程式跳转（家长页）：**

```javascript
import { useRouter } from 'vue-router'
const router = useRouter()
router.push('/')   // 进入孩子模式
```

---

## 8. API 层 api.js（含 SSE）

本项目 **用原生 `fetch`**，不用 axios。

### 8.1 设置持久化（localStorage）

```javascript
const STORAGE_KEY = 'gaosi_tutor_settings'

export function loadSettings() { ... }
export function saveSettings(partial) { ... }
```

存 `lesson_id`、`difficulty`；与 `gaosi_tutor_session_id`（session）分开。

### 8.2 REST 接口

| 函数 | 方法 | 路径 |
|------|------|------|
| `fetchLessons` | GET | `/api/lessons` |
| `updateLessonNotes` | PATCH | `/api/lessons/{id}/notes` |
| `fetchRagStats` | GET | `/api/rag/stats` |
| `indexAllRag` | POST | `/api/rag/index` |
| `searchRag` | POST | `/api/rag/search` |

### 8.3 SSE 流式聊天 — `tutorChatStream`

后端返回 `text/event-stream`，格式：

```
event: delta
data: {"content":"你"}

event: tool_end
data: {"tool":"generate_practice","diagram":{...}}

event: done
data: {"answer":"...","session_id":"uuid",...}
```

**前端解析要点：**

```javascript
export function tutorChatStream(payload, onEvent) {
  return new Promise((resolve, reject) => {
    fetch('/api/chat/stream', { method: 'POST', body: JSON.stringify(payload) })
      .then(async (res) => {
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')   // SSE 以空行分隔事件块
          buffer = parts.pop() || ''
          for (const block of parts) {
            // 解析 event: 与 data: 行
            onEvent?.(event, data)
            if (event === 'done') donePayload = data
          }
        }
        resolve(donePayload)
      })
  })
}
```

**ChildChat 中的用法：**

```javascript
await tutorChatStream(
  { question: text, session_id, mode: 'child', lesson_id, difficulty },
  (event, data) => {
    if (event === 'delta') streamBuffer.value += data.content || ''
    if (event === 'tool_end' && data.diagram) streamDiagram.value = data.diagram
  },
)
```

| SSE 事件 | UI 反应 |
|----------|---------|
| `delta` | 追加流式文字 + 闪烁光标 |
| `tool_start` | 可显示「小思正在想题目…」 |
| `tool_end` | 出题工具可能带 `diagram`，提前显示配图 |
| `done` | 落盘 assistant 消息，保存 `session_id` |
| `error` | 显示错误气泡 |

---

## 9. 全局样式 style.css

```css
:root {
  --bg: #fff8f0;
  --card: #ffffff;
  --primary: #ff6b35;
  --primary-soft: #ffe8de;
  --accent: #4ecdc4;
  --text: #2d3436;
  --muted: #636e72;
  --border: #ffe0cc;
}
```

暖色、大字号，面向孩子与家长家庭场景。各页面 `scoped` 样式用 `var(--primary)` 等保持一致。

---

## 10. 页面与组件逐一讲解

### 10.1 ChildChat.vue — 孩子模式

**路由：** `/`  
**职责：** 流式聊天、快捷入口、语音输入/播报、数学配图。

#### 状态一览

| 变量 | 作用 |
|------|------|
| `messages` | 聊天记录 `{ role, content, diagram? }` |
| `settings` | `lesson_id`、`difficulty`、`session_id` |
| `streaming` / `streamBuffer` | 流式输出中与光标 |
| `streamDiagram` | 流式过程中提前展示的图 |
| `quickQuestions` | 「这题不懂」「出一道题」等 |

#### 发送流程 `send(question)`

```
1. push user 消息
2. streaming = true，清空 streamBuffer
3. tutorChatStream(...) 监听 delta / tool_end
4. done：session_id → localStorage
5. push assistant 消息（含 diagram）
6. finally：streaming = false，autoSpeak 时 TTS
```

#### Session 持久化

```javascript
const SESSION_KEY = 'gaosi_tutor_session_id'
// done 事件：
localStorage.setItem(SESSION_KEY, done.session_id)
```

刷新页面后同一对话记忆由后端 `tutor_sessions` 保证。

#### 快捷按钮

```html
<button v-for="q in quickQuestions" @click="send(q)">{{ q }}</button>
```

「出一道题」走后端 `practice_flow` 快捷路径，SSE 仍会发 `tool_start` / `delta`。

#### 语音

- `useSpeechInput`：`onFinal` 回调里 `send(text)`
- `useSpeechOutput`：回答结束后 `speak(answer)`，可关自动朗读

---

### 10.2 ParentPanel.vue — 家长模式

**路由：** `/parent`

#### 三块功能

```
┌─ 设置区 ─────────────────────────────┐
│ 讲次 el-select                        │
│ 难度 el-radio-group                   │
│ 家庭笔记 textarea + RAG 片段统计       │
│ [保存] [同步知识库] [进孩子模式] [新对话] │
├─ 分隔线 ─────────────────────────────┤
│ 家长提问区（简化聊天，无配图）          │
└──────────────────────────────────────┘
```

#### 家庭笔记与 RAG

```javascript
await updateLessonNotes(form.lesson_id, form.family_notes)
// 后端 PATCH 会自动 index_lesson_notes

await indexAllRag()   // 「同步知识库」全量 reindex
ragStats.value = await fetchRagStats()
```

界面展示：`知识库：N 条片段（M 讲有笔记）`。

#### 保存设置 `saveAll`

1. `updateLessonNotes` 写 MySQL + 单讲索引  
2. `saveSettings({ lesson_id, difficulty })` 写 localStorage  
3. 孩子模式 `loadSettings()` 读取同一配置  

#### 家长聊天 `ask`

与 ChildChat 类似，但 `mode: 'parent'`，无 `MathDiagram`，UI 用 `el-input`。

#### 新对话 `newSession`

```javascript
localStorage.removeItem(SESSION_KEY)
messages.value = []
```

---

### 10.3 MathDiagram.vue — 题目配图

**入参：** `spec` 对象，由后端 `generate_practice` 返回的 `diagram` 字段。

| `spec.type` | 组件 |
|-------------|------|
| `observe_match` | `ObserveMatchDiagram`（观察匹配类） |
| `views` | 多视角 SVG 面板（参照物 + panels） |

```html
<MathDiagram v-if="msg.diagram" :spec="msg.diagram" />
```

流式时可在 `tool_end` 就先显示图，不必等全文打完。

---

### 10.4 composables — 语音输入/输出

**useSpeechInput.js**

- 封装 `SpeechRecognition` / `webkitSpeechRecognition`
- `lang: 'zh-CN'`，`interimResults` 显示「正在听…」
- 返回 `supported`、`listening`、`toggleListening`、`error`

**useSpeechOutput.js**

- 封装 `speechSynthesis`
- `autoSpeak` 存 localStorage，孩子页顶栏可切换

**注意：** Chrome 桌面版体验最好；需 HTTPS 或 localhost 才允许麦克风。

---

## 11. Element Plus 组件速查

家长页常用：

| 组件 | 用途 |
|------|------|
| `el-form` / `el-form-item` | 设置表单布局 |
| `el-select` / `el-option` | 21 讲下拉 |
| `el-radio-group` | 兴趣 / 拓展 |
| `el-input type="textarea"` | 家庭笔记 |
| `el-button` `:loading` | 保存、同步、发送 |
| `el-divider` | 设置区与聊天区分隔 |
| `ElMessage` | 成功/失败提示（需 import） |

孩子页以原生 `<button>`、`<input>` 为主，按钮更大、更适合点击。

---

## 12. 如何自己添加新功能

### 示例：加「学习统计」页 `/stats`

**1. api.js**

```javascript
export async function fetchLearningStats() {
  const res = await fetch('/api/stats')
  if (!res.ok) throw new Error('加载失败')
  return res.json()
}
```

**2. views/StatsPanel.vue**

```vue
<script setup>
import { onMounted, ref } from 'vue'
import { fetchLearningStats } from '../api'
const stats = ref(null)
onMounted(async () => { stats.value = await fetchLearningStats() })
</script>
```

**3. router.js**

```javascript
{ path: '/stats', component: () => import('./views/StatsPanel.vue') }
```

**4. App.vue 导航加链接**

```html
<router-link to="/stats">学情</router-link>
```

### 通用检查清单

```
□ 后端 API 是否已有（Swagger /docs）
□ api.js 封装请求
□ views/ 新建 .vue
□ router.js 注册路由
□ App.vue 加导航（如需）
□ 要流式？→ 参考 tutorChatStream 或复用
□ 要持久化？→ localStorage 或 session_id
□ 改完 make smoke + 浏览器点一遍
```

### 复制模板建议

| 想做什么 | 参考 |
|----------|------|
| 聊天 + SSE | `ChildChat.vue` |
| 表单 + 保存 | `ParentPanel.vue` 上半部分 |
| 自定义 UI 组件 | `MathDiagram.vue` |
| 可复用逻辑 | `composables/` |

---

## 13. 常见问题 FAQ

### Q: 改了代码页面没变化？

Vite HMR 一般自动刷新。若无：看终端报错，或 Cmd+R 强刷。

### Q: 页面空白？

F12 → Console：常见为 import 路径错、后端未启动。

### Q: API 404 / Network Error？

```bash
curl http://localhost:8000/api/health
make start   # 或分别起 backend + frontend
```

确认 `vite.config.js` 里 `proxy['/api']` 指向 8000。

### Q: 聊天一直转圈？

- `DEEPSEEK_API_KEY` 是否配置  
- Network 里 `/api/chat/stream` 是否 200，EventStream 是否有 `done`  
- 后端日志是否有异常  

### Q: 语音不可用？

- 用 Chrome，允许麦克风  
- 非 localhost 需 HTTPS  
- 看 `speechError` 提示文案  

### Q: 配图不显示？

- 只有 `generate_practice` 等返回 `diagram` 时才有  
- 检查 SSE `tool_end` 里 `data.diagram`  
- `MathDiagram` 是否收到 `spec.type` 支持的类型  

### Q: 家庭笔记检索不到？

- 家长页是否 **保存** 或 **同步知识库**  
- `curl /api/rag/stats` 看 `chunks_in_store`  
- 见 [agent-rag.md](./agent-rag.md)  

### Q: ref 和 reactive 怎么选？

- 单值、会整体替换的列表 → `ref`  
- 固定字段的表单对象 → `reactive`  
- 不确定时 `ref` 更省心  

### Q: 和 MES 前端文档的关系？

MES 有 Dashboard、工单表格、终端机 SOP 等页面；**同一套 Vue 原理**，本项目换成聊天 + 家长设置。MES 版长文可参考兄弟仓库 `mes/docs/frontend-guide.md`（若存在）。

---

## 附录：与后端的接口对照

| 前端 | 后端 |
|------|------|
| `tutorChatStream` | `POST /api/chat/stream` |
| `fetchLessons` | `GET /api/lessons` |
| `updateLessonNotes` | `PATCH /api/lessons/{id}/notes` |
| `indexAllRag` | `POST /api/rag/index` |
| `session_id` in localStorage | `tutor_sessions` 表 |

---

*文档版本：与 gaosi-tutor 前端（ChildChat + ParentPanel + SSE + 语音）代码同步。*
