# 生产级 Demo 详解 — 阶段 5 实现思路

> 本文档说明：阶段 5 如何把现有 Agent 从「能跑」升级到「能演示、能调试、能回归」。  
> 四大能力：**SSE 流式**、**对话记忆**、**可观测日志**、**评估用例**。  
> 前置：阶段 0～4 已完成（Tool Calling + RAG + 写操作确认门）。

---

## 目录

1. [阶段 5 要解决什么问题](#1-阶段-5-要解决什么问题)
2. [和阶段 4 的区别](#2-和阶段-4-的区别)
3. [整体架构与实施顺序](#3-整体架构与实施顺序)
4. [能力一：SSE 流式输出](#4-能力一sse-流式输出)
5. [能力二：对话记忆（Session）](#5-能力二对话记忆session)
6. [能力三：Agent 日志与可观测](#6-能力三agent-日志与可观测)
7. [能力四：评估用例（防回归）](#7-能力四评估用例防回归)
8. [API 汇总设计](#8-api-汇总设计)
9. [前端改动要点](#9-前端改动要点)
10. [与确认门的配合](#10-与确认门的配合)
11. [推荐实施步骤（分 4 步）](#11-推荐实施步骤分-4-步)
12. [局限与改进方向](#12-局限与改进方向)
13. [自测清单](#13-自测清单)

---

## 1. 阶段 5 要解决什么问题

阶段 4 之后，Agent **功能完整**，但作为 Demo 还有明显短板：

| 现状 | 用户感受 |
|------|---------|
| `/chat` 阻塞 3～8 秒才返回整段文字 | 「卡住了？」 |
| 每次提问独立，无 `session_id` | 「刚才那个工单呢？」接不上 |
| tool 链只在响应 JSON 里看 | 排查问题要翻 Network |
| 改 prompt / 工具后靠手测 | 容易悄悄退化 |

阶段 5 目标：**工程化**，让 SanyMES AI 助手可以稳定 demo、方便调试、改代码后有自动化回归。

### 验收标准（来自学习路线）

- [ ] 前端流式聊天（打字机效果）
- [ ] 多轮对话能记住上下文（session）
- [ ] 每次请求有 tool / latency 日志
- [ ] 10 条自动化评估用例
- [ ] 能给同事做 5 分钟演示

---

## 2. 和阶段 4 的区别

| | 阶段 4 | 阶段 5 |
|--|--------|--------|
| 关注点 | **业务能力**（写操作 + 确认门） | **工程体验**（流式、记忆、日志、测试） |
| 核心改动 | tools / confirm_store / loop | llm 流式、session 表、eval 脚本 |
| API | `/chat` + `/confirm` | 新增 `/chat/stream`，扩展 session 参数 |
| 前端 | 弹窗确认 | 流式渲染 + session 持久化 |
| 业务逻辑 | 新增 create / release | **基本不动** services.py |

**原则：阶段 5 是「包一层」，不重写 Agent 核心循环。**

---

## 3. 整体架构与实施顺序

```
┌─────────────────────────────────────────────────────────┐
│  前端 AgentChat.vue                                      │
│  fetch SSE ← /chat/stream    session_id 存 localStorage   │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  router.py                                               │
│  /chat（保留）  /chat/stream（新）  /confirm（保留）      │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  loop.py（run_agent / run_agent_stream）                 │
│  决策轮：非流式 + tools  │  总结轮：流式 content          │
└───────────────────────────┬─────────────────────────────┘
                            ↓
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   tools.py           agent_sessions      agent_logs
   （不变）            agent_messages      （或 logging）
```

### 推荐实施顺序

| 步骤 | 能力 | 理由 |
|------|------|------|
| **Step 1** | SSE 流式 | 独立、见效最快，Demo 体验提升最大 |
| **Step 2** | Session 记忆 | 依赖 messages 结构，与流式 API 一起设计更顺 |
| **Step 3** | 日志 | 流式 + session 跑通后再加观测点 |
| **Step 4** | 评估脚本 | 有日志和固定用例，回归才有依据 |

每步完成后都应保持 `/chat` 非流式接口可用（Swagger / 脚本调试）。

---

## 4. 能力一：SSE 流式输出

### 4.1 为什么不是「全程流式」

Agent 循环里有两类 LLM 调用：

| 轮次 | 函数 | 是否流式 | 原因 |
|------|------|---------|------|
| **决策轮** | `chat_with_tools()` | **否** | 需要完整 `tool_calls` JSON，流式解析 fragile |
| **总结轮** | `chat()` | **是** | 给用户看的自然语言，适合逐 token 推送 |

```
用户问题
   ↓
[非流式] chat_with_tools → tool_calls?
   ↓ 是
execute_tool → tool 结果
   ↓（可能多轮）
[流式] chat → delta delta delta... → done
```

写操作遇到 `needs_confirmation` 时：**不流式**，直接 SSE 发 `pending_confirmation` 事件，与阶段 4 一致。

### 4.2 SSE 事件协议设计

端点：`POST /api/agent/chat/stream`  
`Content-Type: text/event-stream`

每条事件格式：

```
event: <type>
data: <json>

```

建议事件类型：

| event | data 示例 | 时机 |
|-------|-----------|------|
| `tool_start` | `{"tool":"get_work_order","args":{"order_no":"WO-..."}}` | 开始执行工具 |
| `tool_end` | `{"tool":"get_work_order","ok":true,"ms":45}` | 工具执行完成 |
| `delta` | `{"content":"工单"}` | 总结轮 token 片段 |
| `pending_confirmation` | 同阶段 4 的 `PendingConfirmationOut` | 写操作待确认 |
| `done` | `{"answer":"...","tool_calls":[...],"session_id":"..."}` | 本轮结束 |
| `error` | `{"message":"..."}` | 异常 |

前端监听示例：

```javascript
// 伪代码：用 fetch + ReadableStream 解析 SSE（POST 不能直接用 EventSource）
for await (const event of parseSSE(response.body)) {
  if (event.type === 'delta') appendToBubble(event.data.content)
  if (event.type === 'done') finalizeMessage(event.data)
  if (event.type === 'pending_confirmation') showConfirmDialog(event.data)
}
```

### 4.3 llm.py 改动

新增流式封装，**仅用于总结轮**：

```python
def chat_stream(messages: list[dict], *, model: str, max_tokens: int = 300):
    stream = get_llm_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
```

`chat_with_tools` **保持** `stream=False`。

### 4.4 loop.py 改动

新增生成器版本，与 `run_agent` 并行存在：

```python
def run_agent_stream(question: str, db: Session, *, messages: list[dict] | None = None):
    # 1. 复用 run_agent_from_messages 的 tool 循环逻辑
    # 2. 最后一轮改用 chat_stream，yield {"event": "delta", ...}
    # 3. 工具执行前后 yield tool_start / tool_end
    # 4. needs_confirmation 时 yield pending_confirmation 并 return
    ...
```

**不要**删掉现有 `run_agent()` — 评估脚本和 Swagger 仍可用非流式。

### 4.5 router.py 改动

```python
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
def chat_stream(data: AgentChatInput, db: Session = Depends(get_db)):
    def event_generator():
        for item in run_agent_stream(...):
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

注意：StreamingResponse 内**不要**在 generator 里用已关闭的 `db` session — 在 loop 开始前完成所有 DB 操作，或 generator 内自建 Session。

---

## 5. 能力二：对话记忆（Session）

### 5.1 要解决的场景

```
用户：WO-20250706-001 进度怎么样？
助手：生产中，当前在液压系统工位…

用户：那客户是谁？          ← 没有 session 时 LLM 不知道「那」指哪个工单
助手：（应能接上上文）
```

### 5.2 数据表设计

在 `models.py` 新增（或单独 `agent_models.py`）：

**agent_sessions**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string (UUID) | session_id |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 最后活跃 |

**agent_messages**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 主键 |
| `session_id` | FK | 所属会话 |
| `role` | string | user / assistant / system（一般只存 user+assistant） |
| `content` | text | 文本内容 |
| `tool_calls` | text (JSON) | 可选，assistant 的工具调用摘要 |
| `created_at` | datetime | |

Demo 规模：**不存完整 OpenAI messages**（含 tool 角色），只存用户可见的对话 + 工具摘要，足够多轮引用。

### 5.3 上下文窗口策略

从 DB 加载 session 最近 **N 轮**（建议 N=10 条 message 或 5 轮 QA），拼进 `run_agent`：

```python
history = load_session_messages(session_id, limit=10)
messages = [
    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    *history,
    {"role": "user", "content": question},
]
```

**不**把历史里的 tool 原始 JSON 全塞回 — 体积大且易干扰 LLM。assistant 消息保留最终回答文本即可。

### 5.4 API 扩展

**请求**（`/chat` 与 `/chat/stream` 共用）：

```python
class AgentChatInput(BaseModel):
    question: str
    session_id: str | None = None   # 空则新建 session
```

**响应** `done` 事件 / `AgentChatOutput` 增加：

```python
session_id: str
```

### 5.5 前端

- `session_id` 存 `localStorage`（`sanymes_agent_session`）
- 刷新页面后同 session 继续聊
- 可选：「新对话」按钮清空 session_id

### 5.6 与 confirm 的关系

`/confirm` 执行写操作后，应把 **assistant 最终回答** 写入 session，否则「创建完工单」后的总结会丢失。

`pending_confirmation` 本身可不写入 history（用户还没确认）。

---

## 6. 能力三：Agent 日志与可观测

### 6.1 要记录什么

每次 `/chat` 或 `/chat/stream` 请求一条 **trace**：

| 字段 | 示例 |
|------|------|
| `request_id` | UUID |
| `session_id` | 可选 |
| `question` | 用户原问 |
| `tools` | `[{"tool":"get_work_order","ms":32,"ok":true}]` |
| `llm_turns` | 2 |
| `total_ms` | 4200 |
| `model` | deepseek-v4-flash |
| `status` | ok / pending / error |
| `created_at` | timestamp |

### 6.2 实现方式（Demo 级）

**方案 A（推荐）：SQLite 表 `agent_traces`**

- 与现有 `sanymes.db` 同库，零额外依赖
- 可在 Dashboard 或简单 `/api/agent/traces` 查询最近 20 条

**方案 B：Python logging 写文件**

- `backend/logs/agent.log` 一行 JSON
- 适合本地调试，前端不好展示

在 `loop.py` 用 `try/finally` 包裹，无论成功失败都写 trace：

```python
started = time.perf_counter()
try:
    result = ...
finally:
    log_agent_trace(request_id=..., tools=tool_trace, total_ms=...)
```

流式接口在 `done` / `error` 事件发出前写日志。

### 6.3 调试价值

- 「为什么这次慢了？」→ 看 `tools` 各段 ms 和 `llm_turns`
- 「为什么没调 search_sop？」→ 对比 question 和 tool_trace
- 评估失败时附 `request_id` 查详情

---

## 7. 能力四：评估用例（防回归）

### 7.1 目标

固定 **10 个问题**，每次改 prompt / tools / loop 后跑一遍，检查：

1. 是否调用了**期望的工具**（顺序可宽松）
2. 是否**没有**调用 forbidden 工具（如只读问题不应 create）
3. （可选）回答是否包含关键词

### 7.2 用例表示例

文件：`backend/scripts/agent_eval.py` 或 `backend/tests/agent_eval_cases.json`

```python
CASES = [
    {
        "id": "read_order_progress",
        "question": "WO-20250706-001 进度怎么样？",
        "expect_tools": ["get_work_order"],
        "forbidden_tools": ["create_work_order"],
    },
    {
        "id": "list_orders",
        "question": "现在有哪些工单在生产？",
        "expect_tools": ["list_work_orders"],
    },
    {
        "id": "sop_safety",
        "question": "液压系统工位要注意什么安全事项？",
        "expect_tools": ["search_sop"],
        "answer_contains": ["液压"],
    },
    {
        "id": "create_preview",
        "question": "给测试客户建一条 52 米泵车工单，数量 1",
        "expect_tools": ["list_products", "create_work_order"],
        "expect_pending": "create_work_order",  # 应停在确认门，不真创建
    },
    # ... 共 10 条
]
```

### 7.3 运行方式

```bash
cd backend
python -m scripts.agent_eval          # 调真实 LLM（需 .env API Key）
python -m scripts.agent_eval --dry    # 只测 tools 层，不调 LLM（可选）
```

输出：

```
[PASS] read_order_progress  tools=['get_work_order']  2.1s
[FAIL] sop_safety           expected search_sop, got []  3.4s
---
8/10 passed
```

### 7.4 写操作用例注意

- **不要**在 CI 里真 execute 写操作（污染数据库）
- 测到 `pending_confirmation` 即 PASS
- 真 execute 的集成测试单独标记 `@manual`

### 7.3 依赖

- 现有项目**无 pytest** — 阶段 5 可用纯脚本 + `assert`，不必强行引入测试框架
- 若加 pytest，放 `backend/tests/test_agent_eval.py` 调用同一 CASES

---

## 8. API 汇总设计

| 接口 | 阶段 | 请求 | 响应 |
|------|------|------|------|
| `POST /api/agent/chat` | 2+ | `{question, session_id?}` | JSON（保留） |
| `POST /api/agent/chat/stream` | **5 新** | 同上 | SSE 事件流 |
| `POST /api/agent/confirm` | 4 | `{action_id}` | JSON（保留，可选加 session_id） |
| `GET /api/agent/traces` | **5 新** | `?limit=20` | 最近 trace 列表（可选） |

Schema 扩展：

```python
class AgentChatInput(BaseModel):
    question: str
    session_id: str | None = None

class AgentChatOutput(BaseModel):
    answer: str
    tool_calls: list[dict] = []
    pending_confirmation: PendingConfirmationOut | None = None
    session_id: str | None = None      # 新增
    request_id: str | None = None      # 新增，便于查日志
```

---

## 9. 前端改动要点

文件：`frontend/src/views/AgentChat.vue`、`frontend/src/api.js`

### 9.1 流式

- 默认走 `/chat/stream`；失败时 fallback 到 `/chat`（可选）
- 发送后立即插入**空 assistant 气泡**，`delta` 事件追加 `content`
- `tool_start` / `tool_end` 可在气泡下方实时展示「正在查询工单…」
- `loading` 状态在收到第一个 `delta` 或 `done` 时结束

### 9.2 api.js

```javascript
export async function agentChatStream(question, sessionId, onEvent) {
  const res = await fetch('/api/agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  })
  // 解析 SSE，每事件回调 onEvent(type, data)
}
```

### 9.3 Session

```javascript
const SESSION_KEY = 'sanymes_agent_session'
let sessionId = localStorage.getItem(SESSION_KEY)
// done 事件里：sessionId = data.session_id; localStorage.setItem(...)
```

### 9.4 确认门

- `pending_confirmation` 仍用 `ElMessageBox` + `/confirm`
- confirm 响应若含 `answer`，可非流式一次性显示（阶段 5 简化方案）
- 若 confirm 后也有长回答，可第二步再给 `/confirm/stream`（**非必须**）

---

## 10. 与确认门的配合

阶段 4 的确认流在阶段 5 中**保留**，交互略调整：

```
流式 /chat/stream
   ↓
tool_start: list_products
tool_end
tool_start: create_work_order
   ↓
event: pending_confirmation   ← 流暂停，不发 delta
   ↓
前端弹窗 → POST /confirm（非流式 JSON）
   ↓
若还有 release：再次 pending_confirmation
   ↓
最终 answer 可通过 confirm 响应一次性返回，或再开短流式
```

**推荐简化：** 确认门全程非流式；只有「纯只读 / 总结轮」走流式。Demo 足够用。

---

## 11. 推荐实施步骤（分 4 步）

### Step 1：SSE 流式（1～2 天）✅ 已实现

| 任务 | 文件 |
|------|------|
| `chat_stream()` | `llm.py` |
| `run_agent_stream()` | `loop.py` |
| `POST /chat/stream` | `router.py` |
| 前端打字机 | `AgentChat.vue`, `api.js` |

**验收：** 问「WO-20250706-001 进度」可见逐字输出；tool 仍正常；`/chat` 非流式仍可用。

### Step 2：Session 记忆（1 天）✅ 已实现（MySQL）

| 任务 | 文件 |
|------|------|
| 表 `agent_sessions` / `agent_messages` | `models.py` |
| load/save session | `agent/session_store.py` |
| 扩展 Input/Output | `schemas.py` |
| localStorage | `AgentChat.vue` |
| 全库切 MySQL | `database.py`, `settings.py`, `DATABASE_URL` |

**验收：** 先问工单进度，再问「客户是谁」能答对；刷新页面同 session 继续聊。

### Step 3：日志（0.5 天）✅ 已实现

| 任务 | 文件 |
|------|------|
| 表 `agent_traces` | `models.py` |
| 写 trace / 查询 | `agent/trace_store.py` |
| 埋点 | `router.py`（chat / stream / confirm） |
| 查询 API | `GET /api/agent/traces` |

**验收：** 每次 chat 后 MySQL `agent_traces` 有记录；可用 `GET /api/agent/traces` 查看最近 20 条。

### Step 4：评估脚本（1 天）✅ 已实现

| 任务 | 文件 |
|------|------|
| 10 条 LLM 用例 + 2 条 dry | `scripts/agent_eval.py` |

**运行：**
```bash
cd backend
./venv/bin/python -m scripts.agent_eval --dry    # 不调 LLM，测 tools
./venv/bin/python -m scripts.agent_eval          # 需 API Key
./venv/bin/python -m scripts.agent_eval --list   # 列出用例
```

**验收：** dry 模式 2/2 PASS；LLM 模式 ≥8/10 PASS（依赖模型稳定性）。

---

## 12. 局限与改进方向

| 局限 | 说明 | 后续 |
|------|------|------|
| 流式仅总结轮 | 决策轮仍阻塞 | 可接受；工业界常见做法 |
| Session 不存 tool 消息 | 极复杂多轮可能丢上下文 | 存 tool 摘要或 LangGraph checkpoint |
| SQLite 单进程 | 并发写 session 弱 | 生产换 PostgreSQL |
| 评估依赖真实 LLM | CI 不稳定/耗钱 | 加 mock 或 recorded responses |
| 无鉴权 | 任何人可 chat | 接登录后再说 |
| confirm 非流式 | 确认后回答一次性出现 | 可选 `/confirm/stream` |

---

## 13. 自测清单

```
SSE 流式
[ ] POST /chat/stream 返回 text/event-stream
[ ] 只读问题有 delta 打字效果
[ ] tool_start / tool_end 能在前端看到（或 done 里 tool_calls 正确）
[ ] /chat 非流式仍可用

Session
[ ] 首次请求返回 session_id
[ ] 刷新页面后同 session 多轮对话
[ ] 「新对话」清空 session

日志
[ ] 每次请求有 trace（tools + total_ms）
[ ] 失败请求也有 trace

评估
[ ] agent_eval.py 10 条用例可运行
[ ] 改坏 prompt 后 eval 能 FAIL

确认门（回归）
[ ] 流式 + 创建下达仍弹窗两次
[ ] 取消不写库

演示
[ ] 5 分钟脚本：查工单 → 搜 SOP → 创建下达 → 展示 trace
```

### 5 分钟演示脚本（建议）

1. **查进度**（流式）— 「WO-20250706-001 进度怎么样？」
2. **搜 SOP** — 「液压系统安全注意事项」
3. **多轮** — 「刚才那个工单客户是谁？」
4. **写操作** — 「给中建三局建 52 米泵车 1 台并下达」→ 两次确认
5. **运维感** — 打开 traces 或日志，指给同事看 tool 链和耗时

---

## 文件规划（阶段 5 完成后）

```
backend/app/agent/
├── llm.py                 ← + chat_stream
├── loop.py                ← + run_agent_stream；埋 log
├── router.py              ← + /chat/stream, /traces?
├── session.py             ← 新建：load/save messages
├── trace.py               ← 新建：写 agent_traces（可选合并 session.py）
└── ...

backend/app/models.py      ← + AgentSession, AgentMessage, AgentTrace
backend/scripts/agent_eval.py   ← 新建

frontend/src/
├── api.js                 ← + agentChatStream
└── views/AgentChat.vue    ← 流式 UI + session
```

---

> 相关文档：[Agent 学习路线](./agent-learning-roadmap.md) · [写操作与确认门](./agent-write-confirm.md) · [Function Calling](./agent-function-calling.md) · [后续演进路线](./agent-evolution.md)
