# Python 基础学习文档（结合 gaosi-tutor 项目）

> 面向能读一点代码、但对 Python 语法细节不熟的同学。示例优先来自本仓库真实代码。  
> 若你刚遇到 `def f(*, a, b)` 这种写法，可直接看 [第 3 章](#3-函数参数里的-强制关键字参数)。

## 目录

1. [读本项目需要哪些 Python 基础](#1-读本项目需要哪些-python-基础)
2. [类型注解](#2-类型注解)
3. [函数参数里的 `*`（强制关键字参数）](#3-函数参数里的-强制关键字参数)
4. [`*args` 与 `**kwargs`](#4-args-与-kwargs)
5. [位置专用参数 `/`](#5-位置专用参数-)
6. [默认参数与可变默认值陷阱](#6-默认参数与可变默认值陷阱)
7. [生成器 `yield`](#7-生成器-yield)
8. [`@lru_cache` 缓存](#8-lru_cache-缓存)
9. [`from __future__ import annotations`](#9-from-__future__-import-annotations)
10. [`zip()` 并行遍历多个序列](#10-zip-并行遍历多个序列)
11. [本项目常见写法速查](#11-本项目常见写法速查)
12. [本仓库文件索引](#12-本仓库文件索引)
13. [延伸阅读](#13-延伸阅读)

---

## 1. 读本项目需要哪些 Python 基础

| 主题 | 在本项目中的体现 |
|------|------------------|
| 函数与参数 | `chunk_family_note(*, ...)`、`search_family_notes(..., *, lesson_id=)` |
| 类型注解 | `-> list[dict]`、`db: Session` |
| 装饰器 | `@lru_cache`、`@router.get` |
| 生成器 | SSE 流式 `yield` |
| 上下文与资源 | `try/finally: db.close()` |
| 模块导入 | `from .embedder import embed_texts` |
| 并行遍历 | `for a, b in zip(xs, ys)` |

不要求先学完整本 Python 书；**遇到不懂的语法查本文档对应章节**即可。

---

## 2. 类型注解

类型注解是「提示」，运行时不强制检查（除非你用 mypy 等工具）。

```python
def embed_query(query: str) -> list[float]:
    ...
```

| 写法 | 含义 |
|------|------|
| `query: str` | 参数应是字符串 |
| `-> list[float]` | 返回值是浮点数列表 |
| `lesson_id: int \| None` | 整数或 `None`（Python 3.10+） |
| `list[dict]` | 字典组成的列表 |

**本项目示例：**

```python
# backend/app/agent/rag/chunker.py
def chunk_family_note(...) -> list[dict]:

# backend/app/agent/session_store.py
def load_history(db: Session, session_id: str, limit: int = 12) -> list[dict]:
```

注解帮助 IDE 补全和阅读；**不写注解代码也能跑**。

---

## 3. 函数参数里的 `*`（强制关键字参数）

### 3.1 问题从哪来

`chunker.py` 里的定义：

```python
def chunk_family_note(
    *,
    lesson_id: int,
    title: str,
    topic: str,
    notes: str,
) -> list[dict]:
```

参数列表里 **单独一个 `*`**，后面没有变量名。

### 3.2 含义

**`*` 是一条分界线：它后面的参数只能用「关键字」传递，不能按位置传递。**

```python
# ✅ 正确：必须写参数名
chunk_family_note(
    lesson_id=5,
    title="加与减",
    topic="计算",
    notes="孩子减法还不太熟练",
)

# ❌ 错误：TypeError
chunk_family_note(5, "加与减", "计算", "笔记内容")
```

### 3.3 为什么这样设计

四个参数都是 `int` / `str`，按位置传容易写反：

```python
# 若允许位置参数，这种 bug 很难发现
chunk_family_note(5, "计算", "加与减", notes)  # title 和 topic 颠倒了
```

强制关键字后，调用处 **自解释**：

```python
# indexer.py 中的实际调用
chunks = chunk_family_note(
    lesson_id=lesson_id,
    title=meta["title"],
    topic=meta["topic"],
    notes=text,
)
```

### 3.4 和其他形式对比

```python
# 形式 A：全部可位置可关键字（最常见）
def f(a, b, c=0):
    ...

# 形式 B：* 之后只能关键字（本项目 chunk_family_note）
def f(*, lesson_id, title):
    ...

# 形式 C：a 可位置；* 之后只能关键字
def f(a, *, b, c=0):
    f(1, b=2)

# 形式 D：/ 之前只能位置（Python 3.8+，较少见）
def f(a, b, /, c):
    f(1, 2, c=3)
```

记忆口诀：

- **`*` 单独出现** → 右边「必须带名字」
- **`/`** → 左边「不能只带名字」（必须按位置）

### 3.5 本项目里另一处：仅部分参数关键字专用

`retriever.py`：

```python
def search_family_notes(
    db: Session,
    query: str,
    *,
    lesson_id: int | None = None,
    top_k: int | None = None,
) -> dict:
```

| 参数 | 传法 |
|------|------|
| `db`, `query` | 可以 `search_family_notes(db, "借位")` |
| `lesson_id`, `top_k` | 必须 `lesson_id=5`、`top_k=3` |

这样 **必填的放前面**（可省略名字），**可选的放 `*` 后**（避免 `search_family_notes(db, q, None, 5)` 这种难读调用）。

### 3.6 和「解包」里的 `*` 不是一回事

```python
# 定义里的 *  → 强制关键字参数（本章）
def chunk_family_note(*, lesson_id: int): ...

# 调用里的 *  → 把列表/元组解开成位置参数
args = [db, "query"]
search_family_notes(*args)  # 等价于 search_family_notes(db, "query")

# 调用里的 ** → 把字典解开成关键字参数
kwargs = {"lesson_id": 5, "top_k": 3}
search_family_notes(db, "借位", **kwargs)
```

**同名符号，场景不同：**

| 出现位置 | 作用 |
|----------|------|
| `def f(*, a)` | 定义：后面只能关键字 |
| `def f(*args)` | 定义：收集多余位置参数 |
| `f(*items)` | 调用：序列解包为位置参数 |
| `f(**kw)` | 调用：字典解包为关键字参数 |

---

## 4. `*args` 与 `**kwargs`

### 4.1 `*args` — 收集多余位置参数

```python
def log(*args):
    for x in args:
        print(x)

log(1, 2, 3)  # args == (1, 2, 3)
```

### 4.2 `**kwargs` — 收集多余关键字参数

```python
def log(**kwargs):
    print(kwargs)

log(a=1, b=2)  # kwargs == {"a": 1, "b": 2}
```

FastAPI 路由里常见 `**` 解包 Pydantic 模型字段，本质也是关键字参数。

本项目业务代码 **很少** 自定义 `*args/**kwargs`；知道即可。

---

## 5. 位置专用参数 `/`

Python 3.8+：

```python
def f(a, b, /, c):
    # a, b 只能按位置传；c 可以关键字
    ...

f(1, 2, c=3)   # ✅
f(1, b=2, c=3) # ❌ b 不能关键字
```

本项目几乎未用 `/`；与 `*` 相反，了解即可。

---

## 6. 默认参数与可变默认值陷阱

```python
def load_history(db: Session, session_id: str, limit: int = 12):
    ...
```

默认值在 **函数定义时** 求值一次。

**经典坑：不要用可变对象做默认值**

```python
# ❌ 错误示范
def bad(items=[]):
    items.append(1)
    return items

bad()  # [1]
bad()  # [1, 1]  列表被共用！

# ✅ 用 None
def good(items=None):
    if items is None:
        items = []
```

本项目 `session_store.py`、`loader.py` 等默认参数多为 `int` / `str` / `None`，较安全。

---

## 7. 生成器 `yield`

普通 `return` 结束函数；**`yield` 产出一个值后暂停**，下次继续。

```python
# backend/app/agent/loop.py（简化）
def run_agent_stream_from_messages(...) -> Iterator[dict]:
    for delta in chat_stream(...):
        yield {"event": "delta", "data": {"content": delta}}
    yield {"event": "done", "data": {...}}
```

| | `return` | `yield` |
|--|----------|---------|
| 返回 | 一个值，函数结束 | 多个值，多次暂停/恢复 |
| 调用结果 | 普通对象 | 生成器对象 |
| 本项目 | 普通 API 响应 | SSE 流式、`get_db()` |

`database.get_db()` 也是生成器：

```python
def get_db():
    db = SessionLocal()
    try:
        yield db      # 交给 FastAPI 路由使用
    finally:
        db.close()    # 请求结束后执行
```

---

## 8. `@lru_cache` 缓存

```python
from functools import lru_cache

@lru_cache()
def _get_model():
    return TextEmbedding(model_name=...)
```

**无参调用**时，`@lru_cache()` 表示：函数 **只执行一次**，之后返回缓存结果。

本项目用于：

- `embedder._get_model()` — 不重复加载 ONNX 模型
- `store._get_client()` — 不重复创建 Chroma 客户端
- `settings.get_settings()` — 配置只读一次

---

## 9. `from __future__ import annotations`

RAG 模块文件顶部常见：

```python
from __future__ import annotations
```

作用：把类型注解 **延迟求值**，允许写前向引用，且减少循环导入问题。

```python
class TutorSession(Base):
    messages: Mapped[list["TutorMessage"]]  # 引号里的类尚未定义也行
```

Python 3.11+ 部分行为已默认化；保留这行无害，与旧版本兼容。

---

## 10. `zip()` 并行遍历多个序列

### 10.1 基本用法

`zip()` 把多个序列 **按位置配对**，一次循环同时取出对应元素：

```python
names = ["Alice", "Bob"]
scores = [90, 85]

for name, score in zip(names, scores):
    print(name, score)
# Alice 90
# Bob 85
```

等价于按索引写 `for i in range(len(names))`，但更简洁，也 **不要求** 你先手动对齐下标。

| 要点 | 说明 |
|------|------|
| 返回值 | 迭代器，每次产出一个 **元组** |
| 长度 | 以 **最短** 序列为准，多余的元素被丢弃 |
| 解包 | `for a, b in zip(...)` 把元组拆成多个变量 |

```python
list(zip([1, 2, 3], ["a", "b"]))  # [(1, 'a'), (2, 'b')]  3 被丢掉
```

### 10.2 本项目实战：Chroma 检索结果对齐

`retriever.py` 里 Chroma `collection.query()` 返回 **三个平行列表**——文档正文、元数据、距离：

```python
result = collection.query(
    query_embeddings=[query_vec],
    n_results=k,
    include=["documents", "metadatas", "distances"],
)

docs = result.get("documents") or [[]]    # [["孩子减法还不太熟练...", ...]]
metas = result.get("metadatas") or [[]]   # [[{"lesson_id": 5, "title": "加与减"}, ...]]
dists = result.get("distances") or [[]]   # [[0.18, 0.42, ...]]
```

Chroma 支持一次传入多个 query，所以外层是 **二维列表**（每个 query 对应一行）。本项目每次只查 1 条 query，取 `[0]` 得到一维列表：

```python
for doc, meta, dist in zip(docs[0], metas[0], dists[0]):
    score = round(max(0.0, 1.0 - float(dist)), 4)
    hits.append({
        "lesson_id": meta.get("lesson_id"),
        "title": meta.get("title"),
        "topic": meta.get("topic"),
        "snippet": doc,
        "score": score,
    })
```

数据对齐关系：

```
docs[0][i]   ↔  metas[0][i]   ↔  dists[0][i]
   ↓              ↓                ↓
 正文片段      讲次元数据        余弦距离
```

**为什么用 `zip` 而不是三个独立循环？**

- 三个列表 **下标一一对应**，`zip` 保证同一条 hit 的 doc / meta / dist 不会错位
- 比 `for i in range(len(docs[0]))` 更易读
- 循环体里直接得到 `doc`、`meta`、`dist` 三个名字，无需 `docs[0][i]` 反复写下标

### 10.3 为什么要 `docs[0]` 而不是 `docs`

Chroma 返回结构（简化）：

```python
{
  "documents": [["片段1", "片段2", "片段3"]],   # 外层 = query 个数
  "metadatas": [[{...}, {...}, {...}]],
  "distances": [[0.18, 0.42, 0.55]],
}
```

| 层级 | 含义 | 本项目 |
|------|------|--------|
| 外层 `docs` | 每个 query 一组结果 | 长度 1（只查 1 条 query） |
| 内层 `docs[0]` | 该 query 的 Top-K 命中 | 长度 = `n_results` |

所以完整写法是 **先 `[0]` 取当前 query 的结果，再 `zip` 对齐三个平行列表**。

### 10.4 和「解包」里的 `*` 区分

| 写法 | 场景 | 含义 |
|------|------|------|
| `zip(a, b)` | 内置函数 | 并行遍历，每次产出一个元组 |
| `f(*items)` | 函数调用 | 把序列 **展开** 成位置参数 |
| `def f(*args)` | 函数定义 | **收集** 多余位置参数 |

`zip` 是 **配对遍历**；调用处的 `*` 是 **参数展开**。名字相似，作用不同。

### 10.5 常见变体

```python
# 转成字典列表（本项目 indexer 里类似思路）
rows = [(1, "加与减", "计算"), (2, "乘除", "计算")]
for lesson_id, title, topic in rows:
    ...

# 并行遍历两个等长列表（indexer.py 全量索引）
for lesson_id, title, topic, notes in rows:
    chunks = chunk_family_note(lesson_id=lesson_id, title=title, ...)

# 需要下标时：enumerate + zip 很少同用；一般用 enumerate 即可
for i, (doc, meta) in enumerate(zip(docs[0], metas[0])):
    ...
```

---

## 11. 本项目常见写法速查

| 写法 | 文件示例 | 含义 |
|------|----------|------|
| `def f(*, a, b)` | `chunker.py` | 只能关键字传参 |
| `def f(a, *, b=None)` | `retriever.py` | 可选参数强制关键字 |
| `-> list[dict]` | 多处 | 返回字典列表 |
| `db: Session` | `session_store.py` | SQLAlchemy 会话 |
| `if not text:` | 多处 | 空字符串 / None 为假 |
| `x if cond else y` | `tools.py` | 三元表达式 |
| `for a, b in zip(...)` | `retriever.py` | 并行遍历多个等长列表 |
| `with admin.connect() as conn:` | `init_db.py` | 上下文管理器自动关闭 |
| `try / finally` | `get_db`, `router` | 保证清理资源 |

---

## 12. 本仓库文件索引

| 语法点 | 推荐阅读文件 |
|--------|--------------|
| `*` 关键字专用 | `backend/app/agent/rag/chunker.py` |
| `*,` 可选关键字 | `backend/app/agent/rag/retriever.py` |
| `zip()` 并行遍历 | `backend/app/agent/rag/retriever.py`（Chroma 结果对齐） |
| `yield` SSE | `backend/app/agent/router.py`、`loop.py` |
| `@lru_cache` | `embedder.py`、`store.py`、`settings.py` |
| 类型注解 + ORM | `backend/app/models.py` |
| 生成器依赖注入 | `backend/app/database.py` |

---

## 13. 延伸阅读

- [Python 官方教程 — 定义函数](https://docs.python.org/zh-cn/3/tutorial/controlflow.html#defining-functions)
- [PEP 3102 — Keyword-Only Arguments](https://peps.python.org/pep-0310/)（强制关键字参数）
- [PEP 570 — Positional-Only Parameters](https://peps.python.org/pep-0570/)（`/`）
- 本项目 [frontend-guide.md](./frontend-guide.md) — 若也读前端，有 JS 对照表

---

*文档版本：与 gaosi-tutor 后端代码同步。*
