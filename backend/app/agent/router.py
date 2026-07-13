import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..curriculum.loader import get_family_notes, list_lessons, update_family_notes
from ..database import SessionLocal, get_db
from ..schemas import (
    HealthOut,
    LessonNotesUpdate,
    LessonOut,
    RagIndexOut,
    RagSearchIn,
    RagSearchOut,
    RagStatsOut,
    TutorChatInput,
    TutorChatOutput,
)
from .loop import run_agent_from_messages, run_agent_stream_from_messages
from .practice_flow import is_practice_request, stream_direct_practice
from .prompts import build_system_prompt
from .rag.indexer import index_all_notes, index_lesson_notes, rag_stats
from .rag.retriever import search_family_notes
from .session_store import append_message, get_or_create_session, load_history

router = APIRouter(prefix="/api", tags=["tutor"])


def _format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    from ..settings import get_settings

    db_ok = "ok"
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_ok = "error"

    settings = get_settings()
    agent_ok = "ok" if settings.deepseek_api_key else "missing_api_key"

    rag_ok = "ok"
    rag_chunks = 0
    try:
        stats = rag_stats(db)
        rag_chunks = stats.get("chunks_in_store", 0)
    except Exception:
        rag_ok = "error"

    return HealthOut(
        status="ok" if db_ok == "ok" else "degraded",
        database=db_ok,
        agent=agent_ok,
        lessons=len(list_lessons()),
        rag=rag_ok,
        rag_chunks=rag_chunks,
    )


@router.get("/lessons", response_model=list[LessonOut])
def lessons(db: Session = Depends(get_db)):
    result = []
    for item in list_lessons():
        result.append(
            LessonOut(
                id=item["id"],
                title=item["title"],
                topic=item["topic"],
                family_notes=get_family_notes(db, item["id"]),
            )
        )
    return result


@router.patch("/lessons/{lesson_id}/notes")
def patch_lesson_notes(
    lesson_id: int, data: LessonNotesUpdate, db: Session = Depends(get_db)
):
    outcome = update_family_notes(db, lesson_id, data.family_notes)
    if not outcome.get("ok"):
        raise HTTPException(status_code=404, detail=outcome.get("error", "讲次不存在"))
    index_outcome = index_lesson_notes(db, lesson_id)
    outcome["rag"] = index_outcome
    return outcome


@router.get("/rag/stats", response_model=RagStatsOut)
def rag_stats_api(db: Session = Depends(get_db)):
    return rag_stats(db)


@router.post("/rag/index", response_model=RagIndexOut)
def rag_index_all(db: Session = Depends(get_db)):
    return index_all_notes(db)


@router.post("/rag/index/{lesson_id}", response_model=RagIndexOut)
def rag_index_lesson(lesson_id: int, db: Session = Depends(get_db)):
    outcome = index_lesson_notes(db, lesson_id)
    if not outcome.get("ok"):
        raise HTTPException(status_code=404, detail=outcome.get("error", "讲次不存在"))
    return outcome


@router.post("/rag/search", response_model=RagSearchOut)
def rag_search_api(data: RagSearchIn, db: Session = Depends(get_db)):
    outcome = search_family_notes(db, data.query, lesson_id=data.lesson_id)
    if not outcome.get("ok"):
        raise HTTPException(status_code=400, detail=outcome.get("error", "检索失败"))
    return outcome


@router.post("/chat", response_model=TutorChatOutput)
def chat(data: TutorChatInput, db: Session = Depends(get_db)):
    sid = get_or_create_session(
        db,
        data.session_id,
        mode=data.mode,
        lesson_id=data.lesson_id,
        difficulty=data.difficulty,
    )
    history = load_history(db, sid)
    append_message(db, sid, "user", data.question)

    system_prompt = build_system_prompt(
        db, mode=data.mode, lesson_id=data.lesson_id, difficulty=data.difficulty
    )
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": data.question},
    ]
    result = run_agent_from_messages(messages, db, session_id=sid)
    append_message(db, sid, "assistant", result.answer or "（无回答）", result.tool_trace)
    return TutorChatOutput(
        answer=result.answer,
        tool_calls=result.tool_trace,
        session_id=sid,
    )


@router.post("/chat/stream")
def chat_stream(data: TutorChatInput):
    def event_generator():
        db = SessionLocal()
        sid = None
        tool_trace: list[dict] = []
        final_answer = ""

        try:
            sid = get_or_create_session(
                db,
                data.session_id,
                mode=data.mode,
                lesson_id=data.lesson_id,
                difficulty=data.difficulty,
            )
            history = load_history(db, sid)
            append_message(db, sid, "user", data.question)

            if is_practice_request(data.question):
                for item in stream_direct_practice(
                    db,
                    lesson_id=data.lesson_id,
                    difficulty=data.difficulty,
                    session_id=sid,
                ):
                    evt = item["event"]
                    payload = dict(item["data"])
                    if evt == "delta":
                        final_answer += payload.get("content", "")
                    elif evt == "done":
                        final_answer = payload.get("answer") or final_answer
                        tool_trace = payload.get("tool_calls") or tool_trace
                        payload["session_id"] = sid
                    yield _format_sse(evt, payload)
            else:
                system_prompt = build_system_prompt(
                    db,
                    mode=data.mode,
                    lesson_id=data.lesson_id,
                    difficulty=data.difficulty,
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    *history,
                    {"role": "user", "content": data.question},
                ]

                for item in run_agent_stream_from_messages(
                    messages, db, session_id=sid
                ):
                    evt = item["event"]
                    payload = dict(item["data"])

                    if evt == "delta":
                        final_answer += payload.get("content", "")
                    elif evt == "done":
                        final_answer = payload.get("answer") or final_answer
                        tool_trace = payload.get("tool_calls") or tool_trace
                        payload["session_id"] = sid

                    yield _format_sse(evt, payload)

            append_message(
                db, sid, "assistant", final_answer or "（无回答）", tool_trace or None
            )
        except Exception as exc:
            yield _format_sse("error", {"message": str(exc)})
        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
