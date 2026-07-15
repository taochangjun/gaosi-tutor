---
name: check-rag-impl
description: >-
  检查 gaosi-tutor RAG 混合检索练习中指定函数的实现是否正确。用户输入函数名
  （如 tokenize_for_bm25、rrf_merge）时，对照 docs/rag-hybrid-exercise.md 规范
  审阅代码、运行针对性冒烟测试并输出结构化反馈。Use when the user asks to
  check/review/verify a RAG function implementation, or names a function from
  bm25_index.py or hybrid.py.
---

# 检查 RAG 函数实现

用户给出**函数名**（如 `tokenize_for_bm25`），按本 skill 审阅其实现是否有问题。

## 工作流程

### 1. 解析函数名

从用户消息提取函数名。支持别名：

| 用户可能输入 | 规范名 |
|-------------|--------|
| `tokenize` | `tokenize_for_bm25` |
| `build_corpus` / `bm25_corpus` | `build_bm25_corpus` |
| `bm25` | `bm25_search` |
| `rrf` / `merge` | `rrf_merge` |
| `hybrid` / `hybrid_search` | `hybrid_search_family_notes` |

若无法识别，列出 [reference.md](reference.md) 中全部可检查函数并请用户重选。

### 2. 定位实现

| 函数 | 文件 |
|------|------|
| `tokenize_for_bm25` | `backend/app/agent/rag/bm25_index.py` |
| `build_bm25_corpus` | `backend/app/agent/rag/bm25_index.py` |
| `get_bm25_corpus` | `backend/app/agent/rag/bm25_index.py` |
| `invalidate_bm25_cache` | `backend/app/agent/rag/bm25_index.py` |
| `bm25_search` | `backend/app/agent/rag/bm25_index.py` |
| `rrf_merge` | `backend/app/agent/rag/hybrid.py` |
| `_hit_key` | `backend/app/agent/rag/hybrid.py` |
| `hybrid_search_family_notes` | `backend/app/agent/rag/hybrid.py` |

用 Read 工具读取该函数**完整实现**（含 docstring 上下文）。

### 3. 对照规范

读取 [reference.md](reference.md) 中该函数的 **必过项 / 常见错误 / 冒烟断言**，逐项核对。

同时扫一眼：
- 是否仍为 `raise NotImplementedError`（未实现）
- 是否 import 了 `rank_bm25`（`build_bm25_corpus` / `bm25_search` 需要）
- 空输入、空库、lesson_id 过滤等边界

### 4. 运行针对性测试

在项目根目录执行（需已 `make install` 且 MySQL 可用时跑依赖 DB 的项）：

```bash
cd backend && ./venv/bin/python ../.cursor/skills/check-rag-impl/scripts/check_function.py <函数名>
```

脚本会输出 `PASS` / `FAIL` / `SKIP` 及错误信息。将结果纳入报告。

**无 DB 也可测的函数**：`tokenize_for_bm25`、`rrf_merge`（脚本内用内存数据）。

### 5. 输出报告（必须用此结构）

```markdown
## 检查：`函数名`

**文件**：`path/to/file.py`
**状态**：✅ 通过 | ⚠️ 有问题 | ❌ 未实现

### 规范核对
- [x] 或 [ ] 必过项 1：…
- [x] 或 [ ] 必过项 2：…

### 发现的问题
1. 🔴 **严重**：…（必须修）
2. 🟡 **建议**：…（可选优化）

### 测试
\`\`\`
（粘贴 check_function.py 输出）
\`\`\`

### 下一步
（一条具体修改建议；若已通过，建议测下一函数或 `make smoke-hybrid`）
```

### 6. 原则

- **先跑测试再下结论**；测试失败时结合代码指出根因
- 不要替用户重写整函数，只指出问题和最小修改方向
- 通过全部必过项且测试 PASS → 明确告知可进入下一练习
- 用户只贴了代码片段时，仍先 Read 仓库中最新文件再评

## 快速命令

```bash
# 单函数检查
cd backend && ./venv/bin/python ../.cursor/skills/check-rag-impl/scripts/check_function.py tokenize_for_bm25

# 全部混合检索练习
make smoke-hybrid
```

## 延伸阅读

- 练习步骤：[docs/rag-hybrid-exercise.md](../../docs/rag-hybrid-exercise.md)
- 函数规范：[reference.md](reference.md)
