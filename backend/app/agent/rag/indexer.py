"""
家庭笔记索引管线（RAG Index：MySQL → 切块 → Embedding → Chroma）。

数据流：
  lesson_progress.family_notes (MySQL)
    → chunk_family_note()
    → embed_texts()
    → upsert_chunks() / delete_lesson_chunks()

触发时机：
- 家长 PATCH /api/lessons/{id}/notes 保存笔记
- POST /api/rag/index 全量同步
- POST /api/rag/index/{lesson_id} 单讲
- make rag-index / scripts/smoke_rag.py

db 参数：SQLAlchemy Session，只读 MySQL；Chroma 写入在 store 模块。

详见 docs/agent-rag.md §7。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .bm25_index import invalidate_bm25_cache
from ...curriculum.loader import get_lesson_meta, list_lessons
from ...models import LessonProgress
from .chunker import chunk_family_note
from .embedder import embed_texts
from .store import (
    count_chunks,
    delete_lesson_chunks,
    get_chroma_path,
    list_indexed_lesson_ids,
    upsert_chunks,
)


def _lesson_notes_rows(db: Session) -> list[tuple[int, str, str, str]]:
    """
    汇总「有内容」的家庭笔记行，供全量索引与统计。

    返回：(lesson_id, title, topic, notes_text)
    - MySQL：一次 query 全部 lesson_progress
    - 静态 JSON：list_lessons() 提供标题/专题
    - 只保留 notes 非空的讲次
    """
    notes_map = {
        row.lesson_id: (row.family_notes or "").strip()
        for row in db.query(LessonProgress).all()
    }
    rows: list[tuple[int, str, str, str]] = []
    for lesson in list_lessons():
        lesson_id = lesson["id"]
        notes = notes_map.get(lesson_id, "").strip()
        if notes:
            rows.append((lesson_id, lesson["title"], lesson["topic"], notes))
    return rows


def index_lesson_notes(db: Session, lesson_id: int) -> dict:
    """
    单讲索引：删旧 chunk → 切块 → embed → upsert。

    笔记为空：只 delete_lesson_chunks，返回 chunks_indexed=0。
    笔记过短无法切块：同上。

    返回 dict 供 API 与 PATCH notes 响应里的 rag 字段使用。
    """
    meta = get_lesson_meta(lesson_id)
    if not meta:
        return {"ok": False, "error": f"讲次 {lesson_id} 不存在"}

    notes = (
        db.query(LessonProgress)
        .filter(LessonProgress.lesson_id == lesson_id)
        .first()
    )
    text = (notes.family_notes if notes else "") or ""
    text = text.strip()

    # 先清该讲旧向量，避免段落删改后残留
    delete_lesson_chunks(lesson_id)
    if not text:
        return {
            "ok": True,
            "lesson_id": lesson_id,
            "chunks_indexed": 0,
            "message": "笔记为空，已清除该讲索引",
        }

    chunks = chunk_family_note(
        lesson_id=lesson_id,
        title=meta["title"],
        topic=meta["topic"],
        notes=text,
    )
    if not chunks:
        return {
            "ok": True,
            "lesson_id": lesson_id,
            "chunks_indexed": 0,
            "message": "笔记过短，未生成 chunk",
        }

    vectors = embed_texts([c["text"] for c in chunks])
    n = upsert_chunks(chunks, vectors)
    invalidate_bm25_cache()
    return {"ok": True, "lesson_id": lesson_id, "chunks_indexed": n}


def index_all_notes(db: Session) -> dict:
    """
    全量索引：遍历所有有笔记的讲次，并清理「DB 已空但 Chroma 仍有」的残留。

    家长面板「同步知识库」、make rag-index 调用此函数。
    """
    rows = _lesson_notes_rows(db)
    total_chunks = 0
    lessons_indexed = 0

    for lesson_id, title, topic, notes in rows:
        delete_lesson_chunks(lesson_id)
        chunks = chunk_family_note(
            lesson_id=lesson_id,
            title=title,
            topic=topic,
            notes=notes,
        )
        if not chunks:
            continue
        vectors = embed_texts([c["text"] for c in chunks])
        total_chunks += upsert_chunks(chunks, vectors)
        lessons_indexed += 1

    # MySQL 笔记已清空的讲次，Chroma 里可能还有旧 chunk → 只删库里实际存在的
    lesson_ids_with_notes = {lesson_id for lesson_id, _, _, _ in rows}
    stale_lesson_ids = list_indexed_lesson_ids() - lesson_ids_with_notes
    for lesson_id in stale_lesson_ids:
        delete_lesson_chunks(lesson_id)

    invalidate_bm25_cache()
    return {
        "ok": True,
        "lessons_indexed": lessons_indexed,
        "chunks_indexed": total_chunks,
        "total_chunks": count_chunks(),
    }


def rag_stats(db: Session) -> dict:
    """
    RAG 健康/统计信息。

    notes_with_content：MySQL 中有非空笔记的讲次数
    chunks_in_store：Chroma 向量条数
    chroma_path：持久化目录（调试 / check_env 用）
    """
    rows = _lesson_notes_rows(db)
    return {
        "ok": True,
        "notes_with_content": len(rows),
        "chunks_in_store": count_chunks(),
        "chroma_path": str(get_chroma_path()),
    }
