# Chroma 学习文档（基于 gaosi-tutor 项目）

> 面向第一次接触 Chroma 的开发者。文中 API 示例均来自本仓库 `backend/app/agent/rag/store.py` 与 `retriever.py`。  
> 配套：[vector-db-learning.md](./vector-db-learning.md)（向量/RAG 总览）、[agent-rag.md](./agent-rag.md)（业务管线）、[sqlalchemy-learning.md](./sqlalchemy-learning.md)（MySQL 原文）。

## 目录

1. [Chroma 是什么](#1-chroma-是什么)
2. [核心概念速览](#2-核心概念速览)
3. [在本项目中的位置](#3-在本项目中的位置)
4. [安装与配置](#4-安装与配置)
5. [客户端模式](#5-客户端模式)
6. [Collection：逻辑上的「表」](#6-collection逻辑上的表)
7. [写入：add / upsert / update](#7-写入add--upsert--update)
8. [删除：delete 与 metadata 过滤](#8-删除delete-与-metadata-过滤)
9. [检索：query 详解](#9-检索query-详解)
10. [距离度量：cosine / L2 / IP](#10-距离度量cosine--l2--ip)
11. [HNSW 与 ANN（Chroma 如何变快）](#11-hnsw-与-annchroma-如何变快)
12. [持久化与目录结构](#12-持久化与目录结构)
13. [与 Embedding 的配合](#13-与-embedding-的配合)
14. [常见陷阱与最佳实践](#14-常见陷阱与最佳实践)
15. [动手实验](#15-动手实验)
16. [与其他向量库对比](#16-与其他向量库对比)
17. [本仓库文件索引](#17-本仓库文件索引)
18. [延伸阅读](#18-延伸阅读)

---

## 1. Chroma 是什么

**Chroma** 是一个开源的 **向量数据库（Vector Database）**，用 Python 即可嵌入应用，特别适合 RAG、语义搜索。

| 特点 | 说明 |
|------|------|
| **嵌入式** | `pip install chromadb`，无需单独起服务（PersistentClient） |
| **持久化** | 向量落本地目录，重启不丢 |
| **Collection** | 类似「表」，存 id + embedding + document + metadata |
| **ANN 检索** | 内置 HNSW，百万级向量仍可毫秒级 query |
| **metadata 过滤** | 检索前按 `lesson_id` 等字段缩小范围 |

在本项目中，Chroma **只存家庭笔记的向量索引**；原文在 MySQL `lesson_progress.family_notes`。

---

## 2. 核心概念速览

```
Client（客户端）
  └── Collection（集合，如 family_notes）
        ├── id          唯一键，如 lesson-5-chunk-0
        ├── embedding   float[] 向量（fastembed 算出）
        ├── document    原文 chunk 文本（检索时直接返回 snippet）
        └── metadata    业务字段，如 lesson_id, title, topic
```

| 概念 | 一句话 |
|------|--------|
| **Client** | 连接 Chroma 的入口（内存 / 本地文件 / 远程 Server） |
| **Collection** | 一组向量的命名空间；本项目只有一个 `family_notes` |
| **Embedding** | 文本对应的浮点向量；Chroma **不**自动算，需你先 embed 再写入 |
| **query** | 给 query 向量，返回最近的 K 条 |
| **where** | metadata 过滤条件，如 `{"lesson_id": 5}` |
| **upsert** | 有则更新、无则插入（reindex 时常用） |

---

## 3. 在本项目中的位置

```
indexer.py                    retriever.py
    │                             │
    ├─ embed_texts()              ├─ embed_query()
    │                             │
    └──────────► store.py ◄────────┘
                    │
            PersistentClient
                    │
            backend/data/chroma/   ← 磁盘
```

**store.py 封装的四个对外操作：**

| 函数 | Chroma API | 场景 |
|------|------------|------|
| `upsert_chunks` | `collection.upsert` | 索引笔记 |
| `delete_lesson_chunks` | `collection.delete(where=...)` | reindex 前清讲次 |
| `count_chunks` | `collection.count` | stats / health |
| （在 retriever） | `collection.query` | Agent 检索 |

数据流：

```
家长保存笔记 → MySQL
            → index_lesson_notes()
            → upsert_chunks() → Chroma

孩子提问 → search_family_notes()
        → collection.query() → hits[]
```

---

## 4. 安装与配置

### 4.1 依赖

```txt
# backend/requirements.txt
chromadb>=0.5.23
```

```bash
make install
```

### 4.2 环境变量（`backend/config/.env`）

```env
RAG_CHROMA_PATH=data/chroma
```

| 变量 | 默认 | 含义 |
|------|------|------|
| `RAG_CHROMA_PATH` | `data/chroma` | PersistentClient 数据目录（相对 `backend/`） |

解析逻辑见 `store.get_chroma_path()`：相对路径会拼到 `backend/data/chroma`。

### 4.3 关闭遥测

```python
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
```

Chroma 默认可能上报匿名使用数据；本项目在 `store.py` 开头关闭。

---

## 5. 客户端模式

Chroma 提供三种常用 Client，**本项目用 PersistentClient**。

| Client | 代码 | 数据存哪 | 适用 |
|--------|------|----------|------|
| **EphemeralClient** | `chromadb.EphemeralClient()` | 内存 | 单元测试、临时实验 |
| **PersistentClient** | `chromadb.PersistentClient(path="...")` | 本地目录 | ✅ gaosi-tutor |
| **HttpClient** | `chromadb.HttpClient(host=...)` | 远程 Chroma Server | 多进程共享、生产 |

### 5.1 本项目：PersistentClient + 单例

```python
@lru_cache()
def _get_client():
    return chromadb.PersistentClient(path=str(get_chroma_path()))
```

- `@lru_cache`：进程内只建一个 Client，避免重复打开 SQLite
- 重启 FastAPI 后数据仍在 `data/chroma/`
- **不适合** 多 worker 同时写同一目录（会锁冲突）→ 生产换 HttpClient + Server 或 Qdrant

### 5.2 最小可运行示例（独立于本项目）

```python
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"  # 关闭遥测，避免部分环境下的告警

import chromadb

client = chromadb.PersistentClient(path="./my_chroma")
col = client.get_or_create_collection("demo")

col.upsert(
    ids=["a"],
    documents=["孩子减法还不太熟练"],
    embeddings=[[0.1, 0.2, 0.3]],  # 占位向量；真实项目用 fastembed
    metadatas=[{"lesson_id": 5}],
)

result = col.query(
    query_embeddings=[[0.1, 0.2, 0.3]],  # 与写入相同 → distance 应为 0
    n_results=1,
    include=["documents", "metadatas", "distances"],  # 要什么字段须显式 include
)
print(result)
```

**预期输出解读：**

```python
{
  'ids': [['a']],
  'documents': [['孩子减法还不太熟练']],
  'metadatas': [[{'lesson_id': 5}]],
  'distances': [[0.0]],   # 0 表示 query 向量与库内向量完全相同
  'embeddings': None,     # 未 include 则不返回
}
```

**关于 `Failed to send telemetry event ...` 告警：**

- 来自 Chroma 内置遥测与 `posthog` 等依赖的版本不兼容
- **不影响** upsert / query 功能，你的结果已证明查询成功
- 设 `ANONYMIZED_TELEMETRY=False` 通常可消除；本项目 `store.py` 已默认设置

---

## 6. Collection：逻辑上的「表」

### 6.1 创建 / 获取

```python
COLLECTION_NAME = "family_notes"

def get_collection() -> Collection:
    return _get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
```

| 参数 | 含义 |
|------|------|
| `name` | 集合名，全局唯一（在该 Client 下） |
| `metadata` | 集合级配置；`hnsw:space` 指定距离度量 |

**一个项目一类知识 = 一个 Collection** 是常见做法。若以后要加「错题本」「课本摘要」，可新建 `mistake_notes` 等集合。

### 6.2 每条记录的四元组

本项目 `upsert_chunks` 写入：

```python
collection.upsert(
    ids=[c["id"] for c in chunks],           # lesson-5-chunk-0
    documents=[c["text"] for c in chunks],   # 原文，query 时当 snippet 返回
    embeddings=vectors,                       # fastembed 输出
    metadatas=[c["metadata"] for c in chunks], # lesson_id, title, topic, ...
)
```

为什么 **document 和 embedding 都存**？

- embedding：用于相似度计算
- document：检索命中后直接把原文给 LLM，不必再查 MySQL

---

## 7. 写入：add / upsert / update

| 方法 | 行为 | 本项目 |
|------|------|--------|
| `add` | 仅插入；id 重复会报错 | 未用 |
| `upsert` | id 存在则覆盖 | ✅ `upsert_chunks` |
| `update` | 更新已有 id 的部分字段 | 未用 |

### 7.1 upsert 与 reindex

家庭笔记修改后：

```python
delete_lesson_chunks(lesson_id)   # 删掉该讲全部旧 chunk
# ... 重新 chunk + embed ...
upsert_chunks(chunks, vectors)    # 同 id 写入新向量
```

chunk id 规则：`lesson-{讲次}-chunk-{序号}`，同一讲 reindex 时序号从 0 重新编号，**先删后写** 避免旧段落残留。

### 7.2 批量写入

`upsert` 接受列表，一次可写多条。本项目按讲次批量；全量 `index_all_notes` 循环每讲调用。

Chroma 内部会做 HNSW 索引更新；数据量小（<1000）时几乎无感。

---

## 8. 删除：delete 与 metadata 过滤

```python
def delete_lesson_chunks(lesson_id: int) -> None:
    collection = get_collection()
    try:
        collection.delete(where={"lesson_id": lesson_id})
    except Exception:
        pass
```

| 场景 | 操作 |
|------|------|
| 家长清空某讲笔记 | `delete` 后不 `upsert` |
| 单讲 reindex | 先 `delete` 再 `upsert` |
| 全量索引后清理 | 对「MySQL 已无笔记」的讲次 `delete` |

**metadata 类型注意：** Chroma 对 metadata 值类型有要求（str / int / float / bool）。本项目 `lesson_id` 用 **int**，与 `where={"lesson_id": 5}` 一致。

按 id 删除（本项目未用）：

```python
collection.delete(ids=["lesson-5-chunk-0"])
```

清空整个 collection：

```python
client.delete_collection("family_notes")
# 再 get_or_create_collection 重建
```

---

## 9. 检索：query 详解

`retriever.search_family_notes` 核心：

```python
collection = get_collection()
where = {"lesson_id": lesson_id} if lesson_id else None
query_vec = embed_query(query)

result = collection.query(
    query_embeddings=[query_vec],
    n_results=min(k, stats["chunks_in_store"]),
    where=where,
    include=["documents", "metadatas", "distances"],
)
```

### 9.1 参数说明

| 参数 | 含义 |
|------|------|
| `query_embeddings` | 查询向量列表；支持一次多个 query，返回二维结果 |
| `n_results` | Top-K，不超过 collection 总数 |
| `where` | metadata 过滤；`None` 表示搜全库 |
| `include` | 返回哪些字段；默认可能不含 document，需显式指定 |

### 9.2 返回结构

```python
{
  "ids": [["lesson-5-chunk-0", ...]],
  "documents": [["孩子减法还不太熟练...", ...]],
  "metadatas": [[{"lesson_id": 5, "title": "加与减", ...}, ...]],
  "distances": [[0.18, 0.42, ...]],   # cosine distance，越小越相似
}
```

外层列表对应每个 query；本项目每次只查 1 条 query，故取 `[0]`：

```python
for doc, meta, dist in zip(docs[0], metas[0], dists[0]):
    score = round(max(0.0, 1.0 - float(dist)), 4)
```

### 9.3 where 过滤示例

```python
# 只搜第 5 讲
where={"lesson_id": 5}

# 多条件（Chroma 语法因版本而异，查阅官方文档）
where={"$and": [{"lesson_id": 5}, {"topic": "计算"}]}
```

过滤在 ANN 前后如何执行属于实现细节；工程上记住：**带 lesson_id 可缩小搜索空间、提高准确率**。

### 9.4 query_texts 备选写法

Chroma 也支持传入原文由内置 embedding 函数计算向量：

```python
collection.query(query_texts=["借位"], n_results=3)
```

本项目 **不用** 这种方式，因为 embedding 由 **fastembed** 在 `embedder.py` 统一完成，保证与索引阶段同一模型。

---

## 10. 距离度量：cosine / L2 / IP

创建 Collection 时指定：

```python
metadata={"hnsw:space": "cosine"}
```

| 度量 | Chroma 配置值 | 含义 | 适用 |
|------|---------------|------|------|
| **余弦距离** | `cosine` | 向量夹角；对长度不敏感 | ✅ bge 等语义模型 |
| **欧氏距离** | `l2` | 空间直线距离 | 部分图像向量 |
| **内积** | `ip` | 越大越相似（常配合归一化向量） | 特定训练方式 |

**规则：**

- 建库时的 `hnsw:space` 须与 embedding 模型训练/评估方式一致
- 更换 metric 需 **删 collection 重建**，不能原地改
- `distances` 返回的是 **distance** 不是 similarity；本项目用 `1 - dist` 转成 score 展示

---

## 11. HNSW 与 ANN（Chroma 如何变快）

暴力检索：query 与每条向量算距离 → O(N)。

**HNSW（Hierarchical Navigable Small World）**：多层图结构，检索时自上而下「跳跃」逼近最近邻 → 约 O(log N)。

你需要知道的结论：

- Chroma 默认用 HNSW 做 **近似** 最近邻，极少数情况会漏掉最优条
- 家庭笔记规模（<500 向量）即使用暴力也够快；HNSW 是为扩展预留
- 调 HNSW 参数（`M`、`ef_construction`）属于进阶优化，本项目用默认即可

---

## 12. 持久化与目录结构

### 12.1 数据目录

默认：`backend/data/chroma/`

```bash
ls backend/data/chroma/
# 通常可见 chroma.sqlite3 及若干二进制/索引文件（随 chromadb 版本变化）
```

### 12.2 备份与迁移

| 操作 | 做法 |
|------|------|
| **备份** | 复制整个 `data/chroma` 目录（服务停写时最稳） |
| **清空重建** | `rm -rf backend/data/chroma` → `make rag-index` |
| **换机器** | 复制目录 + 相同 `chromadb` 版本 + 相同 embedding 模型 |

### 12.3 与 MySQL 的关系

| | MySQL | Chroma |
|--|-------|--------|
| 角色 | 原文 source of truth | 检索索引副本 |
| 丢了能否恢复 | 不可丢 | 可从 MySQL reindex 重建 |
| 修改笔记后 | UPDATE family_notes | 必须 reindex 该讲 |

---

## 13. 与 Embedding 的配合

Chroma **不负责** 把文本变向量（除非你自己配 `embedding_function`）。

本项目分工：

```
embedder.py          store.py / retriever.py
    │                        │
embed_texts(chunks)    upsert(embeddings=...)
embed_query(query)     query(query_embeddings=...)
```

**铁律：**

1. 索引与查询 **同一模型**（`RAG_EMBEDDING_MODEL`）
2. 换模型 → 删 `data/chroma` → 全量 `index_all_notes`
3. 向量维度必须与模型输出一致，否则 upsert/query 报错

---

## 14. 常见陷阱与最佳实践

### ✅ 推荐

| 实践 | 原因 |
|------|------|
| PersistentClient + 单例 Client | 避免重复打开库 |
| 稳定 id + upsert | 笔记更新可预测覆盖 |
| metadata 存 `lesson_id` | 按讲次过滤 |
| reindex 前先 delete 该讲 | 避免旧 chunk 残留 |
| MySQL 存原文 | Chroma 可随时重建 |

### ❌ 避免

| 陷阱 | 后果 |
|------|------|
| 把 Chroma 当唯一数据源 | 笔记无法编辑恢复 |
| 换 embedding 不删库 | 检索结果随机 |
| 多 uvicorn worker 共写同一目录 | 锁错误、数据损坏 |
| id 重复用 `add` 而非 `upsert` | 插入失败 |
| 忽略 `where` 的 metadata 类型 | 过滤不生效 |
| 用 Chroma 内置 embed 与 fastembed 混用 | 向量空间不一致 |

### 故障排查

| 现象 | 检查 |
|------|------|
| 检索永远空 | `collection.count()`、`make rag-index` |
| `chunks_in_store` 有值但查不到 | embedding 是否换过；query 是否与索引同模型 |
| 删讲次后仍能搜到旧内容 | 是否执行了 `delete_lesson_chunks` |
| 启动报 chromadb 错 | `make install`、Python 版本兼容 |

---

## 15. 动手实验

### 实验 1：冒烟全链路

```bash
make smoke-rag
```

### 实验 2：Python 里直接操作 Collection

```bash
cd backend
./venv/bin/python
```

```python
from app.database import SessionLocal
from app.agent.rag.store import get_collection, count_chunks
from app.agent.rag.indexer import rag_stats

db = SessionLocal()
print(rag_stats(db))
print("count:", count_chunks())

col = get_collection()
print(col.peek(limit=3))   # 看前几条（API 名以当前 chromadb 版本为准）
db.close()
```

### 实验 3：观察 query 返回的 distance

```python
from app.agent.rag.retriever import search_family_notes
from app.database import SessionLocal

db = SessionLocal()
for q in ["借位", "减法薄弱", "小动物出题"]:
    r = search_family_notes(db, q, lesson_id=5)
    print(q, "->", [(h["score"], h["snippet"][:30]) for h in r["hits"]])
db.close()
```

### 实验 4：清空并重建

```bash
rm -rf backend/data/chroma
make rag-index
curl -s http://127.0.0.1:8000/api/rag/stats | python3 -m json.tool
```

### 实验 5：EphemeralClient 对比（理解 Persistent）

```python
import chromadb
c = chromadb.EphemeralClient()
col = c.create_collection("test")
col.add(ids=["1"], embeddings=[[1,0,0]], documents=["hello"])
print(col.count())  # 1
# 进程结束 → 数据消失；PersistentClient 则保留在磁盘
```

---

## 16. 与其他向量库对比

| | Chroma | Qdrant | pgvector |
|--|--------|--------|----------|
| 部署 | pip 嵌入 / 可选 Server | 独立服务 | PostgreSQL 扩展 |
| 本项目 | ✅ 使用中 | 规模变大可考虑 | 已有 PG 时可选 |
| metadata 过滤 | 支持 | 很强 | SQL + 向量 |
| 混合检索 BM25 | 弱 | 可插件 | 需另做 |
| 多进程写 | Persistent 不适合 | 适合 | 适合 |

gaosi-tutor 当前 **<500 chunk**，Chroma PersistentClient 最合适。详见 [vector-db-learning.md §10](./vector-db-learning.md#10-向量库选型指南)。

---

## 17. 本仓库文件索引

| 文件 | Chroma 相关内容 |
|------|----------------|
| `backend/app/agent/rag/store.py` | Client、Collection、upsert、delete、count |
| `backend/app/agent/rag/retriever.py` | `collection.query` |
| `backend/app/agent/rag/indexer.py` | 调用 upsert/delete 的索引管线 |
| `backend/app/settings.py` | `RAG_CHROMA_PATH` |
| `backend/scripts/smoke_rag.py` | 端到端验证 |
| `backend/scripts/check_env.py` | RAG/Chroma 是否可用 |
| `backend/requirements.txt` | `chromadb>=0.5.23` |

### HTTP 调试接口

| 接口 | 作用 |
|------|------|
| `GET /api/rag/stats` | `chunks_in_store`、`chroma_path` |
| `POST /api/rag/index` | 全量写入 Chroma |
| `POST /api/rag/search` | 直接 query，不经过 LLM |

---

## 18. 延伸阅读

- [Chroma 官方文档](https://docs.trychroma.com/)
- [Chroma Cookbook](https://cookbook.chromadb.dev/) — 配方与常见模式
- 本项目 [agent-rag.md](./agent-rag.md) — 从业务看 Index/Retrieve
- 本项目 [vector-db-learning.md](./vector-db-learning.md) — Embedding、选型、RAG 全链路
- [HNSW 论文科普](https://www.pinecone.io/learn/series/faiss/hnsw/) — 理解 ANN（英文）

---

*文档版本：与 gaosi-tutor（chromadb ≥0.5.23、PersistentClient、family_notes collection、cosine）代码同步。*
