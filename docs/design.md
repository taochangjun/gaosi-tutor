# gaosi-tutor 设计文档

> **项目名：** gaosi-tutor  
> **定位：** 面向小学低年级（MVP：高思竞赛数学课本·一年级上册）的 Agent 陪学助手  
> **定稿日期：** 2026-07-09  
> **状态：** 已确认，待 Phase 1 实施

---

## 1. 背景与动机

### 1.1 为什么做这个项目

- 儿子即将上小学一年级，正在学习 **高思学校竞赛数学课本** 系列。
- 家长在 MES Demo 中已走完 Agent 学习路线（Tool Calling、SSE、Session、Eval），但 **MES 制造业务与日常无关**，讲解 Demo 时缺乏真实体感。
- **gaosi-tutor** 把同一套 Agent 工程能力落到 **家庭陪学** 场景：需求自己提、产品自己用、迭代自己验——更贴近生活，也更能持续维护。

### 1.2 与 MES 的关系

| | MES Demo | gaosi-tutor |
|---|----------|-------------|
| 目的 | 学习 Agent + 工业 Demo | 真实陪学产品 |
| 业务 | 工单、工位、物料 | 讲次、练习、答疑 |
| 代码 | 独立仓库 | **独立仓库**，复用 Agent 架构思路 |
| 数据库 | MySQL `mes` | MySQL **`gaosi_tutor`**（独立库） |

两个项目 **不合并 repo**，避免业务耦合；工程模式（FastAPI + Vue + 手写 loop）保持一致，降低迁移成本。

---

## 2. 需求定稿

| 维度 | 决策 |
|------|------|
| 核心能力 | **答疑 + 出题练习**（学情追踪 Phase 2） |
| 知识库 | **家庭笔记 RAG**（Chroma + fastembed）；prompt 仍注入当前讲笔记摘要 |
| 使用者 | **孩子模式** + **家长模式** |
| 范围 | **一年级上册，21 讲** |
| 技术方案 | 方案 1：MES Agent 模式精简复刻 |
| 数据库 | **MySQL**（与 MES 相同运维习惯，不用 SQLite） |
| LLM | **DeepSeek**（沿用现有 API Key 配置方式） |

---

## 3. 产品形态

### 3.1 双模式

```
┌─────────────────┐     ┌─────────────────┐
│   孩子模式       │     │   家长模式       │
│  大按钮、少设置   │     │  选讲次、难度     │
│  「我不懂」「出题」│     │  看对话、调策略   │
└────────┬────────┘     └────────┬────────┘
         └──────────┬─────────────┘
                    ▼
              同一个 Agent
         （不同 system prompt + UI）
```

**孩子模式**

- 当前讲次由家长预先选好（或默认「上次学到哪」）。
- 快捷入口：「这题不懂」「再出一道」「我答完了」。
- 回复：短句、鼓励、**先启发再讲**（不第一时间给完整答案）。

**家长模式**

- 选择：第 N 讲、难度（兴趣 / 拓展）。
- 可查看当前 session 对话。
- Phase 1.5：可编辑该讲「家庭笔记」（注入 prompt，仍非 RAG）。

### 3.2 Agent 人格（Prompt 要点）

- 身份：高思风格的 **思维教练**，不是刷题机器。
- 答疑：苏格拉底式——先问「你怎么想的？」，再给一步提示。
- 出题：情境题、图形题（文字描述）；**不声称题目来自原书**。
- 一年级约束：句子短、少术语；必要时用类比或 emoji。
- 安全：话题限定数学学习；不确定时诚实说「我们一起再想想」。

### 3.3 版权边界

- **不存储、不传播** 高思课本原文、扫描件或盗版电子版。
- MVP 仅保存 **讲次元数据**（序号、标题、专题分类）。
- Phase 2 若做 RAG，只索引 **家长自写的要点/错题摘要**。

---

## 4. 课程数据（一年级上册 · 21 讲）

静态 JSON：`backend/data/curriculum/grade1-upper.json`

