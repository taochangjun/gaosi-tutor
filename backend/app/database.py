"""
数据库连接与 Session 工厂（SQLAlchemy 核心入口）。

本模块负责三件事：
1. Engine（引擎）—— 管理与数据库的底层连接池
2. Base（声明式基类）—— 所有 ORM 模型（见 models.py）都继承它
3. SessionLocal / get_db —— 创建「工作单元」Session，供业务代码读写数据

推荐阅读顺序：先看 docs/sqlalchemy-learning.md，再对照 models.py 与 session_store.py。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .settings import get_settings


def _make_engine():
    """
    根据 DATABASE_URL 创建 Engine。

    Engine 是 SQLAlchemy 的「连接管理器」：
    - 维护连接池，复用 TCP 连接，避免每次查询都重新握手
    - 把 Python 对象操作翻译成 SQL 并发送给数据库
    - 本身不保存业务状态；真正干活的是 Session
    """
    url = get_settings().database_url

    if url.startswith("sqlite"):
        # SQLite 默认只允许创建它的线程访问连接。
        # FastAPI 用线程池处理请求，需要关闭此限制。
        return create_engine(url, connect_args={"check_same_thread": False})

    # MySQL / PostgreSQL 等网络数据库：
    # pool_pre_ping：借出连接前先 ping，丢弃已断开的连接
    # pool_recycle：3600 秒后回收连接，避免 MySQL wait_timeout 导致僵死连接
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


# 全局单例 Engine，进程启动时创建一次，整个应用共享连接池
engine = _make_engine()

# sessionmaker 是 Session 的「工厂函数」。
# 调用 SessionLocal() 会得到一个新的 Session 实例。
#
# autocommit=False：不自动提交；必须显式 db.commit() 才持久化（推荐，便于回滚）
# autoflush=False：不自动 flush；减少隐式 SQL，由 commit() 或手动 flush() 触发
# bind=engine：该 Session 使用上面创建的 engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    声明式 ORM 基类（SQLAlchemy 2.0 风格）。

    所有模型类（TutorSession、TutorMessage 等）继承 Base 后：
    - 类属性会映射为数据库表列
    - Base.metadata 收集所有表结构，供 create_all() 建表使用
    """

    pass


def get_db():
    """
    FastAPI 依赖注入用的 Session 生成器（generator）。

    用法（在 router 中）：
        def my_api(db: Session = Depends(get_db)):
            db.query(...)

    生命周期：
    1. 请求进入 → yield 之前：创建 Session
    2. 路由函数执行：使用 db 做查询/写入
    3. 请求结束 → finally：db.close() 归还连接到池

    注意：generator 形式的依赖保证「一个 HTTP 请求 = 一个 Session」，
    避免多请求共享 Session 导致数据错乱或连接泄漏。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
