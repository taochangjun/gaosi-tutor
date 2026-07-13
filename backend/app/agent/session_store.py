"""对话 Session 持久化（SQLAlchemy ORM 读写 tutor_sessions / tutor_messages）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import TutorMessage, TutorSession

HISTORY_LIMIT = 12


def get_or_create_session(
    db: Session,
    session_id: str | None,
    *,
    mode: str = "child",
    lesson_id: int = 1,
    difficulty: str = "interest",
) -> str:
    """
    按 session_id 查找会话；不存在则新建。

    db: Session —— 由调用方传入，本函数内完成 commit，不负责 close。
    """
    if session_id:
        # SELECT ... WHERE id = ? LIMIT 1
        row = db.query(TutorSession).filter(TutorSession.id == session_id).first()
        if row:
            # ORM 脏检查：改属性后 commit 会生成 UPDATE
            row.mode = mode
            row.lesson_id = lesson_id
            row.difficulty = difficulty
            row.updated_at = datetime.utcnow()
            db.commit()
            return session_id

    sid = str(uuid.uuid4())
    # INSERT：add 把新对象挂到 Session，commit 时才真正写入
    db.add(
        TutorSession(
            id=sid,
            mode=mode,
            lesson_id=lesson_id,
            difficulty=difficulty,
        )
    )
    db.commit()
    return sid


def load_history(db: Session, session_id: str, limit: int = HISTORY_LIMIT) -> list[dict]:
    """
    加载最近 N 条消息，按时间正序返回（供拼进 LLM messages）。

    分两步查询：先取最新 N 个 id，再 IN 查询完整行（避免 ORDER BY + LIMIT 后顺序错乱）。
    """
    recent_ids = [
        row[0]
        for row in (
            db.query(TutorMessage.id)
            .filter(TutorMessage.session_id == session_id)
            .order_by(TutorMessage.id.desc())
            .limit(limit)
            .all()
        )
    ]
    if not recent_ids:
        return []

    rows = (
        db.query(TutorMessage)
        .filter(TutorMessage.id.in_(recent_ids))
        .order_by(TutorMessage.id.asc())
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def append_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
) -> None:
    """插入一条消息，并刷新所属 session 的 updated_at。"""
    db.add(
        TutorMessage(
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=(
                json.dumps(tool_calls, ensure_ascii=False, default=str)
                if tool_calls
                else None
            ),
        )
    )
    session = db.query(TutorSession).filter(TutorSession.id == session_id).first()
    if session:
        session.updated_at = datetime.utcnow()
    db.commit()