| 讲 | 标题 | 专题 |
|----|------|------|
| 1 | 简单的比较 | 应用题 |
| 2 | 位置 | 组合 |
| 3 | 拼图游戏 | 几何 |
| 4 | 立体图形的初步认识 | 几何 |
| 5 | 加与减 | 计算 |
| 6 | 简单的找规律 | 计算 |
| 7 | 生活中的可能性 | 计数 |
| 8 | 分类 | 组合 |
| 9 | 用工具比较 | 应用题 |
| 10 | 找路线走一走 | 组合 |
| 11 | 多角度观察初步 | 几何 |
| 12 | 有趣的骰子 | 组合 |
| 13 | 基数与序数 | 应用题 |
| 14 | 图文算式 | 数字谜 |
| 15 | 图形规律初步 | 计算 |
| 16 | 简单的数图形 | 计数 |
| 17 | 角的初步认识 | 几何 |
| 18 | 加减法竖式 | 计算 |
| 19 | 单位换算 | 应用题 |
| 20 | 钟面数学初步 | 组合 |
| 21 | 趣题巧解 | 组合 |

**JSON 字段示例：**

```json
{
  "grade": "1",
  "volume": "upper",
  "lessons": [
    {
      "id": 5,
      "title": "加与减",
      "topic": "计算",
      "family_notes": ""
    }
  ]
}
```

---

## 5. 技术架构

### 5.1 总览

```
┌──────────────┐   SSE    ┌─────────────────────────────────┐
│  Vue 前端     │ ◄──────► │  FastAPI                         │
│  ChildChat   │          │  POST /api/chat/stream           │
│  ParentPanel │          │  GET  /api/lessons               │
└──────────────┘          │  PATCH /api/lessons/{id}/notes   │
                          │         │                        │
                          │    agent/loop.py                 │
                          │         │                        │
                          │    tools.py                      │
                          │    ├ list_lessons                │
                          │    ├ get_lesson_context          │
                          │    ├ generate_practice           │
                          │    └ evaluate_answer             │
                          │         │                        │
                          │    llm.py → DeepSeek API         │
                          └─────────┬────────────────────────┘
                                    │
                          ┌─────────▼─────────┐
                          │ MySQL gaosi_tutor  │
                          │ tutor_sessions     │
                          │ tutor_messages     │
                          │ practice_records   │
                          │ lesson_progress    │
                          └───────────────────┘
```

### 5.2 从 MES 复用的模块

| MES 文件/模式 | gaosi-tutor 对应 | 说明 |
|---------------|------------------|------|
| `agent/loop.py` | 同结构 | tool 循环 + 流式 |
| `agent/llm.py` | 同结构 | `chat` / `chat_stream` |
| `agent/router.py` | 精简版 | 去掉 confirm、traces（Phase 1） |
| `agent/session_store.py` | 改名 `tutor_session_store` | 表名调整 |
| `database.py` + `settings.py` | 同模式 | `DATABASE_URL` 指向 `gaosi_tutor` |
| `AgentChat.vue` | 拆为 Child + Parent | SSE 打字机保留 |

### 5.3 不搬的内容

- MES 业务表与 `services.py`
- RAG（`agent/rag/`）
- 写操作确认门（`confirm_store`）
- `agent_traces`（Phase 2 可选）

### 5.4 Agent Tools（MVP · 4 个）

| Tool | 参数 | 作用 |
|------|------|------|
| `list_lessons` | — | 返回 21 讲列表 |
| `get_lesson_context` | `lesson_id` | 标题、专题、家庭笔记 |
| `generate_practice` | `lesson_id`, `difficulty` | 生成 1 道题（interest / extend） |
| `evaluate_answer` | `lesson_id`, `question`, `student_answer` | 判对错 + 分步反馈（JSON） |

**练习对话流：**

```
孩子：「出题」
  → generate_practice(lesson_id=5, difficulty="interest")
  → Agent 展示题目

孩子：「答案是 8」
  → evaluate_answer(...)
  → 对：鼓励；错：只提示一步
```

### 5.5 数据库表（MySQL）

**库名：** `gaosi_tutor`  
**连接（本地默认）：** `mysql+pymysql://root:root1234@127.0.0.1:3306/gaosi_tutor?charset=utf8mb4`

| 表 | 用途 |
|----|------|
| `tutor_sessions` | 对话 session（含 `mode`: child/parent、`lesson_id`） |
| `tutor_messages` | 消息历史（role, content, tool_calls） |
| `practice_records` | 出题与作答记录（Phase 1 写入，Phase 2 做学情） |
| `lesson_progress` | 当前学到第几讲、家庭笔记（可 JSON 或独立列） |

