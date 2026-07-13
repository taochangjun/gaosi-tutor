"""
RAG 冒烟测试：走通 Index → Retrieve 全链路（不调 LLM）。

步骤：
  1. update_family_notes  — 写 MySQL
  2. chunk_family_note    — 验证切块
  3. index_lesson_notes   — 单讲写入 Chroma
  4. index_all_notes      — 全量同步
  5. search_family_notes  — 语义检索断言

运行：make smoke-rag  或  python scripts/smoke_rag.py --lesson 5
首次运行会下载 fastembed 模型。
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.rag.chunker import chunk_family_note
from app.agent.rag.indexer import index_all_notes, index_lesson_notes
from app.agent.rag.retriever import search_family_notes
from app.curriculum.loader import update_family_notes
from app.database import SessionLocal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lesson", type=int, default=5)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        sample = (
            "孩子减法还不太熟练，尤其是借位。\n"
            "平时喜欢用小动物情境出题，多鼓励。"
        )
        update_family_notes(db, args.lesson, sample)
        print(f"[OK] 写入第 {args.lesson} 讲测试笔记")

        chunks = chunk_family_note(
            lesson_id=args.lesson,
            title="加与减",
            topic="计算",
            notes=sample,
        )
        assert len(chunks) >= 1, "切块失败"
        print(f"[OK] 切块 {len(chunks)} 段")

        one = index_lesson_notes(db, args.lesson)
        assert one.get("ok") and one.get("chunks_indexed", 0) >= 1
        print(f"[OK] 单讲索引 chunks={one['chunks_indexed']}")

        all_out = index_all_notes(db)
        assert all_out.get("ok")
        print(
            f"[OK] 全量索引 lessons={all_out.get('lessons_indexed')} "
            f"chunks={all_out.get('total_chunks')}"
        )

        hit = search_family_notes(
            db, "孩子减法哪里薄弱", lesson_id=args.lesson
        )
        assert hit.get("ok") and hit.get("count", 0) >= 1
        top = hit["hits"][0]
        print(f"[OK] 检索命中 score={top['score']} snippet={top['snippet'][:40]}…")
    finally:
        db.close()


if __name__ == "__main__":
    main()
