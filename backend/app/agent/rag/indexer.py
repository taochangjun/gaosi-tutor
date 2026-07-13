"""家庭笔记索引：MySQL → 切块 → Chroma。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...curriculum.loader import get_lesson_meta, list_lessons
from ...models import LessonProgress
from .chunker import chunk_family_note
from .embedder import embed_texts
from .store import count_chunks, delete_lesson_chunks, get_chroma_path, upsert_chunks


def _lesson_notes_rows(db: Session) -> list[tuple[int, str, str, str]]:
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
    return {"ok": True, "lesson_id": lesson_id, "chunks_indexed": n}


def index_all_notes(db: Session) -> dict:
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

    # 清除 DB 中已删空的讲次残留（遍历 1-21）
    indexed_ids = {lesson_id for lesson_id, _, _, _ in rows}
    for lesson in list_lessons():
        if lesson["id"] not in indexed_ids:
            delete_lesson_chunks(lesson["id"])

    return {
        "ok": True,
        "lessons_indexed": lessons_indexed,
        "chunks_indexed": total_chunks,
        "total_chunks": count_chunks(),
    }


def rag_stats(db: Session) -> dict:
    rows = _lesson_notes_rows(db)
    return {
        "ok": True,
        "notes_with_content": len(rows),
        "chunks_in_store": count_chunks(),
        "chroma_path": str(get_chroma_path()),
    }