与 MES 共用同一 MySQL 实例、**不同 database**，互不干扰。

### 5.6 配置

`backend/config/.env`：

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DATABASE_URL=mysql+pymysql://root:root1234@127.0.0.1:3306/gaosi_tutor?charset=utf8mb4
```

---

## 6. 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | ChildChat | 孩子主界面：大按钮 + 聊天气泡 |
| `/parent` | ParentPanel | 选讲次、难度、模式切换、笔记编辑 |

**孩子模式 UI 要点**

- 字体 ≥ 18px，主色活泼（可与高思风格接近但不抄品牌资产）。
- 固定快捷按钮，减少打字。
- 不暴露 API Key、模型名等技术信息。

**家长模式 UI 要点**

- 讲次下拉（1～21 讲 + 标题）。
- 难度：兴趣 / 拓展。
- 「切换到孩子模式」一键跳转。

---

## 7. 分期计划

### Phase 1 — 能陪学（目标 2～3 周）

- [ ] 初始化 repo：`gaosi-tutor`
- [ ] `docker-compose.yml`：MySQL（库 `gaosi_tutor`）+ 可选 Adminer
- [ ] FastAPI 脚手架 + DeepSeek + 4 tools
- [ ] `grade1-upper.json` 21 讲元数据
- [ ] 双 system prompt（child / parent）
- [ ] Vue：ChildChat + ParentPanel + SSE
- [ ] MySQL session / messages
- [ ] `Makefile`：`make start` / `make init-db`
- [ ] 冒烟脚本：选讲 → 出题 → 作答 → 反馈

### Phase 1.5 — 家庭笔记

- [ ] 家长编辑 `family_notes`（PATCH API + 表单）
- [ ] `practice_records` 落库

### Phase 2 — 学情 + 知识增强

- [ ] 正确率、薄弱讲次、复习建议（家长报表）
- [x] 自整理要点 RAG（非原书）— `search_family_notes` + Chroma
- [x] 语音输入（Web Speech API，孩子模式识别后自动发送）
- [x] 语音播报（Speech Synthesis，孩子模式自动朗读回复，可静音）
- [x] **配图出题**：几何/空间题返回 diagram 规范，前端 SVG 渲染（非 AI 生图）

---

## 8. 项目结构

```
gaosi-tutor/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── loop.py
│   │   │   ├── llm.py
│   │   │   ├── tools.py
│   │   │   ├── prompts.py
│   │   │   ├── router.py
│   │   │   └── session_store.py
│   │   ├── curriculum/
│   │   │   └── loader.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── settings.py
│   │   └── main.py
│   ├── data/curriculum/
│   │   └── grade1-upper.json
│   ├── config/.env.example
│   └── requirements.txt
├── frontend/
│   └── src/views/
│       ├── ChildChat.vue
│       └── ParentPanel.vue
├── docs/
│   └── design.md          ← 本文档
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## 9. 风险与对策

| 风险 | 对策 |
|------|------|
| LLM 算错数学题 | `evaluate_answer` 要求分步推理；鼓励孩子验算 |
| 题目风格偏离高思 | Prompt 强调情境与思维；Phase 2 加家庭笔记 |
| 版权 | 仅存元数据；不导入原书 PDF/Word |
| 一年级打字困难 | MVP 家长代输入 + 快捷按钮；Phase 2 语音 |
| 与 MES 抢 3306 端口 | 共用实例不同库；或 compose 改端口 |

---

## 10. 本地开发命令（规划）

```bash
# 启动 MySQL
docker compose up -d

# 初始化库表 + 灌入 curriculum
make init-db

# 后端 + 前端
make start

# 冒烟
make smoke
```

---

## 11. 确认记录

| 项 | 确认值 |
|----|--------|
| 方案 | 方案 1，MySQL（非 SQLite） |
| 项目名 | gaosi-tutor |
| LLM | DeepSeek |
| 动机 | 贴近家庭陪学，比 MES 业务更易持续使用 |

---

## 12. 下一步

1. 用户审阅本文档  
2. 编写 Phase 1 实施计划（逐步 scaffold + 从 MES 迁移 Agent 核心）  
3. 在本机创建仓库并跑通第一条对话
