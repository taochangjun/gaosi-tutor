# gaosi-tutor

高思竞赛数学课本 · **一年级上册** 陪学 Agent（答疑 + 出题练习）。

## 快速开始

```bash
# 1. 配置 API Key
cp backend/config/.env.example backend/config/.env
# 编辑 DEEPSEEK_API_KEY

# 2. 安装依赖
make install

# 3. 启动 MySQL（独立容器，端口 3307）
make db-up

# 若共用 MES 的 MySQL（3306），改 .env 里 DATABASE_URL 端口为 3306 即可

# 4. 初始化库表
make init-db

# 5. 检查环境
make check

# 6. 启动
make start
```

- 孩子模式：http://localhost:5173/（**语音输入 + 语音播报**，Chrome 推荐）
- 家长模式：http://localhost:5173/parent
- API 文档：http://localhost:8000/docs

## 冒烟测试

```bash
make smoke          # 不调 LLM，验证 21 讲目录
make smoke-llm      # 需 API Key，测出题链路
make smoke-rag      # RAG：切块 → 索引 → 检索（首次会下载 Embedding 模型）
make rag-index      # 全量同步家庭笔记到向量库
```

## 文档

- [设计文档](./docs/design.md)
- [前端代码详解](./docs/frontend-guide.md) — Vue、SSE、语音、双模式页面
- [家庭笔记 RAG](./docs/agent-rag.md) — 切块、索引、检索与 Agent 配合
- [Python 基础](./docs/python-basics-learning.md) — 类型注解、`*` 关键字参数、`yield` 等
- [FastEmbed 学习](./docs/fastembed-learning.md) · [Chroma 学习](./docs/chroma-learning.md) · [向量数据库学习](./docs/vector-db-learning.md) · [SQLAlchemy 学习](./docs/sqlalchemy-learning.md)
- [Agent 学习路线](./docs/agent-learning-path.md) — 以读懂、改好本项目为主线
- [Agent 求职路线](./docs/agent-job-roadmap.md) — 对标 BOSS 直聘招聘要求（含 RAG/LangChain/LangGraph）
- [企业级 RAG 分析与开发路线](./docs/enterprise-rag-roadmap.md) — 基于学堂在线 chat-test 项目提炼

## 技术栈

FastAPI · Vue 3 · MySQL · DeepSeek · 手写 Agent loop

## 与 MES 的关系

独立仓库，复用 [MES Demo](../mes) 的 Agent 工程模式，业务完全无关。
