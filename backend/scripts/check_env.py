"""环境检查。"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.curriculum.loader import list_lessons
from app.database import SessionLocal
from app.settings import get_settings


def main():
    settings = get_settings()
    ok = True

    print("=== gaosi-tutor 环境检查 ===\n")

    if settings.deepseek_api_key:
        print("[OK] DEEPSEEK_API_KEY 已配置")
    else:
        print("[WARN] DEEPSEEK_API_KEY 未配置 — 复制 config/.env.example → config/.env")
        ok = False

    print(f"[INFO] DATABASE_URL = {settings.database_url}")

    try:
        # SessionLocal + text("SELECT 1")：验证 Engine 连接池与数据库可达
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        lessons = len(list_lessons())
        print(f"[OK] MySQL 连接成功，课程 {lessons} 讲")
        db.close()
    except Exception as exc:
        print(f"[FAIL] MySQL: {exc}")
        print("       提示: make db-up && make init-db")
        ok = False

    try:
        from app.agent.rag.indexer import rag_stats

        # 第二次独立 Session：脚本场景手动管理生命周期
        db = SessionLocal()
        stats = rag_stats(db)
        db.close()
        print(
            f"[OK] RAG 模块可用，向量库 {stats.get('chunks_in_store', 0)} 条 "
            f"（有笔记 {stats.get('notes_with_content', 0)} 讲）"
        )
    except Exception as exc:
        print(f"[WARN] RAG: {exc}")
        print("       提示: make install（需 chromadb + fastembed）")

    print()
    if ok:
        print("环境就绪，可 make start")
    else:
        print("请先修复上述问题")
        sys.exit(1)


if __name__ == "__main__":
    main()
