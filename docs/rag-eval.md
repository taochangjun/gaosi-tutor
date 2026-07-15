# RAG 评测详解：Eval、Precision@K、MRR

> **定位**：搞懂「怎么客观说检索变好了」，为 Hybrid / Rerank 做 A/B 对比打底。  
> **前置**：已跑通 [rag-hybrid-exercise.md](./rag-hybrid-exercise.md)、[rag-rerank-exercise.md](./rag-rerank-exercise.md)；家长面板能对比多路结果。  
> **对标**：[enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) 阶段 6 · Eval；公司项目 chat-test 目前几乎无 golden set——个人项目反而好补这块简历点。

---

## 术语

| 名称 | 含义 |
|------|------|
| **Eval（Evaluation）** | 用固定题目 + 标注 + 指标，**量化**系统好不好，而不是靠语感。 |
| **Golden Set / 黄金集** | 一组人工标好的 `(query → 期望相关 chunk)` 样本。 |
| **Retrieval Eval** | 只评「找没找对片段」，不评 LLM 最终回答文采。 |
| **End-to-End Eval** | 评「最终答案对不对 / 是否忠实于材料」（可用人工或 LLM-as-Judge）。 |
| **Precision@K** | 返回的前 K 条里，相关结果占比。 |
| **Recall@K** | 所有「该召回的」相关文档里，前 K 条命中了多少比例。 |
| **MRR** | Mean Reciprocal Rank：第一个相关结果排得越前，分越高。 |

一句话：

> **Demo 靠演示；生产靠 Eval。**  
> Hybrid / Rerank 做完后，下一句面试官常问的是：「你怎么证明变好了？」

---

## 1. 为什么要 Eval？

家长面板肉眼看「好像不错」有三个坑：

1. **挑 query**：只试自己编过的好运问题，漏掉坏 case  
2. **不可复现**：改了 RRF / Rerank 模型，说不清涨了还是跌了  
3. **通路混淆**：向量变好还是精排变好，分不清  

Eval 把问题变成：

```
固定黄金集
    │
    ▼
对每条 query 跑 vector / bm25 / hybrid / rerank
    │
    ▼
算 Precision@3、MRR（可选 Recall@3）
    │
    ▼
出一张表：谁涨、谁跌、哪些 query 仍挂
```

对 gaosi-tutor：先做 **Retrieval Eval** 就够用；完整 RAGAS / 答案评判可以以后再加。

---

## 2. Eval 在 RAG 里评什么？

管线拆开看：

```
Query
  → Retrieve（向量 / BM25 / Hybrid）
  → Rerank（可选）
  → Augment（把 top-N 塞进 prompt）
  → Generate（LLM 回答）
```

| 评测层 | 问的问题 | 常用指标 | gaosi-tutor 优先？ |
|--------|----------|----------|-------------------|
| **检索层** | top-K 里有没有该看的笔记？ | Precision@K、Recall@K、MRR | ✅ 先做这个 |
| **生成层** | 回答是否基于笔记、有没有胡编？ | 人工打分、LLM-as-Judge、faithfulness | 稍后 |
| **产品层** | 家长是否觉得有用？ | 点赞 / A/B | 辅助 |

Rerank 改的是**排序与 top-N 纯度**，所以先盯检索层最对口。

---

## 3. 黄金集（Golden Set）长什么样？

最小字段：

```json
{
  "id": "q005",
  "query": "借位哪里薄弱",
  "lesson_id": 5,
  "relevant_chunk_ids": ["lesson-5-chunk-0"],
  "note": "金标句：孩子减法还不太熟练，尤其是借位。"
}
```

要点：

1. **`relevant_chunk_ids` 必须稳定**  
   用索引里的 `chunk_id`（如 `lesson-5-chunk-0`），不要只写中文摘要——换切块策略后才对得上。  
2. **一条 query 可以有多个相关 chunk**  
   例如「退位」相关句与「借位」金标都算相关。  
3. **规模**  
   - 入门：10～20 条（练习够用）  
   - 像样：30～50 条，覆盖借位 / 竖式 / 左右 / 干扰问法  
4. **索引变了要重标**  
   `make seed-notes-bulk` 重写笔记后，chunk 序号可能变，黄金集要核对。

建议从现在就能测的 query 攒起：「借位哪里薄弱」「竖式不对」「退位减法总搞错」「左右还混」等。

---

