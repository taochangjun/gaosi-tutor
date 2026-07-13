"""对话 Session 持久化。"""

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
    if session_id:
        row = db.query(TutorSession).filter(TutorSession.id == session_id).first()
        if row:
            row.mode = mode
            row.lesson_id = lesson_id
            row.difficulty = difficulty
            row.updated_at = datetime.utcnow()
            db.commit()
            return session_id

    sid = str(uuid.uuid4())
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
