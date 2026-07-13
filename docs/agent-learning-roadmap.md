# SanyMES Agent 学习路线

> 以本仓库 MES Demo 为底座，从零学会 Agent 开发。  
> 路线设计为**项目驱动**：每个阶段产出一个能演示的功能，而不是先啃完所有理论。

---

## 目录

1. [学习目标](#1-学习目标)
2. [前置知识](#2-前置知识)
3. [整体架构地图](#3-整体架构地图)
4. [六个阶段总览](#4-六个阶段总览)
5. [阶段 0：LLM 基础](#5-阶段-0llm-基础)
6. [阶段 1：Context Injection](#6-阶段-1context-injection)
7. [阶段 2：Tool Calling](#7-阶段-2tool-calling)
8. [阶段 3：RAG 检索](#8-阶段-3rag-检索)
9. [阶段 4：多步规划 Agent（已完成）](#9-阶段-4多步规划-agent已完成)
10. [阶段 5：生产级 Demo（待做）](#10-阶段-5生产级-demo待做)
11. [目录与文件对照](#11-目录与文件对照)
12. [API 与测试入口](#12-api-与测试入口)
13. [配套文档索引](#13-配套文档索引)
14. [学习节奏建议](#14-学习节奏建议)
15. [常见弯路](#15-常见弯路)

---

## 1. 学习目标

学完本路线，你应该能够：

- 调用 LLM API（messages、system prompt、token）
- 理解 **Context Injection** 与 **Tool Calling** 的区别
- 手写 Agent 主循环（`while` + `tool_calls`）
- 把现有业务 API 包装成 Agent 工具
- 用 RAG 检索非结构化文档（SOP）
- 知道如何优化延迟、防止幻觉、做 human-in-the-loop

**最终交付物：** 一个能对话的「SanyMES AI 助手」，可查工单、列生产状态、检索 SOP。

---

## 2. 前置知识

| 领域 | 要求 | 本项目中的体现 |
|------|------|----------------|
| Python | 会函数、dict、async 基础即可 | FastAPI、`service.py` |
| HTTP / JSON | 理解 POST 请求体 | `/api/agent/chat` |
| 本仓库后端 | 能跑 `./start.sh` | `backend/run.py` |
| 前端（可选） | 会 copy Vue 页面 | `/agent-chat` 聊天页 |
| LLM 概念 | 零基础可学 | 从阶段 0 开始 |

**不必先学：** LangChain、LangGraph、向量数据库理论、Multi-Agent。

---

## 3. 整体架构地图

```
用户（浏览器 / curl / AgentChat.vue）
        ↓ POST /api/agent/chat
   router.py          ← HTTP 层，薄
        ↓
   loop.py            ← Agent 主循环（阶段 2 核心）
        ↓                    ↓
   llm.py              tools.py ──→ service.py / rag/ / services.py
   chat_with_tools     execute_tool      ↑ 复用 MES 业务逻辑
   chat()                                ↓
                                    SQLite (sanymes.db)
```

**四层模型（与前端指南类似）：**

```
第 4 层  Agent（loop / tools / RAG）     ← 本路线重点
第 3 层  FastAPI 路由 + Pydantic
第 2 层  MES 业务（services.py）
第 1 层  数据库（工单、工位、SOP）
```

---

## 4. 六个阶段总览

| 阶段 | 主题 | 交付物 | 状态 |
|------|------|--------|------|
| **0** | LLM 基础 | `scripts/agent_playground.py` | ✅ 已完成 |
| **1** | Context Injection | `POST /api/agent/ask` | ✅ 已完成 |
| **2** | Tool Calling | `POST /api/agent/chat` + `loop.py` | ✅ 已完成 |
| **3** | RAG | `search_sop` 工具 + `rag/` | ✅ 已完成 |
| **4** | 多步规划 + 写操作 | 一句话创建/下达工单 | ⬜ 待做 |
| **5** | 生产级 Demo | 流式、会话、评估 | ✅ 已完成 |

**原则：**

- 先裸写循环，后上框架（LangGraph 等）
- 阶段 1 的 `/ask` 保留，与阶段 2 的 `/chat` 对比学习
- 每个阶段都有可 `curl` 或页面演示的验收标准

---

## 5. 阶段 0：LLM 基础

### 目标

会调 LLM API，理解 `messages` 和 `system prompt`。

### 交付物

```
backend/scripts/agent_playground.py
backend/config/.env              # DEEPSEEK_API_KEY 等
```

### 核心概念

- `messages`：`system` / `user` / `assistant`
- `temperature`、`max_tokens`
- 流式 `stream=True`（可选）

### 动手

```bash
cd backend
source venv/bin/activate
python scripts/agent_playground.py "MES 里工单下达和物料配送是什么关系？"
python scripts/agent_playground.py --stream "简要说明 MES"
```

### 验收

- [ ] 能解释 system prompt 的作用
- [ ] 能换 3 个不同问题测试
- [ ] 知道 API Key 不要提交 git

---

## 6. 阶段 1：Context Injection

### 目标

后端查数据库 → 把数据塞进 prompt → LLM 解释。**代码决定查什么**。

### 交付物

```
backend/app/agent/
├── service.py       # extract_order_no → build_context → llm_explain
├── llm.py           # complete()
├── prompts.py       # MES_ADVISOR + build_messages
└── router.py        # POST /api/agent/ask
```

### 数据流

```
问题 → 正则提取工单号 → 查单条/列表摘要 → JSON 塞进 user message → LLM 回答
```

### 与阶段 2 的本质区别

| | 阶段 1 | 阶段 2 |
|--|--------|--------|
| 谁决定查库 | Python 代码 | LLM 选工具 |
| 数据怎么给 LLM | 预先注入 context | tool 返回结果 |

### 动手

```bash
curl -X POST http://localhost:8000/api/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "WO-20250706-001 进度怎么样？"}'
```

### 验收

- [ ] 指定工单号能答对状态
- [ ] 泛化问题「有哪些工单在生产」能回答
- [ ] 假工单号返回「不存在」
- [ ] 简单问题走 `maybe_direct_answer` 不调 LLM

---

## 7. 阶段 2：Tool Calling

### 目标

LLM 自己决定调哪个工具；你手写 Agent 循环。

### 交付物

```
backend/app/agent/
├── tools.py         # TOOLS 定义 + execute_tool
├── loop.py          # run_agent 主循环
├── llm.py           # chat_with_tools() + chat()
└── router.py        # POST /api/agent/chat

frontend/src/views/AgentChat.vue   # 页面测试
```

### 核心概念

- `tools` 参数（JSON Schema）
- `message.tool_calls` vs `message.content`
- `role: tool` + `tool_call_id`
- 第 2 轮不传 `tools`（总结轮）

### 详细文档

→ [agent-function-calling.md](./agent-function-calling.md)

### 当前工具

| 工具 | 用途 |
|------|------|
| `get_work_order` | 按工单号查详情 |
| `list_work_orders` | 工单列表摘要 |
| `search_sop` | SOP / 安全规范检索（阶段 3） |

### 动手

```bash
# 命令行
cd backend && python -m app.agent.loop

# HTTP
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "WO-20250706-001 进度怎么样？"}'

# 页面
open http://localhost:5173/agent-chat
```

### 验收

- [ ] LLM 自动选择正确工具
- [ ] 响应含 `tool_calls` 字段
- [ ] `tools.py` 的 `if __name__` 自测通过
- [ ] 理解 messages 完整序列（见 function-calling 文档第 8 节）

### 性能优化（已做）

- 默认 `deepseek-v4-flash`
- 工具结果就绪后第 2 轮用 `chat()` 不传 tools
- `max_tokens=300` + prompt 要求简短回答

---

## 8. 阶段 3：RAG 检索

### 目标

检索工位 **SOP 长文本**，回答操作步骤、安全注意事项。

### 交付物

```
backend/app/agent/rag/
├── chunks.py        # 从工艺路线切分 chunk
├── retriever.py     # SopRetriever（关键词 / 向量）
└── __init__.py

tools.py             # search_sop 工具
main.py              # 启动时 build_index
```

### 核心概念

- **SOP**：标准作业程序
- **Chunk**：检索最小单位（本项目：工位 × sop/safety）
- **Index → Retrieve → Augment → Generate**

### 详细文档

→ [agent-rag.md](./agent-rag.md)

### 动手

```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -d '{"question": "液压系统工位要注意什么安全事项？"}'
```

### 验收

- [ ] 启动日志 `[RAG] SOP 索引已加载：14 个文本块`
- [ ] 问安全/SOP 时 `tool_calls` 含 `search_sop`
- [ ] 答案引用「液压油禁止接触皮肤」等真实 SOP 内容
- [ ] （可选）配置 `EMBEDDING_MODEL` 启用向量检索

---

## 9. 阶段 4：多步规划 Agent（已完成）

### 目标

一句话完成**多步写操作**，例如：

> 「给中建三局建一条 52 米泵车工单，数量 1，然后下达」

### 已交付

| 新增工具 | 包装 |
|---------|------|
| `list_products` | 查产品列表 |
| `create_work_order` | `services.create_work_order` |
| `release_work_order` | `services.release_work_order` |

| 新增能力 | 说明 |
|---------|------|
| 确认门 | 写操作 preview → 前端弹窗 → `POST /api/agent/confirm` |
| 链式确认 | 创建、下达各弹一次窗 |
| `confirm_store.py` | 内存暂存 PendingAction + 对话上下文 |

详见 **[agent-write-confirm.md](./agent-write-confirm.md)**。

### 验收标准

- [x] 一句话触发 3+ 步工具链
- [x] 某步失败时优雅停止并报告
- [x] 危险操作有确认门（弹窗 + `/confirm`）

---

## 10. 阶段 5：生产级 Demo（已完成）

### 目标

工程化：流式、会话、可观测、评估。

| 能力 | 说明 | 状态 |
|------|------|------|
| SSE 流式 | `POST /api/agent/chat/stream` | ✅ |
| 对话记忆 | MySQL `agent_sessions` / `agent_messages` | ✅ |
| 日志 | MySQL `agent_traces` + `GET /api/agent/traces` | ✅ |
| 评估 | `scripts/agent_eval.py` 10 问 | ✅ |

详见 **[agent-production.md](./agent-production.md)**。

### 验收标准

- [x] 前端流式聊天
- [x] Session 多轮记忆（MySQL）
- [x] Agent trace 日志
- [x] 10 条自动化评估用例（+ 2 条 dry）

---

## 11. 目录与文件对照

```
mes/
├── docs/
│   ├── agent-learning-roadmap.md    ← 本文档
│   ├── agent-function-calling.md    ← 阶段 2 深入
│   ├── agent-rag.md                 ← 阶段 3 深入
│   ├── agent-write-confirm.md       ← 阶段 4 深入
│   ├── agent-production.md          ← 阶段 5 深入（实现思路）
│   └── frontend-guide.md            ← 前端 7 概念
├── backend/
│   ├── scripts/agent_playground.py  ← 阶段 0
│   ├── scripts/agent_eval.py        ← 阶段 5 评估
│   ├── config/.env                  ← API Key（勿提交）
│   └── app/agent/
│       ├── router.py                ← /ask + /chat + /confirm
│       ├── service.py               ← 阶段 1
│       ├── tools.py                 ← 阶段 2/4 工具
│       ├── loop.py                  ← 阶段 2/4 循环
│       ├── confirm_store.py         ← 阶段 4 待确认暂存
│       ├── session_store.py         ← 阶段 5 Session
│       ├── trace_store.py           ← 阶段 5 日志
│       ├── llm.py                   ← LLM 封装
│       ├── prompts.py               ← 提示词
│       ├── client.py                ← 早期实验（可忽略）
│       └── rag/                     ← 阶段 3
└── frontend/src/views/
    └── AgentChat.vue                ← 聊天测试页
```

---

## 12. API 与测试入口

| 接口 | 阶段 | 说明 |
|------|------|------|
| `POST /api/agent/ask` | 1 | Context Injection，代码决定查什么 |
| `POST /api/agent/chat` | 2+3+4 | Tool Calling + RAG + 写操作（JSON，保留调试） |
| `POST /api/agent/chat/stream` | **5** | SSE 流式（前端默认） |
| `POST /api/agent/confirm` | 4 | 确认并执行写操作，继续 Agent |
| `GET /api/agent/traces` | **5** | 最近 Agent 请求 trace（默认 20 条） |
| Swagger | 全部 | http://localhost:8000/docs |
| 聊天页 | 2+ | http://localhost:5173/agent-chat |
| 原生 JS Demo | 前端学习 | http://localhost:5173/native-demo.html |

### 推荐体验顺序

1. Swagger 调 `/ask` 和 `/chat`，对比同一问题的差异
2. 打开 `/agent-chat`，点示例问题，看 `tool_calls`
3. 读 `loop.py`，对照 [function-calling 文档](./agent-function-calling.md) 走一遍 messages
4. 问 SOP 问题，再读 [RAG 文档](./agent-rag.md)
5. 试「创建并下达」示例，读 [写操作与确认门文档](./agent-write-confirm.md)

---

## 13. 配套文档索引

| 文档 | 何时读 |
|------|--------|
| **本文档** | 总路线、进度核对 |
| [mes-data-model.md](./mes-data-model.md) | 不熟悉 MES 业务、不懂表结构时 |
| [agent-function-calling.md](./agent-function-calling.md) | 学阶段 2，不懂 tool_calls 时 |
| [agent-rag.md](./agent-rag.md) | 学阶段 3，不懂 chunk/检索时 |
| [agent-write-confirm.md](./agent-write-confirm.md) | 学阶段 4，不懂确认门/写操作时 |
| [agent-production.md](./agent-production.md) | 阶段 5 流式/session/评估 |
| [engineering.md](./engineering.md) | CI、部署、运维命令 |
| [agent-evolution.md](./agent-evolution.md) | 阶段 5 之后：框架、RAG、观测等演进方向 |
| [frontend-guide.md](./frontend-guide.md) | 改 AgentChat 页面或加前端功能 |
| [backend/FASTAPI_GUIDE.md](../backend/FASTAPI_GUIDE.md) | 不懂路由、Depends 时 |

---

## 14. 学习节奏建议

### 快速路径（已有 Python / 后端基础）

| 天 | 内容 |
|----|------|
| Day 1 | 阶段 0 + 读 function-calling 文档前 3 节 |
| Day 2 | 阶段 1 `/ask`，理解 context injection |
| Day 3～4 | 阶段 2：tools.py → loop.py → `/chat` |
| Day 5 | 阶段 3 + agent-rag 文档 |
| Day 6+ | 阶段 5（流式 SSE）或前端优化 AgentChat |

### 业余节奏（每天 1～2 小时）

- **一周** 完成阶段 0～2
- **第二周** 阶段 3 + 消化文档
- **第三周** 阶段 4 + agent-write-confirm 文档
- **第四周起** 阶段 5

---

## 15. 常见弯路

| 弯路 | 正确做法 |
|------|---------|
| 第一天就上 LangChain | 先手写 `loop.py` 30 行 |
| 阶段 2 全量 JSON 塞 prompt | 用 tools 按需查询 |
| 函数里有 `yield` 却当普通函数调用 | generator 要迭代或拆函数 |
| PyCharm 直接跑 `loop.py` 报 import 错 | bootstrap 或 `python -m app.agent.loop` |
| SQLite 路径随 cwd 变 | 从 `backend/` 启动或 chdir |
| `from backend.app...` 包 import | 用 `from ..models` 或 `from app.xxx` |
| 忽略 `tool_call_id` | assistant(tool_calls) 和 tool 必须成对 |
| RAG 和 Tool Calling 对立 | RAG 是多种 tool 之一（`search_sop`） |
| 写操作不经确认直接改库 | preview + `/confirm` 两态，allow_write 控制 |

---

## 进度自检表

复制到你的笔记，完成一项勾一项：

```
阶段 0
[ ] agent_playground.py 跑通
[ ] 理解 messages 结构

阶段 1
[ ] /api/agent/ask 跑通
[ ] 能解释 context injection

阶段 2
[ ] tools.py 自测通过
[ ] loop.py 自测通过
[ ] /api/agent/chat 跑通
[ ] 读过 agent-function-calling.md
[ ] AgentChat 页面能聊天

阶段 3
[ ] 启动看到 SOP 索引 14 块
[ ] search_sop 被正确调用
[ ] 读过 agent-rag.md

阶段 4
[ ] 写操作工具 + 确认门
[ ] 多步工具链（创建 + 下达）
[ ] 读过 agent-write-confirm.md

阶段 5
[ ] 流式 SSE
[ ] Session 记忆（MySQL）
[ ] Agent trace 日志
[ ] agent_eval.py（--dry 2/2，LLM ≥8/10）
[ ] 读过 agent-production.md
```

---

> **当前进度：阶段 0～5 已全部完成。** 后续演进见 [agent-evolution.md](./agent-evolution.md)（框架、RAG、观测、业务扩展等）。  
> 运行评估：`cd backend && ./venv/bin/python -m scripts.agent_eval`
