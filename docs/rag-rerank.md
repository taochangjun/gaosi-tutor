# RAG 精排详解：Rerank

> **定位**：理解「粗排召回 → 精排重排序」在 RAG 中的作用，对照 chat-test 生产实践，规划 gaosi-tutor 接入路径。  
> **前置**：已完成 [rag-hybrid-exercise.md](./rag-hybrid-exercise.md)（向量 + BM25 + RRF），能用家长面板「检索实验」对比三路结果。  
> **对标**：[enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) 阶段 3 · Rerank；公司项目 `chat-test/rag/reranker/`。

---

## 术语

| 名称 | 含义 |
|------|------|
| **Rerank / 精排** | 对一组候选文档再打一次「与 query 相关」的分，按新分数排序，通常只保留 top-N 给 LLM。 |
| **粗排（First-stage retrieval）** | 先从全集里捞出候选：向量、BM25、Hybrid/RRF 等。目标是 **高 Recall**（别漏掉）。 |
| **精排（Second-stage ranking）** | 只在候选集上工作（常见 10～50 条）。目标是 **高 Precision**（Top 几真正相关）。 |
| **Cross-Encoder（交叉编码器）** | 把 `query + document` **拼在一起**过一遍模型，输出相关性分数；比双塔更准、更慢。 |
| **Bi-Encoder（双塔）** | query / 文档各自 embedding，用向量相似度——即我们现在的 Chroma + fastembed。 |
| **top_k / top_n / rerank_top_n** | 粗排取 k 条 → 精排后只留 n 条给生成（chat-test：`top_n` 粗排，`rerank_top_n` 精排）。 |

---

## 1. 为什么需要 Rerank？

Hybrid / RRF 解决的是「**多路都捞到**」；Rerank 解决的是「**捞到之后谁排最前**」。

```
全部笔记 chunk（可能几十～上千）
        │
        ▼
┌───────────────────┐
│ 粗排 First-stage  │  向量 / BM25 / Hybrid
│ 目标：Recall      │  → 候选 10～50 条
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 精排 Rerank       │  Cross-Encoder / Rerank API
│ 目标：Precision   │  → 最终 top 3～5 条注入 LLM
└─────────┬─────────┘
          │
          ▼
     Augment + Generate
```

### 典型痛点（Hybrid 之后仍可能出现）

| 现象 | 原因 | Rerank 能帮什么 |
|------|------|----------------|
| Hybrid Top1 语义对，但不是最贴 query | RRF 只看**排名**，不真正理解「query↔句」相关性 | 精排按跨塔打分重排 |
| Top-K 全塞给 LLM，噪音占上下文 | 粗排偏宽容，假阳性多 | 只留 rerank_top_n |
| 「竖式」问法误伤弱相关笔记 | 向量近邻有时会过宽 | Cross-Encoder 对词义更敏感 |

**一句话**：粗排负责「别漏」，精排负责「Top 几真准」。

---

## 2. Bi-Encoder vs Cross-Encoder

这是理解 Rerank 的核心对比：

| | **Bi-Encoder（现在的向量检索）** | **Cross-Encoder（精排）** |
|--|--------------------------------|---------------------------|
| 输入 | query、doc **各自**编码成向量 | `(query, doc)` **成对**送入模型 |
| 交互 | 向量点积 / cosine，文档之间无交互 | 注意力可直接看 query 与 doc 词对齐 |
| 速度 | 快，可预先算好文档向量、ANN 检索 | 慢，每个候选都要再跑一遍模型 |
| 规模 | 可检索百万级语料 | 通常只精排候选 10～100 条 |
| gaosi-tutor | `embedder.py` + Chroma | **未接入**（本阶段要学） |
| chat-test | DashScope Embedding + ES | 智谱 Rerank API（默认） |

```
Bi-Encoder（粗排）:
  encode(query) ──┐
                  ├──► 相似度 / ANN
  encode(docs)  ──┘     （docs 可提前算好）

Cross-Encoder（精排）:
  for each doc in candidates:
      score = model( [CLS] query [SEP] doc [SEP] )
  sort by score
```

---

## 3. 与当前管线的位置

### gaosi-tutor 现状

```
search_family_notes          → 纯向量 top-K
bm25_search                  → BM25 top-K
hybrid_search_family_notes   → RRF 融合
        │
        ▼
Agent tool / 家长面板「检索实验」
        │
        ✗ 尚无 Rerank
```

### 目标形态

```
hybrid（或更宽的候选，如 top_k=10～20）
        │
        ▼
rerank(query, candidates) → top_n=3～5
        │
        ▼
注入 Agent tool / prompt
```

### chat-test 生产（对照）

