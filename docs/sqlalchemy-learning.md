# SQLAlchemy 学习文档（基于 gaosi-tutor 项目）

> 面向第一次接触 SQLAlchemy 的开发者。文中示例均来自本仓库真实代码，可直接对照阅读。

## 目录

1. [SQLAlchemy 是什么](#1-sqlalchemy-是什么)
2. [核心概念速览](#2-核心概念速览)
3. [本项目的分层结构](#3-本项目的分层结构)
4. [Engine 与连接池](#4-engine-与连接池)
5. [Session：工作单元](#5-session工作单元)
6. [声明式模型（ORM）](#6-声明式模型orm)
7. [CRUD 操作实战](#7-crud-操作实战)
8. [关系映射 relationship](#8-关系映射-relationship)
9. [与 FastAPI 集成](#9-与-fastapi-集成)
10. [原生 SQL 与建表](#10-原生-sql-与建表)
11. [常见陷阱与最佳实践](#11-常见陷阱与最佳实践)
12. [本仓库文件索引](#12-本仓库文件索引)
13. [延伸阅读](#13-延伸阅读)

---

## 1. SQLAlchemy 是什么

SQLAlchemy 是 Python 最流行的数据库工具库，提供两层能力：

| 层次 | 作用 | 本项目用法 |
|------|------|-----------|
| **Core** | 连接管理、SQL 表达式、事务 | `create_engine`、`text("SELECT 1")` |
| **ORM** | 用 Python 类映射数据库表 | `models.py` 里的 `TutorSession` 等 |

可以把它理解成：**Engine 管连接，Session 管事务，Model 管表结构，query/add/commit 管数据读写**。

---

## 2. 核心概念速览

```
┌─────────────┐     bind      ┌─────────────┐
│  Session    │ ──────────────▶│   Engine    │
│ （工作单元）  │                │ （连接池）    │
└──────┬──────┘                └──────┬──────┘
       │ 操作 ORM 对象                   │ TCP 连接
       ▼                               ▼
┌─────────────┐                ┌─────────────┐
│   Model     │   映射为        │   MySQL     │
│ TutorSession│ ──────────────▶│ tutor_sessions│
└─────────────┘                └─────────────┘
```

| 概念 | 一句话解释 |
|------|-----------|
| **Engine** | 数据库连接的工厂 + 连接池，进程级单例 |
| **Session** | 一次业务操作的上下文，跟踪对象的增删改，管理事务 |
| **Base / Model** | Python 类 ↔ 数据库表的映射定义 |
| **Query** | 用 Python 链式 API 构造 SELECT（`db.query(Model).filter(...)`） |
| **commit** | 把 Session 里暂存的变更真正写入数据库 |
| **flush** | 把变更发给数据库但不提交事务（通常 commit 前自动 flush） |

---

## 3. 本项目的分层结构

```
backend/app/
├── database.py          ← Engine、SessionLocal、Base、get_db（入口）
├── models.py            ← 四张表的 ORM 定义
├── main.py              ← 启动时 create_all 建表
├── curriculum/loader.py ← 读写信 lesson_progress
├── agent/
│   ├── session_store.py ← tutor_sessions / tutor_messages CRUD
│   ├── tools.py         ← practice_records 写入
│   ├── router.py        ← FastAPI Depends(get_db) 注入 Session
│   └── rag/indexer.py   ← 从 lesson_progress 读笔记做索引
└── scripts/
    ├── init_db.py       ← CREATE DATABASE + create_all
    └── check_env.py     ← SELECT 1 探活
```

数据流示例（用户发一条聊天）：

```
POST /api/chat/stream
  → SessionLocal() 或 Depends(get_db) 创建 db
  → get_or_create_session(db, ...)     # SELECT / INSERT tutor_sessions
  → load_history(db, sid)              # SELECT tutor_messages
  → append_message(db, ...)            # INSERT tutor_messages + commit
  → execute_tool(..., db)              # 可能 INSERT practice_records
  → db.close()                         # 归还连接
```

---

## 4. Engine 与连接池

**文件：** `backend/app/database.py`

```python
engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
```

- `create_engine(url)` 解析连接字符串，例如：
  `mysql+pymysql://user:pass@localhost:3306/gaosi_tutor`
- 不会立刻连数据库，而是在**第一次需要连接时**才建立。
- `pool_pre_ping`：从池里取连接前先 `SELECT 1`，避免用到已被 MySQL 踢掉的死连接。
- `pool_recycle=3600`：连接使用超过 1 小时就回收重建。

SQLite 特殊参数 `check_same_thread=False`：允许多线程共用连接（FastAPI 默认用线程池）。

---

## 5. Session：工作单元

### 5.1 创建 Session

```python
from app.database import SessionLocal

db = SessionLocal()   # 新建一个 Session
try:
    # ... 业务逻辑 ...
    db.commit()       # 成功则提交
except:
    db.rollback()     # 出错可回滚（本项目多数地方未显式 rollback）
finally:
    db.close()        # 必须关闭，否则连接泄漏
```

### 5.2 Session 里发生了什么

1. **查询**：`db.query(TutorSession).filter(...).first()` → 生成 SQL → 返回 ORM 对象或 `None`
2. **新增**：`db.add(TutorSession(...))` → 对象进入 Session 的「待写入」列表
3. **修改**：`row.mode = "parent"` → Session 跟踪到对象属性变化（dirty）
4. **提交**：`db.commit()` → flush（发 SQL）→ COMMIT 事务

### 5.3 两种获取 Session 的方式

| 方式 | 场景 | 代码位置 |
|------|------|---------|
| `Depends(get_db)` | 普通 HTTP 路由，请求结束自动 close | `router.py` 大部分接口 |
| 手动 `SessionLocal()` | SSE 流式 generator 内自建 Session | `router.py` → `chat_stream` |

流式接口不能复用外层 `Depends(get_db)` 的 Session，因为 generator 执行时请求上下文可能已结束，所以：

```python
def event_generator():
    db = SessionLocal()
    try:
        ...
    finally:
        db.close()
```

---

## 6. 声明式模型（ORM）

**文件：** `backend/app/models.py`

SQLAlchemy 2.0 风格三件套：

```python
class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), default="child")
```

| 写法 | 含义 |
|------|------|
| `Mapped[str]` | 这一列在 Python 里是 `str` |
| `mapped_column(String(36), ...)` | 数据库列类型 VARCHAR(36) |
| `primary_key=True` | 主键 |
| `default="child"` | INSERT 时默认值 |
| `nullable=True` | 允许 NULL |
| `ForeignKey("tutor_sessions.id")` | 外键约束 |
| `index=True` | 建索引加速查询 |

继承 `Base` 后，模型类自动注册到 `Base.metadata`，供建表使用。

---

## 7. CRUD 操作实战

以下均来自 `session_store.py`、`loader.py`、`tools.py`。

### 7.1 Create（插入）

```python
db.add(TutorSession(id=sid, mode=mode, lesson_id=lesson_id))
db.commit()
```

`add()` 不会立刻 INSERT，要等 `commit()`（或 `flush()`）才发 SQL。

插入后若需要数据库生成的 id：

```python
db.add(record)
db.commit()
db.refresh(record)   # 重新 SELECT，拿到自增 id
print(record.id)
```

### 7.2 Read（查询）

**查单条：**

```python
row = db.query(TutorSession).filter(TutorSession.id == session_id).first()
```

- `.filter(条件)` 相当于 SQL `WHERE`
- `.first()` 返回第一条或 `None`
- `.all()` 返回列表

**查多列 / 子查询：**

```python
recent_ids = [
    row[0]
    for row in db.query(TutorMessage.id)
        .filter(TutorMessage.session_id == session_id)
        .order_by(TutorMessage.id.desc())
        .limit(12)
        .all()
]
```

**IN 查询：**

```python
db.query(TutorMessage).filter(TutorMessage.id.in_(recent_ids)).all()
```

**查全部：**

```python
for row in db.query(LessonProgress).all():
    ...
```

### 7.3 Update（更新）

ORM 对象是从 Session 查出来的「活对象」，改属性再 commit 即可：

```python
row = db.query(TutorSession).filter(TutorSession.id == session_id).first()
if row:
    row.mode = mode
    row.updated_at = datetime.utcnow()
    db.commit()
```

等价 SQL：`UPDATE tutor_sessions SET mode=?, updated_at=? WHERE id=?`

### 7.4 Delete（删除）

本项目暂未大量使用删除；标准写法：

```python
db.delete(row)
db.commit()
```

或批量：

```python
db.query(TutorMessage).filter(...).delete()
db.commit()
```

---

## 8. 关系映射 relationship

```python
# TutorSession 一侧（一对多）
messages: Mapped[list["TutorMessage"]] = relationship(
    back_populates="session", order_by="TutorMessage.created_at"
)

# TutorMessage 一侧（多对一）
session: Mapped["TutorSession"] = relationship(back_populates="messages")
```

- `relationship` **不创建数据库列**，外键靠 `ForeignKey` 那一列。
- 可以通过 `session.messages` 懒加载关联消息（注意 N+1 查询问题）。
- 本项目 `load_history` 选择直接查 `TutorMessage` 表，而不是走 `relationship`，更直观可控。

---

## 9. 与 FastAPI 集成

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db

@router.get("/lessons")
def lessons(db: Session = Depends(get_db)):
    row = db.query(LessonProgress).filter(...).first()
    ...
```

`Depends(get_db)` 做了什么：

1. 调用 `get_db()` 生成器，得到 `db`
2. 把 `db` 注入路由函数参数
3. 请求处理完毕后执行 `finally: db.close()`

类型注解 `db: Session` 仅为 IDE / 类型检查，运行时靠 Depends 注入。

---

## 10. 原生 SQL 与建表

### 10.1 执行原生 SQL

当 ORM 不合适时（健康检查、建库）：

```python
from sqlalchemy import text

db.execute(text("SELECT 1"))
```

`init_db.py` 建库：

```python
conn.execute(text(
    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
))
conn.commit()
```

### 10.2 自动建表

```python
from app.database import Base, engine

Base.metadata.create_all(bind=engine)
```

根据所有继承 `Base` 的模型创建**尚不存在**的表；**不会**删除或修改已有表结构。

生产环境更推荐 Alembic 做版本化迁移；本项目为学习/demo 规模，用 `create_all` 足够。

---

## 11. 常见陷阱与最佳实践

### ✅ 推荐

| 实践 | 原因 |
|------|------|
| 一个请求一个 Session | 避免并发写同一 Session |
| 用完 `db.close()` | 防止连接池耗尽 |
| 写操作后 `db.commit()` | `autocommit=False` 时否则数据不落库 |
| 用 `pool_pre_ping` | 长连接被服务端断开时自动恢复 |
| 外键列加 `index=True` | 按 session_id 查历史是热路径 |

### ❌ 避免

| 陷阱 | 后果 |
|------|------|
| 全局共用一个 Session | 多线程数据错乱 |
| 忘记 `commit()` | 数据「丢了」 |
| 在已 close 的 Session 上查询 | `DetachedInstanceError` |
| 在 generator 里用已关闭的 Depends Session | 流式接口常见 bug |
| 把 `create_all` 当迁移工具 | 改列类型/删列不会自动生效 |

### 事务简图

```
db.add / 修改属性
       ↓
   [Session 内存态]
       ↓  db.commit()
   flush → 发 INSERT/UPDATE SQL
       ↓
   COMMIT → 持久化
```

出错时可 `db.rollback()` 撤销本次事务内的所有变更。

---

## 12. 本仓库文件索引

| 文件 | SQLAlchemy 相关内容 |
|------|-------------------|
| `backend/app/database.py` | Engine、SessionLocal、Base、get_db |
| `backend/app/models.py` | 四张表 ORM 定义 |
| `backend/app/main.py` | `Base.metadata.create_all` 启动建表 |
| `backend/app/agent/session_store.py` | Session/Message 增删改查 |
| `backend/app/curriculum/loader.py` | LessonProgress 读写 |
| `backend/app/agent/tools.py` | PracticeRecord 插入与更新 |
| `backend/app/agent/router.py` | `Depends(get_db)`、健康检查 `SELECT 1` |
| `backend/app/agent/rag/indexer.py` | 读取 LessonProgress 做 RAG 索引 |
| `backend/scripts/init_db.py` | CREATE DATABASE + create_all |
| `backend/scripts/check_env.py` | 连接探活 |

---

## 13. 延伸阅读

- [SQLAlchemy 2.0 官方教程（英文）](https://docs.sqlalchemy.org/en/20/tutorial/)
- [ORM Quick Start](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- 本项目对话记忆设计：`docs/agent-production.md` 第 5 节 Session

### 建议动手练习

1. 用 `make init-db` 建表，MySQL 里 `\d tutor_sessions` 看表结构。
2. 在 `session_store.py` 的 `load_history` 加一行 `print(str(query))` 观察生成的 SQL（需改用 2.0 `select()` 或开启 echo）。
3. 临时把 `db.commit()` 注释掉，发一条聊天，刷新 DB —— 理解事务提交的必要性。
4. 打开 `database.py` 里 `create_engine(..., echo=True)`，看每条 SQL 日志。

---

*文档版本：与 gaosi-tutor SQLAlchemy 2.0.36 代码同步。*
