"""课程目录加载与家庭笔记（JSON 静态数据 + SQLAlchemy 读写 lesson_progress）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import LessonProgress

CURRICULUM_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "curriculum" / "grade1-upper.json"
)


@lru_cache()
def load_curriculum() -> dict:
    with CURRICULUM_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def list_lessons() -> list[dict]:
    return load_curriculum()["lessons"]


def get_lesson_meta(lesson_id: int) -> dict | None:
    for lesson in list_lessons():
        if lesson["id"] == lesson_id:
            return lesson
    return None


def get_family_notes(db: Session, lesson_id: int) -> str:
    """按讲次主键查询家庭笔记；无记录返回空字符串。"""
    row = db.query(LessonProgress).filter(LessonProgress.lesson_id == lesson_id).first()
    return row.family_notes if row else ""


def get_lesson_context(db: Session, lesson_id: int) -> dict:
    """合并静态课程元数据 + DB 中的 family_notes。"""
    meta = get_lesson_meta(lesson_id)
    if not meta:
        return {"ok": False, "error": f"讲次 {lesson_id} 不存在"}
    notes = get_family_notes(db, lesson_id)
    return {
        "ok": True,
        "id": meta["id"],
        "title": meta["title"],
        "topic": meta["topic"],
        "grade": load_curriculum()["grade"],
        "volume": load_curriculum()["volume"],
        "family_notes": notes,
    }


def update_family_notes(db: Session, lesson_id: int, notes: str) -> dict:
    """
    UPSERT 语义：有则 UPDATE family_notes，无则 INSERT 新行。
    """
    if not get_lesson_meta(lesson_id):
        return {"ok": False, "error": f"讲次 {lesson_id} 不存在"}
    row = db.query(LessonProgress).filter(LessonProgress.lesson_id == lesson_id).first()
    if row:
        row.family_notes = notes
    else:
        db.add(LessonProgress(lesson_id=lesson_id, family_notes=notes))
    db.commit()
    return {"ok": True, "lesson_id": lesson_id, "family_notes": notes}


def seed_lesson_progress(db: Session) -> int:
    """
    启动时种子数据：为 JSON 目录中尚未入库的讲次各插入一行空笔记。
    返回本次新建的行数。
    """
    created = 0
    for lesson in list_lessons():
        exists = (
            db.query(LessonProgress)
            .filter(LessonProgress.lesson_id == lesson["id"])
            .first()
        )
        if not exists:
            db.add(LessonProgress(lesson_id=lesson["id"], family_notes=""))
            created += 1
    db.commit()
    return created
