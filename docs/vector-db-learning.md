# 向量数据库学习文档（基于 gaosi-tutor 项目）

> 面向第一次接触向量检索 / RAG 的开发者。文中示例均来自本仓库真实代码，可直接对照阅读。  
> 配套文档：[chroma-learning.md](./chroma-learning.md)（Chroma 专项）、[agent-rag.md](./agent-rag.md)（RAG 流程）、[sqlalchemy-learning.md](./sqlalchemy-learning.md)（MySQL 原文存储）、[enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md)（生产级对比）。

## 目录

1. [向量数据库是什么](#1-向量数据库是什么)
2. [核心概念速览](#2-核心概念速览)
3. [本项目的 RAG 分层](#3-本项目的-rag-分层)
4. [Indexing：从 MySQL 到 Chroma](#4-indexing从-mysql-到-chroma)
5. [Embedding：文本如何变成向量](#5-embedding文本如何变成向量)
6. [Chunk：为什么要切块](#6-chunk为什么要切块)
7. [Retrieval：如何查最相似的片段](#7-retrieval如何查最相似的片段)
8. [Chroma 在本项目中的用法](#8-chroma-在本项目中的用法)
9. [ANN 索引原理（HNSW 简介）](#9-ann-索引原理hnsw-简介)
10. [向量库选型指南](#10-向量库选型指南)
11. [常见陷阱与最佳实践](#11-常见陷阱与最佳实践)
12. [动手实验](#12-动手实验)
13. [进阶路线](#13-进阶路线)
14. [本仓库文件索引](#14-本仓库文件索引)
15. [延伸阅读](#15-延伸阅读)

---

## 1. 向量数据库是什么

**向量数据库（Vector Database）** 专门存储和检索 **高维浮点向量**，解决一个问题：

> 给定一句用户提问，从海量文本片段里找出 **语义最相近** 的几段。

传统 SQL 擅长 `WHERE lesson_id = 5` 这种精确匹配；向量库擅长「孩子减法哪里薄弱」这类 **语义相似** 查询。

在本项目中，职责分工是：

| 存储 | 存什么 | 技术 |
|------|--------|------|
| **MySQL** | 家庭笔记原文、对话、练习记录 | SQLAlchemy ORM |
| **Chroma** | 笔记切块后的 embedding 向量 | 本地持久化向量库 |
| **fastembed** | 把文本算成向量（不是 DB，是模型） | 本地 Embedding |

向量库 **不替代** MySQL：原文仍以 MySQL 为 source of truth，Chroma 是检索用的 **索引副本**。

---

## 2. 核心概念速览

```
┌──────────────┐   embed    ┌──────────────┐   upsert   ┌──────────────┐
│  原始文本     │ ─────────▶ │  float[]     │ ─────────▶ │  Chroma      │
│  family_notes│            │  512 维向量   │            │  collection  │
└──────────────┘            └──────────────┘            └──────┬───────┘
                                                                │
用户提问 ──▶ embed ──▶ query 向量 ──▶ ANN 搜索 top-K ──▶ 命中 snippet
                                                                │
                                                                ▼
                                                    Agent prompt / tool 结果
```

| 概念 | 一句话解释 |
|------|-----------|
| **Embedding** | 把文本映射为固定长度向量，语义相近的文本向量距离更近 |
| **Chunk** | 长文档切成短片段再分别 embed，避免整篇塞不进模型、检索粒度太粗 |
| **Collection** | Chroma 里的「逻辑表」，本项目叫 `family_notes` |
| **Metadata** | 附在向量上的业务字段，如 `lesson_id`，用于过滤 |
| **Top-K** | 返回相似度最高的 K 条，本项目默认 `rag_top_k=3` |
| **Cosine distance** | 衡量两向量夹角距离，越小越相似；本项目 Chroma 配置为 cosine |
| **ANN** | 近似最近邻算法，百万向量也能毫秒级返回（牺牲极少精度换速度） |
| **Upsert** | 有则更新、无则插入；笔记修改后重新索引同一 `id` |

---

## 3. 本项目的 RAG 分层

RAG = **Retrieval-Augmented Generation**（检索增强生成）。向量库只负责 **Retrieval** 这一步。

```
backend/app/agent/rag/
├── chunker.py      ← 按段落切块（≤320 字）
├── embedder.py     ← fastembed 本地算向量
├── store.py        ← Chroma 读写封装
├── indexer.py      ← MySQL 笔记 → 切块 → embed → upsert
└── retriever.py    ← 用户 query → embed → query → 返回 hits

调用链：
  家长改笔记 → PATCH /api/lessons/{id}/notes
            → index_lesson_notes(db, id)
            → delete_lesson_chunks + upsert_chunks

  孩子提问   → Agent 调 search_family_notes tool
            → search_family_notes(db, query, lesson_id=?)
            → Chroma collection.query(...)
```

与 Agent 的衔接见 `backend/app/agent/tools.py` 中的 `_tool_search_family_notes`。

---

## 4. Indexing：从 MySQL 到 Chroma

**文件：** `backend/app/agent/rag/indexer.py`

索引管线四步：

```
1. SELECT lesson_progress.family_notes   （MySQL 原文）
2. chunk_family_note(...)                （切块 + metadata）
3. embed_texts([...])                    （批量算向量）
4. upsert_chunks(chunks, vectors)        （写入 Chroma）
```

单讲更新时先 **删后写**，保证旧 chunk 不残留：

```python
delete_lesson_chunks(lesson_id)   # where lesson_id = ?
vectors = embed_texts([c["text"] for c in chunks])
upsert_chunks(chunks, vectors)
```

全量索引 `index_all_notes` 会遍历所有有内容的讲次，并清理 DB 里已清空的讲的 Chroma 残留。

### 何时需要 reindex？

| 事件 | 动作 |
|------|------|
| 家长修改家庭笔记 | 自动 `index_lesson_notes`（PATCH notes API） |
| 点击「同步知识库」 | `POST /api/rag/index` 全量 |
| 更换 embedding 模型 | **必须** 删 `data/chroma` 目录 + 全量 reindex |
| 修改切块策略 | 建议全量 reindex |

---

## 5. Embedding：文本如何变成向量

**文件：** `backend/app/agent/rag/embedder.py`  
**配置：** `settings.rag_embedding_model = "BAAI/bge-small-zh-v1.5"`

```python
model = TextEmbedding(model_name=settings.rag_embedding_model)
vectors = [vec.tolist() for vec in model.embed(texts)]
```

要点：

- **同一模型** 必须用于索引和查询，否则向量空间不一致，检索无意义。
- **bge-small-zh-v1.5** 是中文小模型，512 维左右，本地 CPU 可跑，无需 API Key。
- 首次运行会下载模型权重，略慢；之后 `@lru_cache` 缓存模型实例。

### 本地 vs 云端 Embedding

| | 本地（本项目） | 云端（如 DashScope、OpenAI） |
|--|---------------|------------------------------|
| 成本 | 免费 | 按 token 计费 |
| 隐私 | 数据不出机器 | 文本发到 API |
| 质量 | 小模型够用 | 大模型通常更好 |
| 运维 | 占磁盘、占 CPU | 要 API Key、限流、重试 |

家庭笔记场景，本地 embed 是合理默认；企业文档库见 `enterprise-rag-roadmap.md` 的 DashScope 路线。

---

## 6. Chunk：为什么要切块

**文件：** `backend/app/agent/rag/chunker.py`

| 参数 | 值 | 含义 |
|------|-----|------|
| `MAX_CHUNK_CHARS` | 320 | 单 chunk 最大字符数 |
| `MIN_CHUNK_CHARS` | 8 | 过短段落丢弃 |
| 切分策略 | 按 `\n` 段落 | 家长笔记通常是多条 bullet |

每个 chunk 结构：

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

**为什么不整篇笔记一个向量？**

- 笔记长了以后，一个向量只能表示「整篇平均语义」，细粒度问题（如只问「借位」）召回差。
- LLM context 有限，检索应返回 **最相关的一两段**，不是全文。

---

## 7. Retrieval：如何查最相似的片段

**文件：** `backend/app/agent/rag/retriever.py`

```python
query_vec = embed_query(query)
result = collection.query(
    query_embeddings=[query_vec],
    n_results=min(k, stats["chunks_in_store"]),
    where={"lesson_id": lesson_id} if lesson_id else None,
    include=["documents", "metadatas", "distances"],
)
```

流程：

1. 用户问题 embed 成 query 向量
2. Chroma 在 collection 内做 ANN，找 cosine 距离最小的 K 条
3. 可选 `where` 先按 `lesson_id` 过滤（只搜某一讲）
4. 距离转 score：`score = 1.0 - distance`（展示用，越大越相似）

返回给 Agent 的 hit 示例：

```json
{
  "lesson_id": 5,
  "title": "加与减",
  "snippet": "孩子减法还不太熟练，尤其是借位。",
  "score": 0.82
}
```

---

## 8. Chroma 在本项目中的用法

> **Chroma 专项详解见 [chroma-learning.md](./chroma-learning.md)**（Client、Collection、upsert/query/delete、持久化、实验）。本节为速览。

**文件：** `backend/app/agent/rag/store.py`

### 8.1 客户端模式

```python
chromadb.PersistentClient(path=str(get_chroma_path()))
```

- **PersistentClient**：向量存本地目录 `backend/data/chroma`（可配置 `RAG_CHROMA_PATH`）
- 进程重启后数据仍在，适合 Demo / 家庭项目
- 无需单独起 Docker 服务

### 8.2 Collection 配置

```python
get_or_create_collection(
    name="family_notes",
    metadata={"hnsw:space": "cosine"},
)
```

- `hnsw:space: cosine` 与 bge 类模型常用 metric 一致
- 一个 collection = 一类知识（本项目只有家庭笔记）

### 8.3 核心 API

| 操作 | 方法 | 本项目场景 |
|------|------|-----------|
| 写入/更新 | `collection.upsert(ids, documents, embeddings, metadatas)` | 索引笔记 |
| 删除 | `collection.delete(where={"lesson_id": n})` | 笔记清空或重索引前 |
| 查询 | `collection.query(query_embeddings, n_results, where)` | Agent 检索 |
| 统计 | `collection.count()` | health / rag_stats |

---

## 9. ANN 索引原理（HNSW 简介）

暴力检索：query 与 **每一条** 向量算距离 → O(N)，N 大了就慢。

**HNSW（Hierarchical Navigable Small World）** 是 Chroma 等库默认的 ANN 结构：

- 把向量组织成多层图，检索时从顶层「跳跃」逼近最近邻
- 复杂度约 O(log N)，百万级仍可达毫秒～十毫秒级
- 结果是 **近似** 的：极少数情况下会漏掉最优条，但工程上可接受

你需要知道的结论：

- 向量库快，靠的是 **索引结构（HNSW/IVF 等）**，不是魔法
- metadata 过滤过多 + 数据量小，有时直接暴力扫描也够快
- 换 distance metric（cosine ↔ L2）要重建索引，且须与 embedding 训练方式匹配

---

## 10. 向量库选型指南

### 10.1 五维决策

| 维度 | 问什么 |
|------|--------|
| **数据量** | chunk 总数：<1万 / 1万～100万 / >100万？ |
| **QPS** | 同时多少检索请求？家庭项目个位数 vs 生产上千 |
| **检索类型** | 纯语义 vs 必须 **向量+关键词混合** |
| **运维** | 能否接受独立服务、K8s、备份监控？ |
| **现有栈** | 是否已有 PostgreSQL / Elasticsearch？ |

### 10.2 产品对照（2025 常见选择）

| 产品 | 类型 | 适合场景 | 本项目关系 |
|------|------|----------|-----------|
| **Chroma** | 嵌入式 / 本地文件 | Demo、个人项目、<100万向量 | ✅ 当前使用 |
| **pgvector** | PG 扩展 | 已有 PostgreSQL，想少组件 | 可迁移，SQL+向量一体 |
| **Qdrant** | 独立服务 / 云 | 中等规模、metadata 过滤强 | 生产常见备选 |
| **Milvus** | 独立服务 | 大规模、分布式 | 企业 chat-test 曾双写 |
| **Weaviate** | 独立服务 | 内置模块多、GraphQL API | 备选 |
| **Elasticsearch kNN** | 搜索栈扩展 | **混合检索** BM25+向量 | enterprise-rag-roadmap |
| **Pinecone / Zilliz Cloud** | 全托管 | 零运维、快速验证 | 按量付费 |

### 10.3 按场景推荐

```
数据 < 10 万 chunk + 单进程 Python     → Chroma（你现在）
已有 PostgreSQL + 向量规模中等         → pgvector
要 BM25 + 向量 + 复杂权限过滤           → Elasticsearch
百万～亿级 + 高 QPS                    → Milvus / Qdrant
不想运维                               → Pinecone 等托管
全离线 / 隐私                          → Chroma + 本地 embed（你现在）
```

### 10.4 gaosi-tutor 要不要换？

**现阶段不需要。** 21 讲家庭笔记，chunk 总量通常 < 500，Chroma 本地持久化最简单。

值得优先 investment 的（比换库收益大）：

1. **评测集**：10 个固定问题测 recall
2. **混合检索**：关键词「借位」兜底纯向量漏召
3. **Rerank**：向量 top-10 → cross-encoder 重排 top-3

---

## 11. 常见陷阱与最佳实践

### ✅ 推荐

| 实践 | 原因 |
|------|------|
| MySQL 存原文，Chroma 存索引 | 原文可编辑、可审计；向量可随时重建 |
| 改笔记后立刻 reindex 该讲 | 避免 Agent 读到过期语义 |
| 索引与查询用同一 embedding 模型 | 向量空间必须一致 |
| metadata 带 `lesson_id` | 缩小搜索空间，提高准确率 |
| 用 `smoke_rag.py` 回归 | 改 chunk/embed 配置后快速验证 |

### ❌ 避免

| 陷阱 | 后果 |
|------|------|
| 换 embedding 模型不 reindex | 检索结果随机化 |
| 把 Chroma 当唯一数据源 | 笔记丢了无法恢复 |
| chunk 过大（整篇一条） | 细粒度问题召回差 |
| 忽略 cosine vs L2 | 距离含义错乱，score 不可比 |
| 生产用 PersistentClient 多机写 | 嵌入式库不适合多实例并发写 |

### 距离与 score

本项目 Chroma 返回 **cosine distance** ∈ [0, 2]（实现细节可能略有差异），越小越相似。  
展示时用 `score = 1 - distance` 仅为直观，**不要跨不同库/不同 metric 比较绝对值**。

---

## 12. 动手实验

### 实验 1：走通索引与检索（5 分钟）

```bash
cd gaosi-tutor
make install          # 含 chromadb + fastembed
make db-up && make init-db
cd backend && ./venv/bin/python scripts/smoke_rag.py --lesson 5
```

观察输出：写入笔记 → 切块数 → 索引 chunks → 检索 score。

### 实验 2：调 top_k 看召回变化

在 `config/.env` 中设置：

```env
RAG_TOP_K=5
```

重启服务，同一问题对比返回 hit 数量和内容。

### 实验 3：验证 metadata 过滤

```bash
# 在 Python shell 中
from app.database import SessionLocal
from app.agent.rag.retriever import search_family_notes

db = SessionLocal()
# 不限讲次
print(search_family_notes(db, "减法借位"))
# 限定第 5 讲
print(search_family_notes(db, "减法借位", lesson_id=5))
db.close()
```

对比两次 `hits` 的 `lesson_id` 分布。

### 实验 4：理解 reindex 必要性

1. 记录 `backend/data/chroma` 目录大小
2. 修改 `RAG_EMBEDDING_MODEL` 为另一个模型（如 `BAAI/bge-base-zh-v1.5`）
3. 不删 chroma 直接检索 → 结果异常
4. 删除 `data/chroma`，`POST /api/rag/index` 全量索引 → 恢复正常

### 实验 5：API 层调试

```bash
make start
curl -s http://127.0.0.1:8000/api/rag/stats | jq
curl -s -X POST http://127.0.0.1:8000/api/rag/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"孩子哪里薄弱","lesson_id":5}' | jq
```

### 实验 6（可选）：与 pgvector 最小对比

同一批 chunk 写入 pgvector，对比：

- 安装步骤数
- 过滤语法
- 单次 query 延迟（本项目数据量下可能差异不大）

目的：**建立选型直觉**，不是必须迁移。

---

## 13. 进阶路线

按投入产出比排序：

| 阶段 | 内容 | 参考 |
|------|------|------|
| **L1 会用** | Index / Query / metadata / top-K | 本文 + `smoke_rag.py` |
| **L2 调优** | chunk 大小、top_k、评测集 | 改 `chunker.py` |
| **L3 混合检索** | BM25 + 向量 + RRF 融合 | `enterprise-rag-roadmap.md` § Hybrid |
| **L4 Rerank** | 向量粗排 + cross-encoder 精排 | 智谱 / Cohere Rerank API |
| **L5 生产化** | 版本化索引、alias 切换、token 计费 | chat-test ES Store 设计 |

个人项目到 **L2** 足够；简历级 RAG 故事需覆盖 **L3～L5** 中至少两点。

---

## 14. 本仓库文件索引

| 文件 | 职责 |
|------|------|
| `backend/app/agent/rag/store.py` | Chroma PersistentClient、upsert/query/delete |
| `backend/app/agent/rag/embedder.py` | fastembed 批量/单条 embed |
| `backend/app/agent/rag/chunker.py` | 家庭笔记切块 |
| `backend/app/agent/rag/indexer.py` | MySQL → Chroma 索引管线 |
| `backend/app/agent/rag/retriever.py` | 语义检索入口 |
| `backend/app/agent/tools.py` | Agent tool `search_family_notes` |
| `backend/app/agent/router.py` | `/api/rag/*` HTTP 接口 |
| `backend/app/settings.py` | `rag_chroma_path`、`rag_embedding_model`、`rag_top_k` |
| `backend/scripts/smoke_rag.py` | RAG 冒烟测试 |
| `backend/scripts/check_env.py` | 检查 Chroma / RAG 是否可用 |
| `docs/agent-rag.md` | RAG 概念与 Agent 配合 |
| `docs/enterprise-rag-roadmap.md` | 企业 ES + Hybrid + Rerank 对照 |

### 相关配置项（`config/.env`）

| 变量 | 默认 | 含义 |
|------|------|------|
| `RAG_CHROMA_PATH` | `data/chroma` | Chroma 持久化目录 |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-small-zh-v1.5` | fastembed 模型名 |
| `RAG_TOP_K` | `3` | 默认返回条数 |

---

## 15. 延伸阅读

- [Chroma 官方文档](https://docs.trychroma.com/)
- [fastembed GitHub](https://github.com/qdrant/fastembed)
- 本项目 [fastembed-learning.md](./fastembed-learning.md) — 本地 Embedding 详解
- [MTEB 中文 Embedding 排行榜](https://huggingface.co/spaces/mteb/leaderboard) — 换模型前参考
- [Qdrant 向量数据库教程](https://qdrant.tech/documentation/) — 对比学习 API 设计
- 本项目 [chroma-learning.md](./chroma-learning.md) — Chroma Client / Collection / query 详解
- 本项目 [agent-rag.md](./agent-rag.md) — RAG 在 Agent 中的完整故事
- 本项目 [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) — 从 Chroma 到 ES Hybrid 的演进路径

---

*文档版本：与 gaosi-tutor（Chroma + fastembed + bge-small-zh-v1.5）代码同步。*
