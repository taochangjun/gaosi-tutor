"""初始化 MySQL 库 gaosi_tutor（若尚不存在）并建表。

SQLAlchemy 在本脚本中的三步：
1. make_url 解析连接串，拆出库名
2. 用无库名的 Engine 执行 CREATE DATABASE（Core 层原生 SQL）
3. Base.metadata.create_all 根据 models.py 建表
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.curriculum.loader import list_lessons, seed_lesson_progress
from app.database import Base, SessionLocal, engine
from app.settings import get_settings


def ensure_database():
    settings = get_settings()
    url = settings.database_url
    if "mysql" not in url:
        print("[init-db] 非 MySQL，跳过 CREATE DATABASE")
        return

    # make_url 把连接串解析为 URL 对象，便于改 database 段
    parsed = make_url(url)
    db_name = parsed.database
    # 连到 mysql 系统库，才有权限 CREATE DATABASE
    server_url = parsed.set(database="mysql")
    admin = create_engine(server_url)
    with admin.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        conn.commit()
    print(f"[init-db] 数据库 `{db_name}` 已就绪")


def main():
    ensure_database()
    # 扫描所有 Base 子类，CREATE TABLE IF NOT EXISTS
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = seed_lesson_progress(db)
        print(f"[init-db] 表已创建，讲次记录 +{n}，共 {len(list_lessons())} 讲")
    finally:
        db.close()
    print("[init-db] 完成")


if __name__ == "__main__":
    main()