| 项 | 实现 |
|----|------|
| 触发 | `rerank=True` 或环境变量 `NEED_RERANK` |
| 默认实现 | `rag/reranker/zhipu_rerank_api.py` → `POST /api/paas/v4/rerank` |
| 备用 | 阿里云 `gte-rerank-v2`（代码有，主路径未接） |
| 本地模型 | BCE reranker（已 stub：8 worker × 约 2GB 内存过重） |
| 成本 | 统计 `rerank_tokens`，与 embedding / LLM 一并返回 |
| 参数 | 粗排 `top_n`（默认约 20）→ 精排 `rerank_top_n`（默认约 5～10） |

**设计取舍（简历可讲）**：生产环境倾向 **Rerank API**，避免多 worker 本地加载大模型把内存打爆——chat-test 明确因此禁用本地 BCE。

---

## 4. 常见 Rerank 方案选型

```
要不要 Rerank？
  │
  ├─ 候选已经很少（≤3）且 bad case 少 → 可先跳过
  │
  └─ Top-K 噪音多 / Precision 不够
        │
        ├─ 有 API Key、要最好效果、控内存
        │     → 智谱 / 阿里 / Cohere Rerank API   ← chat-test
        │
        ├─ 要离线、可接受首次下载 + GPU/CPU
        │     → 本地 Cross-Encoder
        │       如 BAAI/bge-reranker-base、BCE、fastembed TextCrossEncoder
        │
        └─ 纯实验、不想接外网
              → 手写「LLM-as-reranker」（把候选贴给 LLM 打分）—贵且慢，仅作对照
```

| 方案 | 优点 | 缺点 | 本项目建议 |
|------|------|------|------------|
| 云 API（智谱等） | 准、省本机内存、与公司栈一致 | 依赖 Key、有延迟与费用 | 进阶对照实验 |
| 本地 Cross-Encoder | 数据不出域、可复现 | 内存/首次下载 | 学习首选（笔记本可跑小模型） |
| LLM 打分 | 实现快 | 贵、慢、不稳定 | 只做概念验证 |

---

## 5. 接口契约（建议在 gaosi-tutor 落地时遵守）

### 函数签名（示意）

```python
def rerank_hits(
    query: str,
    hits: list[dict],
    *,
    top_n: int = 3,
) -> list[dict]:
    """
    输入：粗排 hits（含 snippet / chunk_id / score / ...）
    输出：按精排分数重排后的 hits，长度 ≤ top_n
         建议字段：保留原 meta，score 改为 rerank 分，channel="rerank"
    """
```

### 拼进 hybrid 的位置

```python
# hybrid_search_family_notes 末尾（概念）
hybrid_hits = rrf_merge(vector_hits, bm25_hits, top_k=max(k * 3, 10))  # 先放宽
reranked = rerank_hits(query, hybrid_hits, top_n=k)                     # 再压紧
return {
    "ok": True,
    "query": query,
    "vector": {...},
    "bm25": {...},
    "hybrid": {"hits": hybrid_hits, "count": ...},
    "rerank": {"hits": reranked, "count": len(reranked)},  # 调试对比
}
```

Agent tool **只把 `rerank` 一路（或精排后 hybrid）的 hits** 回传给 LLM，与当前对 hybrid 的裁剪策略一致，避免塞三路 debug 结构。

### HTTP 扩展（可选）

| 接口 | 用途 |
|------|------|
| `POST /api/rag/search/compare` | 已有 vector / bm25 / hybrid |
| 增加 `rerank` 字段 | 或 `?with_rerank=1`，家长面板实验区多一列 |

---

## 6. 分数与阈值要注意的坑

1. **粗排分和精排分不可直接相加**  
   向量 cosine、BM25 raw、RRF 分、rerank relevance_score 尺度都不同。Rerank 后以精排分为准排序即可。

2. **候选太少时精排收益有限**  
   Hybrid 只出 2 条再 rerank，几乎变不出花样。常见：`retrieve_k=10～20` → `rerank_n=3`。

3. **空候选 / 空 query**  
   直接返回 `[]`，不要调 API。

4. **文档文本用什么字段**  
   传 `snippet`（或 `text`）给 reranker；过长可截断（如 512～1024 字）。

5. **延迟**  
   本地模型首次加载慢；API 有网络 RTT。UI「检索实验」要有 loading；Agent 路径可记 `ms` 到 tool_trace。

6. **失败降级**  
   Rerank API 挂了时：退回 hybrid 原序（chat-test 遇异常返回空再走别逻辑——你自己实现时更稳妥的是 **fallback 到 hybrid hits[:top_n]**）。

---

## 7. chat-test 调用形态（简历口述用）

```python
# 概念对应，非直接可跑
passages = [doc.page_content for doc in candidates]
scores_and_indices, token_cost = await zhipu.get_rerank_score(
    query, passages, top_n=rerank_top_n
)
# 按 relevance_score 重排 Document，再 reduce_results 截断塞进 RAG_TEMPLATE
```

