# 工程化指南 — SanyMES Demo

> 部署、CI、环境检查、评估回归与日常运维命令。

---

## 目录

1. [环境要求](#1-环境要求)
2. [首次部署](#2-首次部署)
3. [日常命令（Makefile）](#3-日常命令makefile)
4. [健康检查](#4-健康检查)
5. [CI 流水线](#5-ci-流水线)
6. [Agent 评估回归](#6-agent-评估回归)
7. [Docker MySQL](#7-docker-mysql)
8. [故障排查](#8-故障排查)

---

## 1. 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| MySQL | 8.0+ |
| Docker | 可选（本地 MySQL） |

---

## 2. 首次部署

```bash
# 1. 配置环境变量
cp backend/config/.env.example backend/config/.env
# 编辑 .env：填入 DEEPSEEK_API_KEY，确认 DATABASE_URL

# 2. 创建 MySQL 库（若尚未创建）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS mes CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 或使用 Docker
make db-up

# 3. 安装依赖 + 检查
make install
make check

# 4. 启动
make start
# 或 ./start.sh
```

访问：

- 前端 http://localhost:5173
- API 文档 http://localhost:8000/docs
- AI 助手 http://localhost:5173/agent-chat

---

## 3. 日常命令（Makefile）

```bash
make help        # 命令列表
make check       # 环境检查（DB + API Key）
make eval        # Agent dry 评估（~2s，不调 LLM）
make eval-llm    # Agent 完整 10 问（需 API Key，~40s）
make db-up       # Docker 启动 MySQL
make db-down     # 停止 MySQL 容器
make start       # 一键启动
```

---

## 4. 健康检查

```bash
curl http://localhost:8000/api/health | python3 -m json.tool
```

响应示例：

```json
{
  "status": "ok",
  "database": "ok",
  "agent": "ok",
  "lessons": 21,
  "rag": "ok",
  "rag_chunks": 12
}
```

| 字段 | 含义 |
|------|------|
| `database` | MySQL 连接（`SELECT 1`） |
| `agent` | `ok` 或 `missing_api_key` |
| `rag` | Chroma / RAG 模块是否可用 |
| `rag_chunks` | 向量库中的笔记片段数 |
| `status` | `ok` 正常；`degraded` 表示数据库或 RAG 异常 |

---

## 5. CI 流水线

文件：`.github/workflows/ci.yml`

每次 push / PR 自动执行：

| Job | 内容 |
|-----|------|
| **backend** | MySQL 服务容器 → 安装依赖 → 语法检查 → `check_env` → `agent_eval --dry` |
| **frontend** | `npm ci` → `npm run build` |

CI **不调用 LLM**（无 API Key 成本）。完整评估在本地或 nightly 手动跑：

```bash
make eval-llm
```

---

## 6. Agent 评估回归

改 prompt / tools / loop 后必跑：

```bash
cd backend
./venv/bin/python -m scripts.agent_eval --dry     # 快速
./venv/bin/python -m scripts.agent_eval         # 完整（你已通过 10/10）
./venv/bin/python -m scripts.agent_eval --list  # 列出用例
./venv/bin/python -m scripts.agent_eval --case create_preview
```

查看请求 trace：

```bash
curl http://localhost:8000/api/agent/traces | python3 -m json.tool
```

MySQL：

```sql
USE mes;
SELECT endpoint, LEFT(question,40), total_ms, status, llm_turns
FROM agent_traces ORDER BY id DESC LIMIT 10;
```

---

## 7. Docker MySQL

```bash
docker compose up -d      # MySQL :3306 + Adminer :8080
docker compose down       # 停止
docker compose down -v    # 停止并删数据卷
```

Adminer 登录：http://localhost:8080

- 系统：MySQL
- 服务器：`mysql`（容器内）或 `host.docker.internal` / `127.0.0.1`
- 用户名：`root`
- 密码：`root1234`
- 数据库：`mes`

---

## 8. 故障排查

| 现象 | 处理 |
|------|------|
| `数据库连接失败` | 确认 MySQL 已启动；检查 `DATABASE_URL` |
| Agent 无响应 | `make check` 看 API Key；启动日志 `[WARN] DEEPSEEK_API_KEY` |
| 确认弹窗不出现 | 重启后端；查 `agent_traces` 是否调用了写操作工具 |
| eval LLM 失败 | 网络 / API Key / 模型名；单跑 `--case xxx` 定位 |
| 前端 build 失败 | `cd frontend && npm ci && npm run build` |

---

> 后续演进（Agent 框架、RAG 升级、Langfuse 等）：[agent-evolution.md](./agent-evolution.md)
