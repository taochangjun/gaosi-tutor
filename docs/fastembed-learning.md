# FastEmbed 学习文档（基于 gaosi-tutor 项目）

> FastEmbed 是 Qdrant 团队出品的 **本地文本 Embedding 库**，本项目用它把家庭笔记变成向量，再写入 Chroma。  
> 配套：[chroma-learning.md](./chroma-learning.md)（存向量）、[agent-rag.md](./agent-rag.md)（RAG 管线）、[vector-db-learning.md](./vector-db-learning.md)（总览）。

## 目录

1. [FastEmbed 是什么](#1-fastembed-是什么)
2. [为什么本项目选它](#2-为什么本项目选它)
3. [与 PyTorch / API Embedding 对比](#3-与-pytorch--api-embedding-对比)
4. [在本项目中的位置](#4-在本项目中的位置)
5. [安装与首次运行](#5-安装与首次运行)
6. [核心 API：TextEmbedding](#6-核心-apitextembedding)
7. [模型选择与配置](#7-模型选择与配置)
8. [ONNX 与量化（为什么快又轻）](#8-onnx-与量化为什么快又轻)
9. [与 Chroma 的配合](#9-与-chroma-的配合)
10. [query 与 document 前缀（部分模型）](#10-query-与-document-前缀部分模型)
11. [常见陷阱与最佳实践](#11-常见陷阱与最佳实践)
12. [动手实验](#12-动手实验)
13. [进阶能力（了解即可）](#13-进阶能力了解即可)
14. [本仓库文件索引](#14-本仓库文件索引)
15. [延伸阅读](#15-延伸阅读)

---

## 1. FastEmbed 是什么

**FastEmbed**（[GitHub](https://github.com/qdrant/fastembed) / [Qdrant 文档](https://qdrant.tech/documentation/fastembed/)）是用于 **生成文本向量（Embedding）** 的 Python 库。

```
文本 "孩子减法还不太熟练"
        │
        ▼  TextEmbedding.embed()
浮点向量 [0.023, -0.11, 0.048, ...]   ← 通常 384～1024 维
        │
        ▼
Chroma / Qdrant / ES 等向量库检索
```

| 特点 | 说明 |
|------|------|
| **轻** | 不依赖 PyTorch；用 ONNX Runtime 推理 |
| **快** | CPU 上比典型 PyTorch 推理更省资源 |
| **本地** | 模型从 HuggingFace 下载到本机，**不调 Embedding API** |
| **准** | 内置模型多来自 MTEB 排行榜（如 bge 系列） |

**它不是向量数据库**，只负责「文本 → 向量」；存和搜由 Chroma 完成。

---

## 2. 为什么本项目选它

gaosi-tutor 场景：家庭笔记、21 讲、chunk 总量通常 < 500。

| 需求 | FastEmbed 是否匹配 |
|------|-------------------|
| 隐私：笔记不出本机 | ✅ 本地推理 |
| 零额外 API 费用 | ✅ 无 DashScope/OpenAI embed 计费 |
| 与 Chroma 搭配 | ✅ 常见组合 |
| 中文家庭短文本 | ✅ `BAAI/bge-small-zh-v1.5` |
| 大规模 / 云端统一网关 | ❌ 企业项目用 DashScope API（见 enterprise-rag-roadmap） |

---

## 3. 与 PyTorch / API Embedding 对比

| | FastEmbed | sentence-transformers (PyTorch) | OpenAI / DashScope API |
|--|-----------|--------------------------------|------------------------|
| 依赖体积 | 小（ONNX） | 大（torch） | 无本地模型 |
| GPU | 不必需 | 可选加速 | 在云端 |
| 费用 | 免费 | 免费 | 按 token |
| 隐私 | 数据不出机器 | 本地 | 文本发到 API |
| 换模型 | 改 `model_name` | 改模型名 | 改 API 模型参数 |
| 本项目 | ✅ embedder.py | 未用 | 未用（LLM 仍用 DeepSeek） |

---

## 4. 在本项目中的位置

```
chunker.py  →  chunk 文本
      │
      ▼
embedder.py  →  fastembed TextEmbedding
      │            embed_texts()  索引
      │            embed_query()  检索
      ▼
store.py     →  Chroma upsert(query_embeddings 由你算好传入)
retriever.py →  embed_query + collection.query
```

**文件：** `backend/app/agent/rag/embedder.py`

```python
@lru_cache()
def _get_model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=settings.rag_embedding_model)

def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]
```

| 阶段 | 函数 | 输入 |
|------|------|------|
| 索引 | `embed_texts` | 所有 chunk 的 `text` 列表 |
| 检索 | `embed_query` | 用户问题一句 |

两阶段 **必须用同一 `TextEmbedding` 实例/同一模型**。

---

## 5. 安装与首次运行

```txt
# backend/requirements.txt
fastembed>=0.4.2
```

```bash
make install
```

**首次**调用 `TextEmbedding(...)` 会从 HuggingFace **下载 ONNX 模型**到本地缓存（通常几百 MB），略慢，属正常现象。

之后 `@lru_cache` 缓存模型实例，同进程内不再重复加载。

验证：

```bash
make smoke-rag
# 或
cd backend && ./venv/bin/python -c "
from app.agent.rag.embedder import embed_query
v = embed_query('减法借位')
print(len(v), v[:3])
"
```

---

## 6. 核心 API：TextEmbedding

### 6.1 最小示例

```python
from fastembed import TextEmbedding

model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")

# embed 返回生成器，逐条产出向量
for vec in model.embed(["孩子减法还不太熟练", "平时喜欢小动物情境"]):
    print(type(vec), len(vec))  # numpy 数组，维度由模型决定
```

### 6.2 批量 vs 单条

```python
texts = ["chunk1", "chunk2", "chunk3"]
vectors = list(model.embed(texts))   # 批量，索引时用

query_vec = list(model.embed(["借位哪里薄弱"]))[0]  # 检索时用
```

本项目 `embed_texts` 把生成器转成 `list[float]` 列表，方便传给 Chroma。

### 6.3 模型下载位置

默认缓存在用户目录（与 HuggingFace hub 类似），例如：

```
~/.cache/huggingface/hub/   # 或 fastembed 文档所述路径
```

离线环境需提前在有网机器下载好缓存再拷贝。

---

## 7. 模型选择与配置

### 7.1 本项目默认

```env
# backend/config/.env
RAG_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

```python
# backend/app/settings.py
rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
```

| 模型 | 特点 |
|------|------|
| `BAAI/bge-small-zh-v1.5` | 中文、小模型、CPU 友好；**本项目默认** |
| `BAAI/bge-base-zh-v1.5` | 中文、更大、通常更准、更慢 |
| `BAAI/bge-small-en-v1.5` | FastEmbed 常见默认（英文） |

[支持模型列表](https://qdrant.github.io/fastembed/examples/Supported_Models/) 以官方为准。

### 7.2 换模型流程

1. 修改 `RAG_EMBEDDING_MODEL`
2. **删除** `backend/data/chroma`（旧向量维度/空间无效）
3. `make rag-index` 全量 reindex

**不 reindex 就换模型 = 检索几乎随机。**

### 7.3 与 Chroma cosine 的关系

本项目 Chroma collection 配置 `hnsw:space: cosine`。bge 类模型输出向量通常已归一化或适合余弦相似度，与 FastEmbed + Chroma 的组合是常见做法。

---

## 8. ONNX 与量化（为什么快又轻）

传统做法：`sentence-transformers` + PyTorch，依赖大、冷启动慢。

FastEmbed 路径：

```
HuggingFace 上的 Transformer
        │
        ▼ 转换为 ONNX + 量化权重
ONNX Runtime 在 CPU 上推理
        │
        ▼
输出 embedding 向量
```

| 概念 | 一句话 |
|------|--------|
| **ONNX** | 跨平台推理格式，专为 **推理** 优化 |
| **量化** | 权重从 FP32 压到 INT8 等，更快更省内存，精度略损 |
| **生成器 `embed()`** | 流式产出，大批量时省内存 |

你不需要自己导出 ONNX；`TextEmbedding(model_name=...)` 会处理。

---

## 9. 与 Chroma 的配合

Chroma **不会**自动帮你 embed（除非另配 `embedding_function`）。

本项目 **显式两阶段**：

```python
# 索引
vectors = embed_texts([c["text"] for c in chunks])
collection.upsert(..., embeddings=vectors)

# 检索
query_vec = embed_query(query)
collection.query(query_embeddings=[query_vec], ...)
```

好处：**Embedding 与向量库解耦**，换 embed 库或换 Chroma 互不影响接口。

---

## 10. query 与 document 前缀（部分模型）

部分检索模型（如 e5、bge 检索版）训练时区分：

- 索引文档：`passage: ...` 或 `document: ...`
- 查询问题：`query: ...`

`BAAI/bge-small-zh-v1.5` 在 FastEmbed 中的具体前缀行为以 [官方文档](https://qdrant.github.io/fastembed/) 为准。  
**本项目索引与查询都用同一 `model.embed(text)`**，未手写前缀；若换模型后检索变差，可查该模型是否要求 query/passage 不同前缀。

---

## 11. 常见陷阱与最佳实践

### ✅ 推荐

| 实践 | 原因 |
|------|------|
| `_get_model()` 单例 + `@lru_cache` | 避免重复加载 ONNX |
| 索引与查询同一 `rag_embedding_model` | 向量空间一致 |
| 批量 `embed_texts` 索引 | 比逐条快 |
| 换模型必 reindex Chroma | 维度与语义空间都变 |

### ❌ 避免

| 陷阱 | 后果 |
|------|------|
| 索引用 fastembed、查询用 OpenAI embed | 检索失效 |
| 不 reindex 换模型 | 乱序结果 |
| 首次生产请求才加载模型 | 第一次超时；可启动时 warmup |
| 与 Chroma 内置 embed 混用 | 空间不一致 |

### 故障排查

| 现象 | 处理 |
|------|------|
| 首次很慢 | 正在下载模型，等待或预下载 |
| `No module named fastembed` | `make install` |
| 维度错误 upsert 失败 | 换模型后未清 chroma |
| 内存占用 | 换 `bge-small` 或减小 batch |

---

## 12. 动手实验

### 实验 1：看向量维度和相似度

```python
from fastembed import TextEmbedding

model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
a = list(model.embed(["孩子减法还不太熟练"]))[0]
b = list(model.embed(["减法借位练习"]))[0]
c = list(model.embed(["今天天气很好"]))[0]

import numpy as np
def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

print("dim:", len(a))
print("相关句相似度:", cos(a, b))
print("无关句相似度:", cos(a, c))
```

相关句 cos 应 **高于** 无关句。

### 实验 2：对比换模型

换 `bge-base-zh-v1.5` 再跑实验 1，观察维度和相似度变化；**不要**直接写入现有 Chroma。

### 实验 3：走项目管线

```bash
make smoke-rag
curl -s -X POST http://127.0.0.1:8000/api/rag/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"减法借位","lesson_id":5}' | python3 -m json.tool
```

### 实验 4：启动 warmup（可选）

在 `main.py` on_startup 里调用一次 `embed_query("warmup")`，避免第一个用户请求承担模型加载延迟。

---

## 13. 进阶能力（了解即可）

FastEmbed 除 `TextEmbedding` 外还有（本项目 **未使用**）：

| 能力 | 用途 |
|------|------|
| **SparseEmbedding** | SPLADE 等稀疏向量，偏关键词 |
| **LateInteractionTextEmbedding** | ColBERT 多向量 |
| **TextCrossEncoder** | Rerank 精排 |

企业路线里的 Rerank、混合检索可与这些组合；gaosi-tutor 现阶段 **dense + Chroma** 足够。

---

## 14. 本仓库文件索引

| 文件 | 内容 |
|------|------|
| `backend/app/agent/rag/embedder.py` | TextEmbedding 封装 |
| `backend/app/settings.py` | `RAG_EMBEDDING_MODEL` |
| `backend/requirements.txt` | `fastembed>=0.4.2` |
| `backend/scripts/smoke_rag.py` | 端到端（含 embed） |
| `docs/enterprise-rag-roadmap.md` | 与 DashScope API embed 的企业对比 |

---

## 15. 延伸阅读

- [FastEmbed 官方文档](https://qdrant.tech/documentation/fastembed/)
- [支持模型列表](https://qdrant.github.io/fastembed/examples/Supported_Models/)
- [GitHub: qdrant/fastembed](https://github.com/qdrant/fastembed)
- [MTEB 排行榜](https://huggingface.co/spaces/mteb/leaderboard) — 选模型参考
- 本项目 [chroma-learning.md](./chroma-learning.md) — 向量存哪、怎么 query

---

*文档版本：与 gaosi-tutor（fastembed ≥0.4.2、bge-small-zh-v1.5）代码同步。*
