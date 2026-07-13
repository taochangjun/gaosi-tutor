from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TutorSession(Base):
    __tablename__ = "tutor_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), default="child")
    lesson_id: Mapped[int] = mapped_column(Integer, default=1)
    difficulty: Mapped[str] = mapped_column(String(20), default="interest")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    messages: Mapped[list["TutorMessage"]] = relationship(
        back_populates="session", order_by="TutorMessage.created_at"
    )


class TutorMessage(Base):
    __tablename__ = "tutor_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tutor_sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["TutorSession"] = relationship(back_populates="messages")


class LessonProgress(Base):
    __tablename__ = "lesson_progress"

    lesson_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PracticeRecord(Base):
    __tablename__ = "practice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lesson_id: Mapped[int] = mapped_column(Integer, index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="interest")
    question: Mapped[str] = mapped_column(Text)
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
