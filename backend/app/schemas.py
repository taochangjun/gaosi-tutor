from datetime import datetime

from pydantic import BaseModel, Field


class TutorChatInput(BaseModel):
    question: str
    session_id: str | None = None
    mode: str = Field(default="child", pattern="^(child|parent)$")
    lesson_id: int = Field(default=1, ge=1, le=21)
    difficulty: str = Field(default="interest", pattern="^(interest|extend)$")


class TutorChatOutput(BaseModel):
    answer: str
    tool_calls: list[dict] = []
    session_id: str | None = None


class LessonOut(BaseModel):
    id: int
    title: str
    topic: str
    family_notes: str = ""


class LessonNotesUpdate(BaseModel):
    family_notes: str = ""


class HealthOut(BaseModel):
    status: str
    database: str
    agent: str
    lessons: int
    rag: str = "unknown"
    rag_chunks: int = 0


class RagStatsOut(BaseModel):
    ok: bool = True
    notes_with_content: int = 0
    chunks_in_store: int = 0
    chroma_path: str = ""


class RagIndexOut(BaseModel):
    ok: bool = True
    lesson_id: int | None = None
    lessons_indexed: int | None = None
    chunks_indexed: int = 0
    total_chunks: int | None = None
    message: str | None = None


class RagSearchIn(BaseModel):
    query: str
    lesson_id: int | None = Field(default=None, ge=1, le=21)


class RagSearchHit(BaseModel):
    lesson_id: int | None = None
    title: str | None = None
    topic: str | None = None
    snippet: str
    score: float


class RagSearchOut(BaseModel):
    ok: bool = True
    query: str = ""
    hits: list[RagSearchHit] = []
    count: int = 0
    message: str | None = None


class RagCompareOut(BaseModel):
    ok: bool = True
    query: str = ""
    vector: dict = {}
    bm25: dict = {}
    hybrid: dict = {}