## 4. Precision@K（精确率@K）

### 4.1 定义

对一次查询，系统返回有序列表 \(R_1, R_2, \ldots, R_K\)（只看前 K 条）。  
设相关集合为 \(Rel\)（黄金集里标的 chunk）。

\[
\mathrm{Precision@K}
= \frac{\text{前 K 条中属于 } Rel \text{ 的条数}}{K}
\]

直白说：**前 K 个结果里，有多大比例是你要的。**

### 4.2 例子（家庭笔记）

假设：

- query：`借位哪里薄弱`
- 相关：`{lesson-5-chunk-0}`（「尤其是借位」那句）
- K = 3

| 通道 | Top3 chunk_id（示意） | 命中数 | Precision@3 |
|------|------------------------|--------|-------------|
| 糟糕噪音榜 | noise, noise, noise | 0 | **0** |
| BM25 较好 | **chunk-0**, tmpl-a, tmpl-b | 1 | **1/3 ≈ 0.33** |
| 理想 Rerank | **chunk-0**, 退位相关, 口算相关 | 1 | **0.33**（若只标了 1 个相关） |
| 若标了 2 个相关且都进 Top3 | chunk-0, chunk-1, noise | 2 | **2/3 ≈ 0.67** |

注意：

- **只标了 1 个相关 chunk 时，Precision@3 上限是 1/3**，不是 1。  
  比分时应用「同一黄金集、同一 K」，看各通道相对高低即可。  
- Precision@K **不关心**相关结果排第 1 还是第 3，只关心「进没进前 K」。

### 4.3 什么时候看 Precision@K？

- LLM **只吃 top-K**（如 `rag_top_k=3`）时：喂进去的垃圾比例 ≈ 1 − Precision@K  
- 对比 **Rerank 前后**：精排目标就是抬高 Precision@3  

粗排很宽（K=20）时，更常看 **Recall@20**；压到 3 条给模型时，看 **Precision@3**。

---

## 5. Recall@K（召回率@K）（一并弄清）

\[
\mathrm{Recall@K}
= \frac{\text{前 K 条中命中的相关条数}}{\lvert Rel \rvert}
\]

直白说：**所有该找到的相关文档里，前 K 捞到了几成。**

同一例子，\(Rel=\{chunk\text{-}0\}\)，金标在第 2 名：

- Recall@3 = 1/1 = **1**  
- Recall@1 = 0（若第 1 名不是它）

| | Precision@K | Recall@K |
|--|-------------|----------|
| 分母 | 固定为 K | 相关文档总数 \|Rel\| |
| 关心 | TopK **纯度** | TopK **覆盖** |
| 粗排 | 次要 | **更重要**（别漏） |
| 精排后 top-3 | **更重要** | 仍要看（别把唯一金标挤掉） |

Hybrid / RRF 主打抬 Recall；Rerank 主打抬 Precision。两边都要报，故事才完整。

---

## 6. MRR（Mean Reciprocal Rank）

### 6.1 单条：Reciprocal Rank

对一条 query，找**第一个**相关结果的排名 \(r\)（从 1 开始）：

\[
\mathrm{RR} = \frac{1}{r}
\]

若前 K 名（或整个列表）都没有相关结果：\(\mathrm{RR}=0\)。

| 第一个相关结果的排名 | RR |
|----------------------|-----|
| 第 1 名 | 1.00 |
| 第 2 名 | 0.50 |
| 第 3 名 | ≈0.33 |
| 第 10 名 | 0.10 |
| 未命中 | 0 |

### 6.2 多条取平均：MRR

\[
\mathrm{MRR} = \frac{1}{N}\sum_{i=1}^{N} \mathrm{RR}_i
\]

\(N\) = 黄金集 query 条数。

### 6.3 例子

三条 query，只看「第一个相关」：

| query | 首个相关排名 | RR |
|-------|--------------|-----|
| 借位哪里薄弱 | 1 | 1.00 |
| 竖式不对 | 2 | 0.50 |
| 小动物 | 未进 top10 | 0 |
| **MRR** | | **(1+0.5+0)/3 ≈ 0.50** |

精排若把「借位」从第 4 提到第 1，这一条 RR：0.25 → 1.00，会明显拉高 MRR。

### 6.4 Precision@3 vs MRR：别混

