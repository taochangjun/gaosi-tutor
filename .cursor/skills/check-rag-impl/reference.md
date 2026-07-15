# RAG 混合检索 · 函数实现规范

供 `check-rag-impl` skill 对照使用。与 `docs/rag-hybrid-exercise.md` 同步。

---

## tokenize_for_bm25

**文件**：`backend/app/agent/rag/bm25_index.py`

### 必过项

- [ ] 空字符串 / 仅空白 → 返回 `[]`
- [ ] 非空文本 → 返回非空 `list[str]`
- [ ] `"孩子减法借位"` 的结果中含 `"借"` 或 `"借位"`（字级或词级均可）
- [ ] 不抛异常

### 常见错误

| 问题 | 表现 |
|------|------|
| 忘记 strip / 去空白 | 空格被当成 token |
| `return text.split()` | 中文无空格，整句变 1 个 token，BM25 效果差 |
| 仍 `NotImplementedError` | smoke-hybrid 第 1 关 SKIP |

### 冒烟

`test_tokenize()` in `scripts/smoke_hybrid_rag.py`

---

## build_bm25_corpus

**文件**：`backend/app/agent/rag/bm25_index.py`

### 必过项

- [ ] 使用 `store.list_all_chunks()` 加载语料
- [ ] `records` 每项含 `id`、`text`、`metadata`（与 chunk 对齐）
- [ ] `tokenized[i]` 对应 `records[i]` 的 `text` 分词结果
- [ ] `BM25Okapi(tokenized)` 赋给 `corpus._bm25`
- [ ] `force_rebuild=True` 时忽略旧 `_corpus_cache` 并重建
- [ ] 写入 `_corpus_cache` 供后续检索复用
- [ ] 有 chunk 时 `corpus.is_built()` 为 True
- [ ] 空库：`records=[]`，`is_built()` 为 False（不崩溃）

### 常见错误

| 问题 | 表现 |
|------|------|
| 未 `pip install rank-bm25` | ImportError |
| records 与 tokenized 长度不一致 | 检索下标错位 |
| 未更新 `_corpus_cache` | 每次重建但 get 仍用旧库 |
| 空库仍 `BM25Okapi([[]])` | 可能异常或 is_built 误判 |

### 冒烟

`test_bm25_corpus()` — 需 Chroma 有数据（先 `make smoke-rag` 或家长同步笔记）

---

## get_bm25_corpus

**文件**：`backend/app/agent/rag/bm25_index.py`

### 必过项

- [ ] 缓存为空或未 built → 调用 `build_bm25_corpus(force_rebuild=True)`
- [ ] 返回 `BM25Corpus` 实例

### 常见错误

- `force_rebuild=False` 导致索引更新后仍用旧 BM25

---

## invalidate_bm25_cache

**文件**：`backend/app/agent/rag/bm25_index.py`

### 必过项

- [ ] 将 `_corpus_cache` 置为 `None`

### 集成（练习 6）

- [ ] `indexer.index_lesson_notes` / `index_all_notes` 写入 Chroma 成功后调用

---

## bm25_search

**文件**：`backend/app/agent/rag/bm25_index.py`

### 必过项

- [ ] 调用 `get_bm25_corpus()` 与 `tokenize_for_bm25(query)`
- [ ] `get_scores` 与 `records` 下标对齐
- [ ] 按分数降序取 `top_k`
- [ ] `lesson_id` 有值时过滤 `metadata.lesson_id`
- [ ] 每条 hit 含：`chunk_id`（或 id）、`lesson_id`、`title`、`topic`、`snippet`、`score`、`channel="bm25"`
- [ ] `score` 建议在 0～1（max 归一化即可）
- [ ] 无匹配时返回 `[]` 不抛错

### 常见错误

| 问题 | 表现 |
|------|------|
| 未过滤 lesson_id | 返回其他讲次 |
| 分数未归一化 | 与 vector score 不可比（hybrid 仅看排名则影响小） |
| 正分才返回 | BM25 全负时应有理处理 |
| q_tokens 为空仍 get_scores | 边界需处理 |

### 冒烟

- query `"借位"`, `lesson_id=5` → 命中含「借位」的 snippet
- query `"小动物"` → 命中第二段笔记

---

## rrf_merge

**文件**：`backend/app/agent/rag/hybrid.py`

### 必过项

- [ ] 排名从 **1** 开始（第一名 rank=1，不是 0）
- [ ] 贡献分：`1 / (rrf_k + rank)` 对每个榜单累加
- [ ] 用 `_hit_key(hit)` 合并同一条目
- [ ] 按 RRF 总分降序
- [ ] 返回最多 `top_k` 条
- [ ] 输出 hit 带 `channel="hybrid"`，`score` 为 RRF 分

### 常见错误

| 问题 | 表现 |
|------|------|
| rank 从 0 开始 | 分数偏大，排序可能仍对但不符合规范 |
| 用原始 vector/bm25 分数相加 | 不是 RRF |
| 未去重 | 同一 chunk 出现两次 |
| 空榜单崩溃 | 应返回 [] 或正确处理 |

### 冒烟（固定数据）

```text
vector: a=#1, b=#2
bm25:   b=#1, c=#2
→ hybrid 前三名应含 a,b,c 且 b 靠前
```

---

## _hit_key

**文件**：`backend/app/agent/rag/hybrid.py`

### 必过项

- [ ] 有 `chunk_id` → 用 `chunk_id`
- [ ] 否则 `f"{lesson_id}:{snippet[:80]}"`

---

## hybrid_search_family_notes

**文件**：`backend/app/agent/rag/hybrid.py`

### 必过项

- [ ] 空 query → `{"ok": False, "error": "检索问题不能为空"}`
- [ ] 空知识库 → 三路均为空 hits + message（**不要** NotImplementedError）
- [ ] 调用 `search_family_notes` 得 vector hits，补 `channel="vector"`
- [ ] 调用 `bm25_search` 得 bm25 hits
- [ ] `rrf_merge(vector_hits, bm25_hits, ...)` 得 hybrid hits
- [ ] 返回结构含 `ok`, `query`, `vector`, `bm25`, `hybrid` 各含 `hits` 与 `count`

### 常见错误

| 问题 | 表现 |
|------|------|
| 知识库为空仍 raise NotImplemented | 练习 5 前半已写，后半未写 |
| vector hit 无 chunk_id | RRF 去重靠 snippet，可能不稳定 |
| 只返回 hybrid 不返回分路 | 无法对比调试 |

### 冒烟

`test_hybrid_search(db)` — query `"减法哪里薄弱"`, lesson_id=5

---

## 推荐实现顺序

```
tokenize_for_bm25 → build_bm25_corpus → bm25_search → rrf_merge → hybrid_search_family_notes
```

每完成一个，用 skill 检查后再做下一个。
