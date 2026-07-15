# RAG 动手练习：Rerank（精排）

> **难度**：中级～偏难  
> **预计时间**：6～10 小时（含 UI / tool 接入）  
> **前置**：已完成 [rag-hybrid-exercise.md](./rag-hybrid-exercise.md)，`make smoke-hybrid` 通过；已读 [rag-rerank.md](./rag-rerank.md) §1～§4  
> **对标**：公司项目 chat-test `rag/reranker/`（默认智谱 Rerank API）

---

## 术语


| 名称                | 一句话                                              |
| ----------------- | ------------------------------------------------ |
| **粗排**            | 从全集捞候选（向量 / BM25 / Hybrid），求高 Recall             |
| **精排 / Rerank**   | 只对候选再打「query↔文档」分，求高 Precision，通常只留 top-N        |
| **Cross-Encoder** | `(query, doc)` 成对进模型；比双塔更准、更慢                    |
| **Bi-Encoder**    | query / doc 各自 embedding——即现有 Chroma + fastembed |
| **fallback**      | 精排失败时退回粗排原序的前 top_n，不让整次检索挂掉                     |


---



## 1. 为什么要做这个练习？

Hybrid / RRF 解决「多路都捞到」；**仍可能**出现：


| 现象                          | Rerank 能帮什么               |
| --------------------------- | ------------------------- |
| Hybrid Top1 语义对，但不是最贴 query | 按交叉注意力重排                  |
| Top-K 全塞给 LLM，噪音占上下文        | 只留 `rerank_top_n`（常见 3～5） |
| 「竖式」问法误伤弱相关笔记               | Cross-Encoder 对词义更敏感      |


做完本练习，你将：

1. 实现本地 `rerank_hits`（Cross-Encoder）
2. 接到 `hybrid_search_family_notes`（放宽 → 精排 → 压紧）
3. 对比 API + 家长面板看到 **第四路 Rerank**
4. Agent tool 默认喂精排后 hits

---



## 2. 练习目标

实现后应能：

```bash
make smoke-rerank   # 全部 PASS
```

并可通过对比 API 看到 `rerank` 字段：

```bash
curl -s -X POST http://127.0.0.1:8000/api/rag/search/compare \
  -H 'Content-Type: application/json' \
  -d '{"query":"减法借位","lesson_id":5}' | jq '.rerank'
```

家长面板「检索实验」四列：向量 / BM25 / Hybrid / **Rerank**。

---



## 3. 已提供的脚手架


| 文件                            | 状态            | 说明                                               |
| ----------------------------- | ------------- | ------------------------------------------------ |
| `rag/reranker.py`             | **TODO 待你写**  | `_doc_text_from_hit`、`score_pairs`、`rerank_hits` |
| `scripts/smoke_rerank_rag.py` | ✅ 测试写好        | 实现通过后应全绿                                         |
| `Makefile` → `smoke-rerank`   | ✅ 已加          |                                                  |
| `rag/hybrid.py`               | ✅ 已有三路        | **你改**：接入 rerank、返回第四路                           |
| `schemas.py` / `router.py`    | ✅ 已有 compare  | **你改**：`RagCompareOut` 增加 `rerank`               |
| `ParentPanel.vue`             | ✅ 三列实验区       | **你改**：增加 Rerank 列                               |
| `tools.py`                    | ✅ hybrid tool | **你改**：默认回传精排 hits                               |


**故意不替你写完的**（练习必做，自己改）：

- `hybrid_search_family_notes` 里调用 `rerank_hits`
- Schema / 面板 / Agent tool

**可选进阶**（本练习不强制）：

- `RERANK_PROVIDER=zhipu|local|off`
- 智谱 Rerank API 对照

---



## 4. 环境准备

项目已有 `fastembed`。精排用其 **TextCrossEncoder**（推荐，与 embedding 栈一致）：

```bash
cd backend
# 一般 make install 已装好；确认：
./venv/bin/python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; print('ok')"
```

首次打分会**下载** Cross-Encoder 权重（可能较慢）。推荐小模型：

```text
Xenova/ms-marco-MiniLM-L-6-v2
```

中文效果一般；要更好中文可试 fastembed 支持的多语种 reranker（见官方 `list_supported_models()`），或：

```bash
# 可选方案：sentence-transformers
./venv/bin/pip install sentence-transformers
# CrossEncoder("BAAI/bge-reranker-base")
```

在 `backend/requirements.txt` 末尾有练习注释（无需新必装依赖时可不改）。

---



## 5. 练习步骤



### 练习 1：`_doc_text_from_hit` + 边界（约 20 分钟）

**文件**：`backend/app/agent/rag/reranker.py`

**任务**：从 hit 取出要送给 reranker 的文本；空输入直接返回。

