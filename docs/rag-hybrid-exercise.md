# RAG 动手练习：混合检索（BM25 + 向量 + RRF）

> **难度**：中级  
> **预计时间**：4～8 小时  
> **前置**：已读懂 [agent-rag.md](./agent-rag.md)，跑通 `make smoke-rag`  
> **对标**：公司项目 chat-test 的 `ES Hybrid + RRF`（见 [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) 阶段 3）

---

## 术语

| 缩写 | 全称 | 一句话 |
|------|------|--------|
| **BM25** | **Best Matching 25** | 经典**关键词相关性**排序算法，属于 Okapi BM 系列第 25 版（Robertson / Walker 等，1990s）；按 query 与文档的**词频、文档长度**打分，适合「有共同词」的检索。Python 常用 [`rank_bm25`](https://github.com/dorianbrown/rank_bm25) 的 `BM25Okapi`。 |
| **RRF** | **Reciprocal Rank Fusion** | 多路检索结果的**排名融合**算法：按名次而非原始分数合并，公式见练习 4。 |

---

## 1. 为什么要做这个练习？

当前 gaosi-tutor 只有 **纯向量检索**（Chroma + cosine）：

| 用户问法 | 笔记原文 | 纯向量 |
|----------|----------|--------|
| 「借位哪里薄弱」 | 「尤其是**借位**」 | ✅ 常能命中 |
| 「减法不熟怎么办」 | 「**减法**还不太熟练」 | ✅ 语义相近 |
| 「竖式计算有问题」 | 只写了「借位」没写「竖式」 | ⚠️ 可能漏召回 |

**BM25（Best Matching 25，关键词检索）** 对「query 与原文有共同词」更敏感；**向量** 对「换说法」更敏感。  
**RRF（Reciprocal Rank Fusion）** 把两路排名合并，是企业 RAG 的常见做法（chat-test 用 ES 内置 RRF）。

做完本练习，你将理解：

1. 向量 vs 关键词各自擅长什么  
2. RRF 如何不依赖「统一分数尺度」做融合  
3. 如何设计 **对比 API** 调试检索质量  

---

## 2. 练习目标

实现后应能：

```bash
make smoke-hybrid   # 全部 PASS
```

并可通过（可选）HTTP 对比三路结果：

```bash
curl -s -X POST http://127.0.0.1:8000/api/rag/search/compare \
  -H 'Content-Type: application/json' \
  -d '{"query":"减法借位","lesson_id":5}' | jq
```

---

## 3. 已提供的脚手架

| 文件 | 状态 | 说明 |
|------|------|------|
| `rag/bm25_index.py` | **TODO 待你写** | 分词、语料构建、BM25 检索 |
| `rag/hybrid.py` | **TODO 待你写** | RRF 融合、混合检索入口 |
| `rag/store.py` | ✅ 已加 `list_all_chunks()` | 从 Chroma 拉全量语料 |
| `scripts/smoke_hybrid_rag.py` | ✅ 测试用例写好 | 实现通过后应全绿 |
| `retriever.py` | ✅ 不动 | 继续作为 vector 通道 |

**故意没帮你接好的**（进阶可自行做）：

- Agent tool `search_family_notes_hybrid`
- 家长面板「检索对比」UI
- `indexer` 写入后 `invalidate_bm25_cache()`

---

## 4. 环境准备

```bash
# 在 requirements.txt 取消注释后安装，或：
cd backend && ./venv/bin/pip install rank-bm25

# 可选进阶中文分词：
# ./venv/bin/pip install jieba
```

在 `backend/requirements.txt` 末尾有：

```
# rank-bm25>=0.2.2   # rag-hybrid-exercise 练习用，实现后取消注释
```

---

## 5. 练习步骤

### 练习 1：`tokenize_for_bm25`（约 30 分钟）

**文件**：`backend/app/agent/rag/bm25_index.py`

**任务**：把中文 query / 文档切成 token 列表。

**入门实现**（按字切）：

```python
def tokenize_for_bm25(text: str) -> list[str]:
    text = text.replace(" ", "").strip()
    return list(text) if text else []
```

**进阶**：用 `jieba.cut_for_search(text)` 得到词级 token。

**自测**：

```python
assert "借" in tokenize_for_bm25("孩子减法借位")
```

---

### 练习 2：`build_bm25_corpus`（约 1 小时）

**任务**：从 Chroma 构建内存 BM25 索引。

**提示**：

```python
from rank_bm25 import BM25Okapi
from .store import list_all_chunks

chunks = list_all_chunks()
records = [...]  # id, text, metadata
tokenized = [tokenize_for_bm25(c["text"]) for c in records]
corpus._bm25 = BM25Okapi(tokenized)
```

**注意**：

- 使用模块级 `_corpus_cache`，`force_rebuild=True` 时重建  
- 空库时 `records=[]`，`is_built()` 应为 False  

---

### 练习 3：`bm25_search`（约 1～2 小时）

**任务**：返回与向量检索 **结构兼容** 的 hits：

```python
{
    "chunk_id": "lesson-5-chunk-0",
    "lesson_id": 5,
    "title": "加与减",
    "topic": "计算",
    "snippet": "孩子减法还不太熟练，尤其是借位。",
    "score": 0.82,          # 建议 max 归一化到 0~1
    "channel": "bm25",
}
```

**提示**：

```python
scores = corpus._bm25.get_scores(q_tokens)
# 与 records 下标对齐，降序取 top_k
# lesson_id 有值时：if meta["lesson_id"] != lesson_id: continue
```

**调试 query**：

- `"借位"` → 应强命中含「借位」的 chunk  
- `"小动物"` → 应命中第二段笔记  

---

### 练习 4：`rrf_merge`（约 1～2 小时）

**文件**：`backend/app/agent/rag/hybrid.py`

**公式**：

```
对每个榜单（vector、bm25）：
  第 rank 名（rank 从 1 开始）贡献：1 / (rrf_k + rank)

同一 chunk（用 chunk_id 去重）的 RRF 分 = 各榜贡献之和
```

**示例**（rrf_k=60）：

| chunk | vector 排名 | bm25 排名 | RRF 分 |
|-------|-------------|-----------|--------|
| b | 2 | 1 | 1/62 + 1/61 ≈ 0.032 |
| a | 1 | — | 1/61 ≈ 0.016 |
| c | — | 2 | 1/62 ≈ 0.016 |

→ 排序：**b > a ≈ c**

**实现要点**：

- 用 `_hit_key(hit)` 去重  
- 输出 hit 的 `score` 填 `rrf_score`，`channel` 标 `"hybrid"`  

---

### 练习 5：`hybrid_search_family_notes`（约 1 小时）

**任务**：串起 vector + bm25 + rrf，返回：

```json
{
  "ok": true,
  "query": "减法哪里薄弱",
  "vector": { "hits": [...], "count": 3 },
  "bm25": { "hits": [...], "count": 3 },
  "hybrid": { "hits": [...], "count": 3 }
}
```

**提示**：

```python
vec_out = search_family_notes(db, query, lesson_id=lesson_id, top_k=v_k)
vector_hits = vec_out["hits"]
# 给 vector hit 补上 chunk_id（可从 snippet+lesson 推断，或改 retriever 返回 id）

bm25_hits = bm25_search(query, lesson_id=lesson_id, top_k=b_k)
hybrid_hits = rrf_merge(vector_hits, bm25_hits, rrf_k=rrf_k, top_k=k)
```

**可选增强**：改 `retriever.py` 让 vector hits 带 `chunk_id`（从 Chroma id 返回）。

---

### 练习 6（可选）：索引失效 + HTTP API

#### 6a 缓存失效

在 `indexer.py` 的 `index_lesson_notes` / `index_all_notes` 成功写入 Chroma 后：

```python
from .bm25_index import invalidate_bm25_cache
invalidate_bm25_cache()
```

#### 6b Schema（`schemas.py`）

```python
class RagCompareOut(BaseModel):
    ok: bool = True
    query: str = ""
    vector: dict = {}
    bm25: dict = {}
    hybrid: dict = {}
```

#### 6c 路由（`router.py`）

```python
@router.post("/rag/search/compare", response_model=RagCompareOut)
def rag_compare_api(data: RagSearchIn, db: Session = Depends(get_db)):
    from .rag.hybrid import hybrid_search_family_notes
    out = hybrid_search_family_notes(db, data.query, lesson_id=data.lesson_id)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("error"))
    return out
```

---

## 5.1 用 Skill 检查你的实现

项目内 skill：**`check-rag-impl`**（`.cursor/skills/check-rag-impl/`）

在 Cursor 对话中说：

> 帮我检查 `tokenize_for_bm25` 的实现

或命令行：

```bash
cd backend && ./venv/bin/python ../.cursor/skills/check-rag-impl/scripts/check_function.py tokenize_for_bm25
```

可检查函数：`tokenize_for_bm25`、`build_bm25_corpus`、`bm25_search`、`rrf_merge`、`hybrid_search_family_notes` 等（见 skill 内 reference.md）。

---

## 6. 验收标准

| # | 检查项 | 命令 |
|---|--------|------|
| 1 | 分词非空 | `make smoke-hybrid` 第 1 关 |
| 2 | BM25 语料构建 | 同上 |
| 3 | 「借位」BM25 命中 | 同上 |
| 4 | RRF 合并顺序合理 | 同上 |
| 5 | 三路 hybrid 均有 hits | 同上 |
| 6 | 能口述 vector vs bm25 vs hybrid 差异 | 面试自测 |

**未实现时**：`make smoke-hybrid` 退出码 `2`，提示 `NotImplementedError`。

---

## 7. 实验建议（加深理解）

准备两条 note，故意制造「向量强 / BM25 强」差异：

| 讲次 | 笔记 | 实验 query |
|------|------|------------|
| 5 | 「孩子**减法**还不太熟练，尤其是**借位**」 | `竖式不对`（向量可能中，BM25 可能弱） |
| 6 | 「**竖式**练习要多练」 | `竖式不对`（BM25 应强） |

对比 `/api/rag/search` vs `/api/rag/search/compare`，记录：

- 哪路 recall 更好？  
- hybrid 是否取了两路并集？  

---

## 8. 与公司项目对照

| gaosi-tutor 练习 | chat-test 生产 |
|------------------|----------------|
| Chroma 向量 | ES kNN |
| rank_bm25 | ES BM25 + IK 分词 |
| `rrf_merge()` 手写 | `ApproxRetrievalStrategy(hybrid=True, rrf=...)` |
| 内存 BM25 语料 | ES 倒排索引持久化 |

面试话术：

> 我在个人项目里用 Chroma + rank_bm25 手写 RRF，理解 ES Hybrid 在做什么；公司项目用 ES 一体化完成向量+关键词+融合。

---

## 9. 完成后可继续

- [ ] Agent 增加 tool：`search_family_notes_hybrid`，prompt 里对比何时用 hybrid  
- [x] 家长面板增加「检索实验」折叠区，展示三路 hits  
- [ ] 阶段 3 下一关：**Rerank**（对 hybrid top-10 再精排 top-3）→ 见 [rag-rerank-exercise.md](./rag-rerank-exercise.md)（概念：[rag-rerank.md](./rag-rerank.md)）  
- [ ] Eval：10 条 query 标注「期望命中 chunk」，算 Recall@3  

---

## 10. 相关文档

- [agent-rag.md](./agent-rag.md) — 现有 RAG 管线  
- [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) — 企业级阶段 3  
- [chroma-learning.md](./chroma-learning.md) — Chroma API  
- chat-test `rag/es.py` — Hybrid + RRF 生产参考  

---

*开始实现前：先 `grep -r "NotImplementedError" backend/app/agent/rag/`，做完一个练习就跑一次 `make smoke-hybrid`。*
