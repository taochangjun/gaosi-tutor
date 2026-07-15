# 家庭笔记 RAG 详解 — gaosi-tutor 项目

> 本文档说明：什么是家庭笔记、为什么需要 RAG、本项目如何切块/索引/检索、如何与 Agent 配合。  
> 配套代码：`backend/app/agent/rag/`，工具入口：`search_family_notes`（`tools.py`）。  
> 延伸阅读：[fastembed-learning.md](./fastembed-learning.md)（本地 Embedding）、[chroma-learning.md](./chroma-learning.md)（Chroma API 与实验）、[vector-db-learning.md](./vector-db-learning.md)（向量库原理与选型）、[sqlalchemy-learning.md](./sqlalchemy-learning.md)（MySQL 原文存储）。

---

## 目录

1. [什么是家庭笔记](#1-什么是家庭笔记)
2. [为什么需要 RAG](#2-为什么需要-rag)
3. [什么是 RAG](#3-什么是-rag)
4. [RAG 在本项目中的位置](#4-rag-在本项目中的位置)
5. [双存储：MySQL + Chroma](#5-双存储mysql--chroma)
6. [Chunk 切分策略](#6-chunk-切分策略)
7. [索引管线 indexer](#7-索引管线-indexer)
8. [检索 search_family_notes](#8-检索-search_family_notes)
9. [配置与启用](#9-配置与启用)
10. [HTTP API 与家长面板](#10-http-api-与家长面板)
11. [与 Function Calling 的配合](#11-与-function-calling-的配合)
12. [走一遍完整例子](#12-走一遍完整例子)
13. [局限与改进方向](#13-局限与改进方向)
14. [自测与调试](#14-自测与调试)

---

## 1. 什么是家庭笔记

**家庭笔记（family_notes）** 是家长在家长面板为每一讲写的 **陪练要点**，例如孩子薄弱点、出题偏好、本讲提醒——**不是课本原文**。

| 存储 | 表/集合 | 字段 | 含义 |
|------|---------|------|------|
| MySQL | `lesson_progress` | `family_notes` | 笔记原文（source of truth） |
| MySQL | `lesson_progress` | `lesson_id` | 讲次 1～21，主键 |
| Chroma | `family_notes` collection | embedding + metadata | 检索用向量索引 |

**示例（第 5 讲《加与减》）：**

```
孩子减法还不太熟练，尤其是借位。
平时喜欢用小动物情境出题，多鼓励。
本讲练习时先确认孩子理解「比较」再进计算。
```

**版权边界**（见 [design.md](./design.md)）：

- 不存储、不索引高思课本原文或扫描件
- RAG 只检索 **家长自写** 的内容
- 讲次标题/专题来自静态 JSON `grade1-upper.json`，不进向量库

Agent 的目标：**孩子或家长用自然语言提问时，从家庭笔记里检索相关片段再回答**，而不是让 LLM 凭空编造「孩子哪里薄弱」。

---

## 2. 为什么需要 RAG

### 仅靠 system prompt 注入不够

Phase 1 做法是把当前讲的 `family_notes` **整段塞进 system prompt**（`prompts.py` → `build_system_prompt`）：

```python
notes_block = f"【家庭笔记】\n{notes}" if notes else "【家庭笔记】（暂无）"
```

这适合「当前讲次、笔记不长」的场景，但有局限：

| 问题 | 说明 |
|------|------|
| **跨讲检索** | 家长问「这周孩子哪里最薄弱」，可能涉及多讲笔记 |
| **笔记变长** | 21 讲笔记全塞 prompt 会爆 token |
| **语义匹配** | 用户问「借位不行」，笔记写「减法还不太熟练」——字面不同、语义相近 |
| **按需取数** | 每次对话只需要 1～3 段相关片段，不必全文灌输 |

### 结构化工具也有局限

`get_lesson_context` 返回的是 **固定字段 JSON**（标题、专题、整段笔记）：

```json
{
  "ok": true,
  "id": 5,
  "title": "加与减",
  "topic": "计算",
  "family_notes": "孩子减法还不太熟练……"
}
```

适合「告诉我第 5 讲是什么」，不适合：

- 「孩子计算方面有什么要注意的？」（需语义搜索多讲）
- 「出题时有什么偏好？」（需从长笔记里抠出相关句）

### RAG 的思路

> **R（Retrieval）**：从家庭笔记库 **语义检索** 相关片段  
> **A（Augmented）**：把片段 **增强** 进 LLM 上下文（via tool message）  
> **G（Generation）**：LLM **生成** 陪练建议或答疑

只把 top-K 相关 chunk 交给 LLM，而不是 21 讲笔记全文。

---

## 3. 什么是 RAG

RAG 全称 **Retrieval-Augmented Generation（检索增强生成）**，典型流程 4 步：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Index   │ →  │ Retrieve │ →  │ Augment  │ →  │ Generate │
│  建索引   │    │  检索     │    │  增强上下文 │    │  生成回答  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

| 步骤 | 做什么 | 本项目对应 |
|------|--------|-----------|
| **Index** | 切块 + 算 embedding + 写入向量库 | `indexer.py` + `embedder.py` + `store.py` |
| **Retrieve** | 按问题找 top-K chunk | `retriever.py` → `search_family_notes()` |
| **Augment** | 检索结果作为 tool 返回值 | Agent loop 的 `role: tool` message |
| **Generate** | LLM 组织自然语言 | `loop.py` 后续轮次 `chat()` / 流式 `chat_stream()` |

### 和 Context Injection 的区别

| | system prompt 注入笔记 | RAG |
|--|----------------------|-----|
| 数据选择 | 固定当前讲整段笔记 | **检索器**按问题语义找片段 |
| 跨讲 | 不支持 | 支持（不限 `lesson_id` 时搜全库） |
| 扩展 | 改笔记即可 | 改笔记 + **reindex** 向量库 |

两者 **并存**：prompt 仍带当前讲笔记摘要；Agent 需要细粒度或跨讲信息时调 `search_family_notes`。

### 和 Tool Calling 的关系

RAG **不是替代** Function Calling，而是 **多一种工具**：

| 工具 | 用途 |
|------|------|
| `get_lesson_context` | 当前讲结构化元数据 + 整段笔记 |
| `search_family_notes` | 家庭笔记 **语义检索**（RAG） |
| `generate_practice` | 出题 |
| `evaluate_answer` | 判题 |

LLM 根据问题类型自动选择。

---

## 4. RAG 在本项目中的位置

```
backend/app/agent/rag/
├── chunker.py      # 按段落切块（≤320 字）
├── embedder.py     # fastembed 本地 Embedding
├── store.py        # Chroma PersistentClient 封装
├── indexer.py      # MySQL 笔记 → 切块 → 向量 → upsert
├── retriever.py    # query embed → Chroma query → hits
└── __init__.py     # 导出 index_* / rag_stats / search_family_notes

backend/app/agent/
├── tools.py        # search_family_notes 工具定义 + execute_tool
├── loop.py         # Agent 循环（tool 执行后生成回答）
├── prompts.py      # 提示「答疑前优先 search_family_notes」
└── router.py       # /api/rag/* HTTP 接口

backend/app/
├── models.py       # LessonProgress.family_notes（MySQL）
└── curriculum/loader.py  # 读写 family_notes

frontend/src/views/ParentPanel.vue   # 编辑笔记、同步知识库
```

### 运行时数据流

```
【索引】家长保存笔记
  PATCH /api/lessons/{id}/notes
    → update_family_notes(db)          # MySQL
    → index_lesson_notes(db, id)       # Chroma reindex 该讲

【检索】孩子/家长聊天
  POST /api/chat/stream
    → LLM 调 search_family_notes
    → search_family_notes(db, query, lesson_id?)
    → embed_query + collection.query
    → tool message JSON → LLM 生成回答
```

**注意**：索引 **不是** 启动时全量加载到内存（与旧 MES 项目不同），而是 **按需写入 Chroma 持久化目录**；启动时只做 MySQL 种子数据，不自动 rebuild 向量库。

---

## 5. 双存储：MySQL + Chroma

```
┌─────────────────┐         reindex          ┌─────────────────┐
│  MySQL          │  ──────────────────────▶  │  Chroma         │
│  lesson_progress│   chunk + embed + upsert  │  family_notes   │
│  （原文）        │                           │  （检索索引）     │
└─────────────────┘                           └─────────────────┘
        ▲                                              │
        │ 家长编辑                                      │ 语义检索
        │                                              ▼
  ParentPanel.vue                              search_family_notes
```

| | MySQL | Chroma |
|--|-------|--------|
| 存什么 | 笔记原文 | 向量 + chunk 文本 + metadata |
| 谁写 | `update_family_notes` | `index_lesson_notes` / `index_all_notes` |
| 丢了怎么办 | 不可丢（source of truth） | 删目录后 `make rag-index` 可重建 |
| 技术 | SQLAlchemy ORM | `chromadb.PersistentClient` |

详见 [vector-db-learning.md](./vector-db-learning.md) §5 双存储说明。

---

## 6. Chunk 切分策略

**文件：** `backend/app/agent/rag/chunker.py`

### 什么是 Chunk

**Chunk（文本块）** 是 RAG 检索的 **最小单位**。整篇笔记太长，要拆成小块才能：

- 精准命中（问「借位」只返回含借位的那一段）
- 控制 token（只传 top-3 块给 LLM）

### 切分规则

| 参数 | 值 | 含义 |
|------|-----|------|
| `MAX_CHUNK_CHARS` | 320 | 单块最大字符数 |
| `MIN_CHUNK_CHARS` | 8 | 过短丢弃 |
| 策略 | 按 `\n` 分段 | 家长笔记通常是多条 bullet |

超长段落再按 320 字 **硬切**（无 overlap）。

### Chunk 数据结构

```python
{
    "id": "lesson-5-chunk-0",
    "text": "孩子减法还不太熟练，尤其是借位。",
    "metadata": {
        "lesson_id": 5,
        "title": "加与减",
        "topic": "计算",
        "chunk_index": 0,
    },
}
```

- `id` 稳定：`lesson-{讲次}-chunk-{序号}`，reindex 时 upsert 同 id
- `metadata.lesson_id` 用于检索时 **按讲次过滤**

### 为什么不用「每讲一块」

| 策略 | 优点 | 缺点 |
|------|------|------|
| **按段落切（本项目）** | 细粒度；问偏好/薄弱点可命中单段 | 极短笔记可能 0 chunk |
| 每讲一整块 | 实现简单 | 长笔记语义被「平均」，召回差 |
| 固定 500 字滑窗 | 通用 | 可能拦腰截断一句话 |

21 讲、每讲几条要点的规模，**按段落切 + 320 字上限** 足够。

---

## 7. 索引管线 indexer

**文件：** `backend/app/agent/rag/indexer.py`

### 核心 API

```python
from app.agent.rag import index_lesson_notes, index_all_notes, rag_stats

index_lesson_notes(db, lesson_id=5)   # 单讲：删旧 chunk → 切块 → embed → upsert
index_all_notes(db)                   # 全量：所有有内容的讲
rag_stats(db)                         # 统计：几讲有笔记、Chroma 共多少 chunk
```

### 单讲索引流程

```
1. SELECT lesson_progress WHERE lesson_id = ?
2. delete_lesson_chunks(lesson_id)     # Chroma where lesson_id = ?
3. chunk_family_note(...)              # 若笔记为空 → 只删不建
4. embed_texts([chunk.text, ...])      # fastembed 批量
5. upsert_chunks(chunks, vectors)      # Chroma upsert
```

### Embedding

**文件：** `backend/app/agent/rag/embedder.py`

- 模型：`BAAI/bge-small-zh-v1.5`（默认，可配置）
- 库：`fastembed` — **本地 CPU**，无需额外 API Key
- 首次运行下载模型权重；之后 `@lru_cache` 缓存模型实例

### Chroma 写入

**文件：** `backend/app/agent/rag/store.py`

```python
collection.upsert(
    ids=[c["id"] for c in chunks],
    documents=[c["text"] for c in chunks],
    embeddings=vectors,
    metadatas=[c["metadata"] for c in chunks],
)
```

Collection 配置：`metadata={"hnsw:space": "cosine"}`，与 bge 类模型常用 metric 一致。

持久化路径：`backend/data/chroma`（环境变量 `RAG_CHROMA_PATH`）。

---

## 8. 检索 search_family_notes

**文件：** `backend/app/agent/rag/retriever.py`

### 核心 API

```python
search_family_notes(db, query, *, lesson_id=None, top_k=None) -> dict
```

### 检索流程

```
1. rag_stats(db) — 若 chunks_in_store == 0，返回空 hits + 提示文案
2. embed_query(query) — 问题转向量
3. collection.query(
       query_embeddings=[query_vec],
       n_results=min(top_k, chunks_in_store),
       where={"lesson_id": n}  # 可选
   )
4. distance → score = 1 - distance（展示用，越大越相似）
```

### 返回格式

```json
{
  "ok": true,
  "query": "孩子减法哪里薄弱",
  "count": 2,
  "hits": [
    {
      "lesson_id": 5,
      "title": "加与减",
      "topic": "计算",
      "snippet": "孩子减法还不太熟练，尤其是借位。",
      "score": 0.8234
    }
  ]
}
```

知识库为空时：

```json
{
  "ok": true,
  "hits": [],
  "message": "知识库为空，请家长在「家庭笔记」填写内容后点击「同步知识库」"
}
```

### 检索模式说明

本项目 **仅向量检索**（Chroma + 本地 embedding），**没有** MES 项目那套「无 embedding 时关键词 fallback」。

| | gaosi-tutor | 旧 MES Demo |
|--|-------------|-------------|
| 向量库 | Chroma 持久化 | 内存 + 可选 API embedding |
| 无向量时 | 知识库为空，检索返回提示 | 关键词打分 |
| Embedding | fastembed 本地，默认开启 | 需配置 `EMBEDDING_MODEL` |

---

## 9. 配置与启用

### 依赖安装

```bash
make install   # requirements.txt 含 chromadb、fastembed
```

### 环境变量（`backend/config/.env`）

```env
# 可选，均有默认值
RAG_CHROMA_PATH=data/chroma
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_TOP_K=3
```

| 变量 | 默认 | 含义 |
|------|------|------|
| `RAG_CHROMA_PATH` | `data/chroma` | Chroma 持久化目录（相对 backend/） |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | fastembed 模型名 |
| `RAG_TOP_K` | `3` | 默认返回条数 |

### 首次启用步骤

```bash
make db-up && make init-db    # MySQL 就绪
make check                    # 应看到 RAG 模块 OK（chunks 可能为 0）
make start

# 家长在 /parent 填写笔记并保存，或：
make rag-index                # 全量同步已有笔记到 Chroma
make smoke-rag                # 冒烟：写测试笔记 → 索引 → 检索
```

### 更换 Embedding 模型

**必须** 全量 reindex，否则向量空间不一致：

```bash
rm -rf backend/data/chroma
make rag-index
```

### 常见问题

| 现象 | 可能原因 |
|------|---------|
| 检索永远空 | 未同步知识库；或笔记过短（< 8 字）未生成 chunk |
| 首次很慢 | fastembed 下载模型权重 |
| 改笔记后检索仍是旧的 | 保存笔记应自动 index；否则点「同步知识库」 |
| `check_env` RAG WARN | 未装 chromadb/fastembed，`make install` |

---

## 10. HTTP API 与家长面板

### API 一览

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/api/rag/stats` | chunk 数、有笔记讲数、chroma 路径 |
| POST | `/api/rag/index` | 全量 reindex |
| POST | `/api/rag/index/{lesson_id}` | 单讲 reindex |
| POST | `/api/rag/search` | 调试检索（不经过 LLM） |
| PATCH | `/api/lessons/{id}/notes` | 保存笔记 + **自动** `index_lesson_notes` |

`GET /api/health` 也包含 `rag` 状态与 `rag_chunks` 数量。

### 家长面板（`ParentPanel.vue`）

1. 选择讲次 → 编辑 **家庭笔记** → **保存**
   - 写 MySQL + 单讲 reindex + 刷新 stats
2. **同步知识库** → `POST /api/rag/index` 全量同步
3. 界面展示：`知识库：N 条片段（M 讲有笔记）`

---

## 11. 与 Function Calling 的配合

`search_family_notes` 在 `tools.py` 的 `TOOLS` 中注册：

```python
{
    "name": "search_family_notes",
    "description": "从家庭笔记知识库语义检索家长写的要点、薄弱点、陪练提醒。答疑或陪练建议前优先调用。",
    "parameters": {
        "query": "检索问题",
        "lesson_id": "可选，限定讲次 1～21"
    }
}
```

**执行：**

```python
def _tool_search_family_notes(db, query, lesson_id=None):
    return rag_search(db, query, lesson_id=lesson_id)
```

**Prompt 约束**（`prompts.py`）：

- 孩子模式：「答疑或给陪练建议前，优先调用 search_family_notes」
- 家长模式：「回答陪练策略前，优先 search_family_notes」

**LLM 决策示例：**

| 用户问题 | 预期工具 |
|---------|---------|
| 孩子哪里比较薄弱？ | `search_family_notes(query="薄弱点")` |
| 第 5 讲是什么内容？ | `get_lesson_context(lesson_id=5)` |
| 出一道题 | `generate_practice(lesson_id=5)` |
| 本讲出题有什么偏好？ | `search_family_notes(query="出题偏好", lesson_id=5)` |

RAG 负责 **Retrieve + tool message**；**Generate** 仍由 `loop.py` 完成。  
RAG 在本项目是 **「检索器 + 一种 Agent 工具」**，不是单独的新聊天接口。

---

## 12. 走一遍完整例子

**家长已写入第 5 讲笔记并保存（自动 index）。**

**孩子：** 「我减法老做错，小思你能帮帮我吗？」

### ① 当前 Chroma 中（节选）

```
lesson-5-chunk-0 → "孩子减法还不太熟练，尤其是借位。"
lesson-5-chunk-1 → "平时喜欢用小动物情境出题，多鼓励。"
```

### ② LLM 第 1 轮 → tool_calls

```json
{
  "name": "search_family_notes",
  "arguments": "{\"query\": \"减法薄弱 借位\", \"lesson_id\": 5}"
}
```

### ③ execute_tool → search_family_notes

```json
{
  "ok": true,
  "hits": [
    {
      "lesson_id": 5,
      "title": "加与减",
      "snippet": "孩子减法还不太熟练，尤其是借位。",
      "score": 0.85
    }
  ],
  "count": 1
}
```

### ④ LLM 第 2 轮 → 结合 tool 结果生成

```
没关系，减法借位是 many 小朋友都会遇到的……
（结合笔记建议，苏格拉底式引导，不直接给答案）
```

**注意**：LLM 可能在笔记之外「补充」通用建议。若要求严格只引用家庭笔记，需在 prompt 中加：「仅根据检索结果回答，不要编造孩子情况」。

---

## 13. 局限与改进方向

| 现状 | 改进方向 | 练习 |
|------|----------|------|
| 纯向量检索 | BM25（Best Matching 25）+ RRF 混合检索 | **[rag-hybrid-exercise.md](./rag-hybrid-exercise.md)** ← 推荐动手 |
| 无 Rerank | 交叉编码器 / API 精排 | **[rag-rerank.md](./rag-rerank.md)** ← 下一学习文档 |
| 无 Eval | Golden set + Recall@K | enterprise-rag-roadmap 阶段 6 |

| 局限 | 说明 | 改进方向 |
|------|------|----------|
| 仅向量检索 | 「借位」等精确词可能不如 BM25 | 混合检索 + RRF（见 [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md)） |
| 无 Rerank | top-K 直接给 LLM | cross-encoder 重排 top-3 |
| 无评测集 | 改 chunk 策略不知好坏 | 固定 10 问 + Recall@K |
| 单进程 Chroma | 多 worker 各写各的目录 | 换 Qdrant/pgvector 或共享卷 |
| LLM 可能幻觉 | 编造孩子情况 | prompt 约束 + 引用 snippet 原文 |
| 启动不自动 index | 新环境需手动同步 | 可选 startup hook `index_all_notes` |

个人项目当前规模（21 讲、数百 chunk）**不必急于换库**；优先 **评测 + 混合检索** 收益更高。

---

## 14. 自测与调试

### 只测 RAG 管线（不经过 LLM）

```bash
make smoke-rag
# 或指定讲次
cd backend && ./venv/bin/python scripts/smoke_rag.py --lesson 5
```

### 只测检索器

```bash
cd backend
./venv/bin/python -c "
from app.database import SessionLocal
from app.agent.rag import search_family_notes, rag_stats
db = SessionLocal()
print(rag_stats(db))
print(search_family_notes(db, '减法借位', lesson_id=5))
db.close()
"
```

### 测 HTTP 检索 API

```bash
curl -s http://127.0.0.1:8000/api/rag/stats | jq
curl -s -X POST http://127.0.0.1:8000/api/rag/search \
  -H 'Content-Type: application/json' \
  -d '{\"query\":\"孩子哪里薄弱\",\"lesson_id\":5}' | jq
```

### 测 Agent 工具链（需 API Key）

```bash
make smoke-llm
# 或在家长/孩子界面问：「根据家庭笔记，我这讲要注意什么？」
# 看 SSE tool_start 是否出现 search_family_notes
```

### 对照阅读

| 文档 | 内容 |
|------|------|
| 本文档 | RAG 业务、chunk、索引、检索、Agent 配合 |
| [vector-db-learning.md](./vector-db-learning.md) | 向量库概念、Chroma API、选型、动手实验 |
| [sqlalchemy-learning.md](./sqlalchemy-learning.md) | MySQL `lesson_progress` 读写 |
| [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) | 企业级 Hybrid + Rerank 对照 |
| `backend/app/agent/rag/` | 源码 |

---

## 附录：RAG vs 整段笔记塞 prompt

**不用 RAG（仅 prompt 注入）：**

```python
# build_system_prompt 把当前讲 family_notes 全文塞进 system
notes_block = f"【家庭笔记】\n{notes}"  # 当前讲可能很长
```

**用 RAG：**

```python
# Agent 按需检索，通常 1～3 段 × 几十字 ≈ 100～300 tokens
hits = search_family_notes(db, "借位哪里薄弱", lesson_id=5)
```

**两者配合：**

- prompt 仍带 **当前讲** 笔记摘要 → LLM 始终知道「本讲家庭背景」
- `search_family_notes` → 问法多样、跨讲、或要从长笔记里 **抠相关句** 时用

这就是 RAG 在本项目的价值：**按需取数，而非全量灌输**。

---

*文档版本：与 gaosi-tutor（Chroma + fastembed + search_family_notes）代码同步。*