```python
def _doc_text_from_hit(hit: dict) -> str:
    # 优先 snippet，其次 text；strip；过长可截断到 512～1024 字
    ...
```

**自测**：

```python
assert _doc_text_from_hit({"snippet": "借位"}) == "借位"
assert rerank_hits("", [{"snippet": "x"}]) == []
assert rerank_hits("借位", []) == []
```

---



### 练习 2：`score_pairs` + `rerank_hits`（约 2～3 小时）



#### 2a `score_pairs`

对 `(query, docs)` 成对打分，返回与 `docs` **等长**的 `list[float]`。

**推荐（fastembed）**：

```python
from fastembed.rerank.cross_encoder import TextCrossEncoder

_encoder = None

def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = TextCrossEncoder(model_name="Xenova/ms-marco-MiniLM-L-6-v2")
    return _encoder

def score_pairs(query: str, docs: list[str]) -> list[float]:
    if not docs:
        return []
    enc = _get_encoder()
    return list(enc.rerank(query, docs))
```



#### 2b `rerank_hits`

```python
def rerank_hits(
    query: str,
    hits: list[dict],
    *,
    top_n: int = 3,
    score_fn=None,   # 可选注入，便于单测；默认走 score_pairs
) -> list[dict]:
```

**步骤提示**：

1. `query` 空白或 `hits` 空 → `[]`
2. `docs = [_doc_text_from_hit(h) for h in hits]`
3. `scores = (score_fn or score_pairs)(query, docs)`
4. 按 score **降序**排序，取 `top_n`
5. 输出 hit：保留原 meta，`score` 改为精排分，`channel="rerank"`

**注意**：粗排分与精排分**不可相加**；以精排分为准排序即可。

**自测（可不下模型）**：

```python
hits = [
    {"chunk_id": "a", "snippet": "喜欢小动物出题"},
    {"chunk_id": "b", "snippet": "孩子减法借位还不熟练"},
]
out = rerank_hits(
    "借位",
    hits,
    top_n=1,
    score_fn=lambda q, docs: [0.1, 0.9],
)
assert out[0]["chunk_id"] == "b"
assert out[0]["channel"] == "rerank"
```

---



### 练习 3：接入 `hybrid_search_family_notes`（约 1～2 小时）

**文件**：`backend/app/agent/rag/hybrid.py`

**目标形态**：

```
hybrid（或更宽候选，如 top_k * 3 ～ 20）
        │
        ▼
rerank_hits(query, candidates, top_n=k)
        │
        ▼
返回增加 "rerank": {"hits": [...], "count": n}
```

**建议改法**：

```python
# 概念代码
from .reranker import rerank_hits

# 原先：hybrid_hits = rrf_merge(..., top_k=k)
# 改为：先放宽再精排retrieve_k
retrieve_k = max(k * 3, 10)
hybrid_hits = rrf_merge(vector_hits, bm25_hits, rrf_k=rrf_k, top_k=retrieve_k)

try:
    reranked = rerank_hits(query, hybrid_hits, top_n=k)
except Exception:
    # 失败降级：退回 hybrid 原序前 k 条（比返回空更稳）
    reranked = [
        {**h, "channel": "rerank", "score": h.get("score", 0)}
        for h in hybrid_hits[:k]
    ]

# return 里增加：
# "rerank": {"hits": reranked, "count": len(reranked)},
# 空知识库时 rerank 与三路一样返回 empty
```

**可选开关**（便于对比）：`with_rerank: bool = True`；面板/API 默认开，想看纯 hybrid 时可关。

---



### 练习 4：Schema + 对比 API（约 30～45 分钟）



#### 4a `schemas.py`

```python
class RagCompareOut(BaseModel):
    ok: bool = True
    query: str = ""
    vector: dict = {}
    bm25: dict = {}
    hybrid: dict = {}
    rerank: dict = {}   # 新增
```



#### 4b `router.py`

`/api/rag/search/compare` 已直接 `return` hybrid 出口；只要 hybrid 返回含 `rerank`，一般无需改逻辑（确认 response_model 已用 `RagCompareOut`）。

**自测**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/rag/search/compare \
  -H 'Content-Type: application/json' \
  -d '{"query":"借位","lesson_id":5}' | jq 'keys'