面试可讲三点：

1. **两阶段**：ES hybrid 粗排 → 智谱 rerank 精排  
2. **为何不用本地 BCE**：多 worker 内存成本  
3. **成本归因**：`rerank_tokens` 单独计量  

---

## 8. 与 RRF 的关系（别搞混）

| | RRF | Rerank |
|--|-----|--------|
| 输入 | 多路**已排序列表** | 一路候选 + query |
| 依据 | **排名**倒数融合 | **内容相关性**模型分 |
| 要不要理解文本 | 不要 | 要 |
| 典型位置 | 合并 vector ∪ bm25 | 合并之后再压 top-N |

常见流水线：

```
vector ──┐
         ├──► RRF ──► candidates ──► Rerank ──► final top-N
bm25  ──┘
```

不是「RRF 或 Rerank 二选一」，而是 **先融合、再精排**。

---

## 9. 建议实践路线（gaosi-tutor）

不必一次写完，可按周推进：

### 阶段 A：搞懂再动手（阅读）

- [x] 读本文 §1～§4  
- [ ] 家长面板用同一 query 看 hybrid Top3，手工判断「若只能留 1 条该留谁」——这就是精排在做的事  

### 阶段 B：最小实现（本地）

建议目录：

```
backend/app/agent/rag/
  reranker.py          # rerank_hits()
```

依赖可选其一：

```bash
# 方案 1：sentence-transformers CrossEncoder
pip install sentence-transformers

# 方案 2：fastembed TextCrossEncoder（与现有 embedding 生态更近）
# 见 fastembed 文档 TextCrossEncoder
```

验收：

```bash
# 建议后续加
make smoke-rerank
```

同 query：hybrid top5 vs rerank top3，人工看 Precision 是否更好。

### 阶段 C：接入产品

- [ ] `hybrid_search_family_notes` 增加 `rerank` 字段或开关  
- [ ] Agent tool `search_family_notes_hybrid` 默认走精排后 hits  
- [ ] 家长面板「检索实验」增加 **Rerank** 一列  
- [ ] 空结果 / API 失败时的 fallback  

### 阶段 D：对齐公司栈（可选）

- [ ] 环境变量 `RERANK_PROVIDER=zhipu|local|off`  
- [ ] 智谱 Rerank API 对照实验，记 token 与延迟  

---

## 10. Eval 怎么衡量「Rerank 有没有用」

不必上完整 RAGAS，先做轻量：

| 指标 | 做法 |
|------|------|
| **Precision@3** | 标注 query → 期望相关的 chunk_id；看精排后 top3 命中几个 |
| **MRR** | 第一个相关结果的排名倒数 |
| **人工 A/B** | 同一问：hybrid vs rerank，家长面板并排点赞 |

黄金集可从练习笔记里攒 10～20 条 query（「借位」「小动物」「竖式」各几条）。

---

## 11. 简历包装（一句话）

> 在 Hybrid（向量 + BM25 + RRF）粗排之上增加 Cross-Encoder / Rerank API 精排，将候选从 10～20 压到 top-3 注入 LLM；生产环境倾向 API 以避免多进程本地模型内存膨胀，并单独计量 rerank token。

对照项目：

| | gaosi-tutor | chat-test |
|--|-------------|-----------|
| 粗排 | Chroma + BM25 + 手写 RRF | ES Hybrid + RRF |
| 精排 | 待接入（本路线） | 智谱 Rerank API |
| 调试 | 家长面板三路对比 | 内网 search API + 日志 |

---

## 12. 相关文档与代码

| 资源 | 内容 |
|------|------|
| [rag-hybrid-exercise.md](./rag-hybrid-exercise.md) | 混合检索练习（Rerank 的前置） |
| [agent-rag.md](./agent-rag.md) | 家庭笔记 RAG 全貌 |
| [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) | 企业级阶段 3 / 选型决策树 |
| [fastembed-learning.md](./fastembed-learning.md) | 可延伸 TextCrossEncoder |
| chat-test `rag/reranker/zhipu_rerank_api.py` | 生产 Rerank API |
| chat-test `rag/es.py` / `rag/rag_api.py` | 粗排 → 精排 → 截断 |

---

## 13. 一句话总结

> **Rerank = 在短名单上用「query↔文档」交叉打分，用精度换少量算力。**

Hybrid 解决召回多样性；Rerank 决定真正喂给模型的那几句。下一步落地时，优先本地小 Cross-Encoder 跑通 `rerank_hits`，再考虑对齐智谱 API。

---

*文档版本：与 gaosi-tutor Hybrid 练习完成态配套；实现落地后可增 `rag-rerank-exercise.md` 脚手架。*