| | Precision@3 | MRR |
|--|-------------|-----|
| 看什么 | Top3 **里有多少相关** | **第一个**相关有多靠前 |
| 金标在第 3 名 | Precision 有贡献 | RR 只有 1/3 |
| 金标在第 1 名，后面全噪音 | Precision@3 可能仍低 | MRR 已经很高 |
| 适合描述 | 「塞进 LLM 的 3 条水分大不大」 | 「用户/模型第一眼看到的对不对」 |

实务：**两个都报**。Rerank 常表现为 MRR ↑、Precision@3 ↑；若只抬 MRR、Precision 不动，可能只是把唯一金标挪到前面，后两名仍是噪音。

---

## 7. 怎么用在 gaosi-tutor？

### 7.1 最小对比实验

对同一黄金集，分别跑：

| 通道 | 来源 |
|------|------|
| vector | `search_family_notes` |
| bm25 | `bm25_search` |
| hybrid | `hybrid_search_family_notes(..., with_rerank=False)` 的 hybrid |
| rerank | `with_rerank=True` 的 rerank |

对每条 query 算 Precision@3、RR，再对通道求平均 → 一张表：

```text
          P@3    MRR
vector    0.21   0.35
bm25      0.28   0.42
hybrid    0.31   0.48
rerank    0.40   0.61   ← 期望：中文友好精排时抬升
```

### 7.2 和家长面板的关系

| 面板 | Eval |
|------|------|
| 一次看一条 query 的四列 | 定性、找 bad case |
| 黄金集批量跑指标 | 定量、改参数后回归 |

两者互补：Eval 发现掉分的 query → 面板打开细看为什么。

### 7.3 常见坑

1. **用中文句子当标签，不用 chunk_id** → 一切块全军覆没  
2. **只标 1 个相关，却解读「P@3=0.33 太低」** → 先看相对提升  
3. **重灌 seed 不更新黄金集** → 指标乱跳  
4. **英文 MiniLM 精排** → 中文 query 上 MRR/P@3 可能**变差**（你已见过）  
5. **只在单讲过滤下测** → 漏掉跨讲噪音；建议「全库」和「lesson_id=5」两种设置都有样本  

---

## 8. 和更重框架的关系（知道即可）

| 方案 | 是什么 | 现在要不要上 |
|------|--------|--------------|
| **手写 Precision@K / MRR** | 本页；几十行脚本 | ✅ 推荐下一步 |
| **RAGAS** | faithfulness、answer relevance 等 | 答案层再上 |
| **LLM-as-Judge** | 提示词打分 | 检索稳定后再做 |
| **Langfuse 等** | Trace / 生产观测 | 与 Eval 并列，阶段 6 |

简历可写：

> 自建家庭笔记检索黄金集，对比 vector / BM25 / Hybrid / Rerank 的 Precision@3 与 MRR，用指标驱动精排与调参。

---

## 9. 建议学习顺序

1. [x] 读本文，能手算一例 Precision@3 与 RR  
2. [ ] 标 10 条黄金 query（绑定真实 `chunk_id`）  
3. [ ] 写/跑小型 `scripts/eval`：打出四通道表（后续可增 `rag-eval-exercise.md`）  
4. [ ] 换中文 Rerank 或智谱 API 后重跑，看 MRR / P@3 是否上升  
5. [ ] 再读 [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) 阶段 6  

---

## 10. 相关文档

| 文档 | 关系 |
|------|------|
| [rag-rerank.md](./rag-rerank.md) §10 | 指标一览；细节以本文为准 |
| [rag-rerank-exercise.md](./rag-rerank-exercise.md) | 精排实现；完成后用 Eval 验收 |
| [rag-hybrid-exercise.md](./rag-hybrid-exercise.md) | 混合检索；可用同一黄金集对比 |
| [enterprise-rag-roadmap.md](./enterprise-rag-roadmap.md) | 阶段 6 全局位置 |
| [agent-rag.md](./agent-rag.md) | RAG 管线全貌 |

---

## 11. 一句话总结

> **Eval = 固定题 + 标注 + 指标。**  
> **Precision@3 = Top3 有多纯；MRR = 第一条相关有多靠前；Recall@K = 该召回的漏没漏。**

粗排保 Recall，精排抬 Precision/MRR；没有黄金集，两者都只是感觉。

---

*文档版本：与 gaosi-tutor Hybrid + Rerank 完成态配套；动手脚手架可另增 `rag-eval-exercise.md`。*