# 应含 "rerank"
```

---



### 练习 5：家长面板第四列（约 1 小时）

**文件**：`frontend/src/views/ParentPanel.vue`

**改动要点**：

1. 折叠标题改为「检索实验（向量 / BM25 / Hybrid / Rerank）」
2. `labColumns` 增加一列：

```js
{ key: 'rerank', label: 'Rerank', hits: r.rerank?.hits || [] },
```

1. loading / 成功文案改为「四路」；空库 `message` 也可看 `out.rerank?.message`
2. 首次点「对比检索」可能较慢（本机加载 Cross-Encoder）——保留 `:loading="labLoading"` 即可

---



### 练习 6：Agent tool 默认走精排（约 30～45 分钟）

**文件**：`backend/app/agent/tools.py` → `_tool_search_family_notes_hybrid`

当前只回传 `hybrid.hits`。改为优先 `rerank.hits`：

```python
rerank = out.get("rerank") or {}
hybrid = out.get("hybrid") or {}
hits = rerank.get("hits") or hybrid.get("hits") or []
result = {
    "ok": True,
    "query": out.get("query", query),
    "hits": hits,
    "count": len(hits),
    "channel": "rerank" if rerank.get("hits") else "hybrid",
}
```

调试仍用 compare API / 家长面板看全四路；**不要**把四路整包塞进 tool message。

---



### 练习 7（可选）：云 API / Provider 开关

对齐 chat-test：


| 环境变量                    | 含义                              |
| ----------------------- | ------------------------------- |
| `RERANK_PROVIDER=local` | 默认，本练习路径                        |
| `RERANK_PROVIDER=zhipu` | 调智谱 `/rerank`（需 Key）            |
| `RERANK_PROVIDER=off`   | 跳过精排，rerank 字段 = hybrid[:top_n] |


生产倾向 API 的原因：多 worker 本地加载大模型易把内存打爆（chat-test 因此 stub 掉本地 BCE）。

---



## 6. 验收标准


| #   | 检查项                         | 命令 / 方式                     |
| --- | --------------------------- | --------------------------- |
| 1   | 取文 + 空输入                    | `make smoke-rerank`         |
| 2   | `rerank_hits` 排序与 `channel` | 同上（含注入 `score_fn`）          |
| 3   | hybrid 出口含 `rerank`         | 同上                          |
| 4   | compare API 含 `rerank`      | curl / jq                   |
| 5   | 家长面板四列                      | 浏览器「检索实验」                   |
| 6   | tool 回传精排 hits              | Agent 问家庭笔记相关题，看 tool_trace |
| 7   | 能口述 Bi vs Cross、为何两阶段       | 面试自测                        |


**未实现时**：`make smoke-rerank` 退出码 `2`，提示 `NotImplementedError`。

---



## 7. 实验建议（加深理解）

同一讲次笔记，用家长面板对比：


| query     | 关注点                             |
| --------- | ------------------------------- |
| `借位`      | Hybrid Top1 vs Rerank Top1 是否更贴 |
| `竖式计算有问题` | 弱相关是否被压下去                       |
| `小动物`     | 精排是否仍保住相关 chunk                 |


记录：

- 粗排候选是否够宽？（`retrieve_k` 太小则精排几乎变不出花样）  
- 精排后 Precision@3 是否更好？（人工看即可）

---



## 8. 与公司项目对照


| gaosi-tutor 练习                 | chat-test 生产                     |
| ------------------------------ | -------------------------------- |
| fastembed TextCrossEncoder（本地） | 智谱 Rerank API（默认）                |
| 可选 sentence-transformers       | 阿里 gte-rerank / 本地 BCE（备用或 stub） |
| 手写 fallback → hybrid[:n]       | API 异常时有降级逻辑                     |
| 家长面板四路对比                       | 内网 search API + 日志               |
| 计量可后补 `rerank_ms`              | 统计 `rerank_tokens`               |


面试话术：

> 我在 Hybrid（向量 + BM25 + RRF）之上加了 Cross-Encoder 精排，把候选从十余条压到 top-3 再注入 LLM；个人项目用本地 fastembed 跑通管线，公司项目用智谱 API 控内存与成本。

---



## 9. 完成后可继续

- [ ] Eval：10～20 条黄金 query，算 Precision@3 / MRR → 见 [rag-eval.md](./rag-eval.md)
- [ ] `RERANK_PROVIDER` + 智谱对照，记延迟与 token  
- [ ] tool_trace 增加 `rerank_ms`  
- [ ] 阅读 [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) 阶段 3 选型决策树  

---



## 10. 相关文档

- [rag-rerank.md](./rag-rerank.md) — 精排概念与选型  
- [rag-hybrid-exercise.md](./rag-hybrid-exercise.md) — 本练习前置  
- [fastembed-learning.md](./fastembed-learning.md) — TextCrossEncoder 延伸  
- [agent-rag.md](./agent-rag.md) — 家庭笔记 RAG 全貌  
- chat-test `rag/reranker/zhipu_rerank_api.py` — 生产参考

---

*开始实现前：*`grep -n "NotImplementedError" backend/app/agent/rag/reranker.py`*；做完练习 2 就跑一次* `make smoke-rerank`*，再改 hybrid / 面板。*