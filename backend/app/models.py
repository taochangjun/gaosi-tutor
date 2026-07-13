"""
ORM 模型定义（Object-Relational Mapping：对象 ↔ 数据库表）。

SQLAlchemy 2.0 推荐写法：
- Mapped[T]：标注 Python 侧类型，IDE 可推断 row.title 等属性
- mapped_column(...)：描述对应数据库列的类型、约束、默认值
- relationship(...)：描述表与表之间的关联（不建物理列，靠外键 join）

四张表的业务含义：
- tutor_sessions / tutor_messages：对话记忆（多轮聊天）
- lesson_progress：每讲的家庭笔记
- practice_records：出题与判题记录
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TutorSession(Base):
    """一次陪学会话（对应前端 localStorage 里的 session_id）。"""

    __tablename__ = "tutor_sessions"  # 实际 MySQL 表名

    # primary_key=True：主键，唯一标识一行
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), default="child")  # child | parent
    lesson_id: Mapped[int] = mapped_column(Integer, default=1)
    difficulty: Mapped[str] = mapped_column(String(20), default="interest")
    # default=datetime.utcnow：插入时若未赋值，由 Python 侧填当前时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # onupdate=...：每次 UPDATE 该行时自动刷新 updated_at
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # relationship：一对多，一个 Session 有多条 Message
    # back_populates：与 TutorMessage.session 双向关联
    # order_by：加载 messages 时按时间升序排列
    messages: Mapped[list["TutorMessage"]] = relationship(
        back_populates="session", order_by="TutorMessage.created_at"
    )


class TutorMessage(Base):
    """会话中的一条消息（user / assistant）。"""

    __tablename__ = "tutor_messages"

    # autoincrement=True：自增整数主键，插入时不必手动指定 id
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ForeignKey("tutor_sessions.id")：外键，指向 tutor_sessions 表
    # index=True：为该列建索引，按 session_id 查历史时更快
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tutor_sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)  # Text 适合长文本
    # nullable=True：允许 NULL；工具调用记录序列化为 JSON 字符串
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 多对一：多条 Message 属于一个 Session
    session: Mapped["TutorSession"] = relationship(back_populates="messages")


class LessonProgress(Base):
    """每讲的家庭笔记（家长面板编辑，Agent RAG 检索）。"""

    __tablename__ = "lesson_progress"

    # 用 lesson_id 作主键：每讲最多一行，天然唯一
    lesson_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PracticeRecord(Base):
    """练习题生成与作答评判记录（用于追踪薄弱点）。"""

    __tablename__ = "practice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # session_id 可为空：非对话场景单独出题时可能没有 session
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    lesson_id: Mapped[int] = mapped_column(Integer, index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="interest")
    question: Mapped[str] = mapped_column(Text)
    student_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
