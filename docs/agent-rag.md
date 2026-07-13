# SOP 检索（RAG）详解 — 结合 SanyMES Agent 项目

> 本文档说明：什么是 SOP、什么是 RAG、本项目如何切分 chunk、检索器如何工作、如何启用向量检索。  
> 配套代码：`backend/app/agent/rag/`，工具入口：`search_sop`（`tools.py`）。

---

## 目录

1. [什么是 SOP](#1-什么是-sop)
2. [为什么需要 RAG](#2-为什么需要-rag)
3. [什么是 RAG](#3-什么是-rag)
4. [RAG 在本项目中的位置](#4-rag-在本项目中的位置)
5. [Chunk 切分策略](#5-chunk-切分策略)
6. [检索器 SopRetriever](#6-检索器-sopretriever)
7. [两种检索模式](#7-两种检索模式)
8. [如何启用向量检索](#8-如何启用向量检索)
9. [与 Function Calling 的配合](#9-与-function-calling-的配合)
10. [走一遍完整例子](#10-走一遍完整例子)
11. [局限与改进方向](#11-局限与改进方向)
12. [自测与调试](#12-自测与调试)

---

## 1. 什么是 SOP

**SOP（Standard Operating Procedure，标准作业程序）** 是制造现场对某一工序的**标准化操作说明**，告诉操作工「按什么顺序、做什么、注意什么」。

在本项目（SanyMES Demo）里，SOP 数据存在两处：

| 数据表 | 字段 | 含义 |
|--------|------|------|
| `process_route_steps` | `sop_content` | 工艺路线上的标准作业步骤（模板） |
| `process_route_steps` | `safety_notes` | 该工位的安全注意事项 |
| `station_tasks` | `sop_content` / `safety_notes` | 具体工单在某工位的任务副本（运行时） |

**示例（液压系统工位）：**

```
作业步骤 (sop_content):
  1. 安装液压油箱及管路
  2. 连接各执行器
  3. 液压系统保压测试 28MPa
  4. 检查无泄漏

安全注意事项 (safety_notes):
  液压油禁止接触皮肤
```

MES 终端机（`/terminal`）会展示这些内容给操作工。Agent 阶段 3 的目标是：**用户用自然语言提问，系统从 SOP 文档里检索相关内容再回答**，而不是让 LLM 凭空编造。

---

## 2. 为什么需要 RAG

### 阶段 2 的工具有局限

阶段 2 的工具（`get_work_order`、`list_work_orders`）返回的是**结构化 JSON**：

```json
{
  "order_no": "WO-20250706-001",
  "status": "in_progress",
  "progress": "3/7"
}
```

适合回答「进度怎么样」「有哪些工单」，但**不适合**回答：

- 「液压系统装配要注意什么安全事项？」
- 「底盘预装的具体步骤是什么？」
- 「保压测试压力是多少？」

这些信息在 **长文本 SOP** 里，有以下问题：

| 问题 | 说明 |
|------|------|
| **太长** | 7 个工位 × 多行步骤，全塞进 prompt 会爆 token |
| **非结构化** | 是自然语言段落，不是固定字段 |
| **不能全库扫描** | 每次提问只关心 1～2 个工位的内容 |

### RAG 的思路

> **R（Retrieval）**：先从文档库里**检索**相关片段  
> **A（Augmented）**：把片段**增强**进 LLM 的上下文  
> **G（Generation）**：让 LLM **生成**回答

只把「可能相关的几段 SOP」交给 LLM，而不是整本手册。

---

## 3. 什么是 RAG

RAG 全称 **Retrieval-Augmented Generation（检索增强生成）**，典型流程分 4 步：

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Index   │ →  │ Retrieve │ →  │ Augment  │ →  │ Generate │
│  建索引   │    │  检索     │    │  增强上下文 │    │  生成回答  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 各步含义

| 步骤 | 做什么 | 本项目对应 |
|------|--------|-----------|
| **Index** | 把原始文档切成 chunk，可选计算 embedding | `load_sop_chunks()` + `build_index()` |
| **Retrieve** | 根据用户问题找 top-K 相关 chunk | `SopRetriever.search()` |
| **Augment** | 把检索结果交给 LLM | `role: tool` 的 JSON 内容 |
| **Generate** | LLM 组织自然语言 | Agent loop 第 2 轮 `chat()` |

### 和阶段 1 Context Injection 的区别

| | 阶段 1 | RAG（阶段 3） |
|--|--------|--------------|
| 数据选择 | 代码规则决定塞什么 | **检索器**按问题语义找相关片段 |
| 适用数据 | 结构化（工单 JSON） | 非结构化（SOP 长文本） |
| 扩展性 | 加字段要改代码 | 加文档重新 index 即可 |

### 和阶段 2 Tool Calling 的关系

RAG **不是替代** Function Calling，而是**多了一种工具**：

- `get_work_order` → 查结构化数据
- `search_sop` → 查非结构化文本（RAG 检索器）

LLM 根据问题类型自动选择调哪个工具。

---

## 4. RAG 在本项目中的位置

```
backend/app/agent/
├── rag/
│   ├── chunks.py      # 从 DB 加载并切分 SOP
│   ├── retriever.py   # SopRetriever：建索引 + 检索
│   └── __init__.py
├── tools.py           # search_sop 工具定义与 execute_tool
├── loop.py            # Agent 循环（调用 search_sop 后生成回答）
└── prompts.py         # AGENT_SYSTEM_PROMPT（提示用 search_sop）
```

**启动时**（`main.py` → `on_startup`）：

```python
get_sop_retriever().build_index(db)
# 日志：[RAG] SOP 索引已加载：14 个文本块
```

**运行时**：

```
POST /api/agent/chat
  → run_agent()
  → LLM 调 search_sop
  → SopRetriever.search()
  → 结果作为 tool message 返回 LLM
  → LLM 生成最终回答
```

---

## 5. Chunk 切分策略

### 什么是 Chunk

**Chunk（文本块）** 是 RAG 检索的**最小单位**。原始 SOP 太长，要拆成小块才能：

- 精准命中（问安全就只返回安全块）
- 控制 token（只传 top-3 块给 LLM）

### 本项目的切分策略

文件：`backend/app/agent/rag/chunks.py`

**数据源**：活跃工艺路线 `ProcessRouteStep`（不是运行时 `StationTask`，因为 SOP 模板在工艺路线上更稳定）。

**切分规则：每个工位 → 最多 2 个 chunk**

| chunk_type | 内容来源 | 示例 id |
|------------|---------|---------|
| `sop` | `step.sop_content` 整段 | `SY-5288THB-WS-A04-sop` |
| `safety` | `step.safety_notes` 整段 | `SY-5288THB-WS-A04-safety` |

**当前 demo 共 14 块**：7 工位 × 2（步骤 + 安全）。

### 为什么这样切

| 策略 | 优点 | 缺点 |
|------|------|------|
| **按工位 + 类型切（本项目）** | 问安全/步骤可精准命中；块大小适中 | 单块内多步骤不再细分 |
| 按固定字符数切（如 500 字） | 通用 | 可能把一步操作拦腰截断 |
| 按行切（`\n`） | 细粒度 | 块太多、上下文碎片化 |
| 整本 SOP 一块 | 实现简单 | 检索不精准、token 浪费 |

对本项目 7 工位、每工位 4 行步骤的规模，**「工位 × 类型」二分**是性价比最高的策略。

### SopChunk 数据结构

```python
@dataclass
class SopChunk:
    id: str              # 唯一标识
    station_code: str    # WS-A04
    station_name: str    # 液压系统工位
    product_name: str    # 52米混凝土泵车
    chunk_type: str      # sop | safety
    text: str            # 实际文本内容
```

### 示例 chunk

```json
{
  "id": "SY-5288THB-WS-A04-safety",
  "station_code": "WS-A04",
  "station_name": "液压系统工位",
  "product_name": "52米混凝土泵车",
  "chunk_type": "safety",
  "text": "液压油禁止接触皮肤"
}
```

### 未来可改进的切分

- 按 `\n` 把 `sop_content` 再拆成逐步 chunk（工位有 20+ 步骤时）
- 不同产品不同工艺路线（62 米泵车）自动纳入索引
- 把 `station_tasks` 的运行时 `report_note` 也纳入（现场反馈）

---

## 6. 检索器 SopRetriever

文件：`backend/app/agent/rag/retriever.py`

### 核心 API

```python
retriever = get_sop_retriever()          # 单例
retriever.build_index(db)                # 启动时：加载 chunk + 可选算 embedding
hits = retriever.search(query, top_k=3, station_name=None)  # 检索
```

### build_index：建索引

```
1. load_sop_chunks(db)  → 从 DB 读出所有 SopChunk
2. 若配置了 embedding_model：
     对每个 chunk 拼成 document 文本
     调用 embeddings API 批量算向量
     存入 self._embeddings
3. 否则：仅内存保存 chunks，检索时用关键词
```

**Embedding 用的 document 格式**（`_chunk_document`）：

```
产品：52米混凝土泵车
工位：液压系统工位（WS-A04）
类型：安全注意事项
液压油禁止接触皮肤
```

把元数据（产品、工位、类型）和正文拼在一起，向量化时语义更完整。

### search：检索

```
1. 可选：按 station_name 过滤候选集
2. 有 embedding → 向量相似度排序
   无 embedding → 关键词打分排序
3. 返回 top_k 条，带 score
```

### 返回格式

```json
[
  {
    "station_code": "WS-A04",
    "station_name": "液压系统工位",
    "product_name": "52米混凝土泵车",
    "type": "safety",
    "text": "液压油禁止接触皮肤",
    "score": 4.5
  }
]
```

---

## 7. 两种检索模式

### 模式 A：关键词匹配（默认）

**触发条件**：`.env` 中 **未配置** `EMBEDDING_MODEL`（`settings.embedding_model` 为空）。

**原理**（`_keyword_score`）：

1. 从 query 提取 token（中文 2 字以上 + 英文数字）
2. 在「工位名 + 工位码 + 产品名 + 正文」里匹配，命中 +1
3. 工位名出现在 query 里 → +3
4. 问「安全/注意」且 chunk 是 `safety` 类型 → +1.5
5. 问「步骤/操作」且 chunk 是 `sop` 类型 → +1.0

**优点**：零额外 API、启动快、demo 够用  
**缺点**：同义词、语义相近但用词不同可能漏检（如「防护规范」vs「安全注意事项」）

### 模式 B：向量检索（Embedding）

**触发条件**：配置了 `EMBEDDING_MODEL`。

**原理**：

1. **索引阶段**：每个 chunk 的 document 文本 → embedding 向量（高维浮点数组）
2. **查询阶段**：用户问题 → query 向量
3. **相似度**：query 向量与每个 chunk 向量算 **余弦相似度**（cosine similarity）
4. 按相似度降序取 top_k

**优点**：「液压危险」「液压安全」语义相近也能命中  
**缺点**：需要 embedding API；索引构建多一次 API 调用

### 对比

| | 关键词 | 向量 |
|--|--------|------|
| 配置 | 默认 | 需 `EMBEDDING_MODEL` |
| 匹配方式 | 字面重合 | 语义相似 |
| 额外 API | 无 | index + 每次 search 各 1 次 embedding |
| 适合场景 | 工位名明确、词能对准 | 问法多样、同义表达多 |

---

## 8. 如何启用向量检索

### 步骤 1：确认 API 支持 Embeddings

本项目通过 **OpenAI 兼容接口** 调用（与 chat 同一个 `base_url` + `api_key`）：

```python
client.embeddings.create(model="...", input=["文本1", "文本2"])
```

需确认你使用的服务商提供 embedding 端点（DeepSeek 主站 chat API 未必提供；可改用 OpenAI、Azure、国内 embedding 服务等，只要兼容 OpenAI SDK）。

### 步骤 2：配置环境变量

编辑 `backend/config/.env`：

```env
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.openai.com/v1   # 若用 OpenAI embedding 需改 base_url

# 启用向量检索（字段名 embedding_model → 环境变量 EMBEDDING_MODEL）
EMBEDDING_MODEL=text-embedding-3-small
```

`app/settings.py` 中：

```python
embedding_model: str = ""   # 空 = 关键词；非空 = 向量
```

### 步骤 3：重启后端

```bash
cd backend && python run.py
```

启动日志应出现：

```
[RAG] SOP 索引已加载：14 个文本块
```

若 embedding 成功，`build_index` 会为 14 个 chunk 各算一个向量（启动时多一次 API 调用，略慢）。

### 步骤 4：验证

```bash
# 直接测检索器
cd backend
python -c "
from app.database import SessionLocal
from app.agent.rag import get_sop_retriever
db = SessionLocal()
r = get_sop_retriever()
r.build_index(db)
print(r.search('液压装配有什么危险', top_k=2))
db.close()
"

# 通过 Agent 测
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "液压系统工位要注意什么安全事项？"}'
```

### 向量检索内部流程（代码对照）

**建索引**（`build_index`）：

```python
texts = [self._chunk_document(c) for c in self._chunks]
response = client.embeddings.create(model=settings.embedding_model, input=texts)
self._embeddings = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
```

**查询**（`_search_by_embedding`）：

```python
q_emb = client.embeddings.create(model=..., input=[query]).data[0].embedding
sim = cosine(q_emb, chunk_embedding)   # 余弦相似度，范围约 0～1
```

### 常见问题

| 现象 | 可能原因 |
|------|---------|
| 启动报错 embedding | `EMBEDDING_MODEL` 或 `base_url` 不对 |
| 向量和关键词结果差不多 | chunk 少（14 块），短文本差异不大 |
| 检索很慢 | 每次 search 都调 embedding API；可缓存 query 向量或换本地模型 |

---

## 9. 与 Function Calling 的配合

`search_sop` 在 `tools.py` 中注册为 Agent 工具：

```python
{
    "name": "search_sop",
    "description": "检索工位 SOP 作业步骤或安全注意事项...",
    "parameters": {
        "query": "检索关键词或自然语言问题",
        "station_name": "可选，缩小到某工位"
    }
}
```

**执行函数**（不直接暴露 RAG 给前端，走统一 tool 协议）：

```python
def tool_search_sop(query: str, station_name: str | None = None) -> dict:
    hits = get_sop_retriever().search(query, top_k=3, station_name=station_name)
    if not hits:
        return {"ok": False, "error": "未找到相关 SOP 内容"}
    return {"ok": True, "data": hits}
```

**LLM 决策示例：**

| 用户问题 | 预期工具 |
|---------|---------|
| 液压系统工位要注意什么安全事项？ | `search_sop(query=..., station_name=液压系统工位)` |
| WO-001 进度怎么样？ | `get_work_order` |
| 底盘预装有哪些步骤？ | `search_sop(query=底盘预装 步骤)` |

RAG 负责 **Retrieve + 把结果放进 tool message**；**Generate** 仍由 Agent loop 里的 LLM 完成。  
因此 RAG 在本项目是 **「检索器 + 一种特殊工具」**，不是单独的新接口。

---

## 10. 走一遍完整例子

**用户：** 「液压系统工位要注意什么安全事项？」

### ① 启动时已建索引

```
14 chunks in memory
  ...
  SY-5288THB-WS-A04-safety → "液压油禁止接触皮肤"
  SY-5288THB-WS-A04-sop    → "1. 安装液压油箱及管路..."
```

### ② LLM 第 1 轮 → tool_calls

```json
{
  "name": "search_sop",
  "arguments": "{\"query\": \"安全注意事项\", \"station_name\": \"液压系统工位\"}"
}
```

### ③ execute_tool → SopRetriever.search

```json
{
  "ok": true,
  "data": [
    {
      "station_name": "液压系统工位",
      "type": "safety",
      "text": "液压油禁止接触皮肤",
      "score": 4.5
    }
  ]
}
```

### ④ LLM 第 2 轮 → 根据 tool 结果生成

```
液压系统工位的安全注意事项：液压油禁止接触皮肤……
```

**注意**：LLM 可能在检索结果之外「补充」通用安全建议。若要求严格只引用 SOP，需在 prompt 中加：「仅根据检索结果回答，不要补充」。

---

## 11. 局限与改进方向

| 局限 | 说明 | 改进 |
|------|------|------|
| 仅 14 个 chunk | demo 规模小 | 多产品、多路线、拆更细 |
| 索引在内存 | 重启重建 | 持久化到文件 / Chroma / pgvector |
| 关键词检索 | 同义词弱 | 启用 embedding |
| 无重排序 | top_k 直接给 LLM | 加 cross-encoder rerank |
| LLM 可能幻觉 | 补充 SOP 没有的内容 | 强化 prompt + 引用原文 |

---

## 12. 自测与调试

### 只测检索器（不经过 LLM）

```bash
cd backend
python -c "
from app.database import SessionLocal
from app.agent.rag import get_sop_retriever
db = SessionLocal()
r = get_sop_retriever()
print('indexed:', r.build_index(db))
for q in ['液压系统安全', '底盘预装步骤', '臂架下方']:
    print(q, '->', r.search(q, top_k=1))
db.close()
"
```

### 测 Agent 工具链

```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "底盘预装工位有哪些操作步骤？"}'
```

看响应里的 `tool_calls` 是否包含 `search_sop`，`answer` 是否引用步骤内容。

### 对照阅读

| 文档 | 内容 |
|------|------|
| [agent-function-calling.md](./agent-function-calling.md) | Tool Calling、messages 结构 |
| 本文档 | RAG、chunk、检索器、向量配置 |
| `backend/app/agent/rag/` | 源码 |

---

## 附录：RAG vs 全量塞 prompt

**不用 RAG（阶段 1 做法）：**

```python
# 把所有 SOP 塞进 system prompt — 7 工位全文，token 爆炸
context = all_sops_json  # 可能 5000+ tokens
```

**用 RAG（阶段 3）：**

```python
# 只检索 3 个相关块，约 200 tokens
hits = retriever.search("液压安全", top_k=3)
```

这就是 RAG 的核心价值：**按需取数，而非全量灌输**。
