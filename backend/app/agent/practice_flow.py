"""出题快捷流程：绕开 LLM 直接调 generate_practice，保证配图。

db 传给 _tool_generate_practice，最终 INSERT practice_records。
"""

from __future__ import annotations

import time
from typing import Iterator

from sqlalchemy.orm import Session

from .tools import _tool_generate_practice

PRACTICE_TRIGGERS = frozenset(
    {
        "出一道题",
        "再出一道",
        "出题",
        "来一道题",
        "出一题",
        "再来一道",
    }
)


def is_practice_request(question: str) -> bool:
    q = question.strip()
    if q in PRACTICE_TRIGGERS:
        return True
    return len(q) <= 10 and "出题" in q


def format_practice_answer(result: dict) -> str:
    lines = ["来看一道题！"]
    if result.get("diagram"):
        lines.append("👆 先看图（分两步：小猫在哪 → 照片看到啥），再动脑筋～")
    lines.append("")
    lines.append(result.get("question", ""))
    hint = (result.get("hint") or "").strip()
    if hint:
        lines.extend(["", f"小提示：{hint}"])
    return "\n".join(lines)


def stream_direct_practice(
    db: Session,
    *,
    lesson_id: int,
    difficulty: str,
    session_id: str,
) -> Iterator[dict]:
    yield {
        "event": "tool_start",
        "data": {
            "tool": "generate_practice",
            "args": {"lesson_id": lesson_id, "difficulty": difficulty},
        },
    }

    started = time.perf_counter()
    result = _tool_generate_practice(
        db, lesson_id, difficulty, session_id=session_id
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    ok = bool(result.get("ok"))

    tool_end = {
        "tool": "generate_practice",
        "ok": ok,
        "ms": elapsed_ms,
    }
    if ok and result.get("diagram"):
        tool_end["diagram"] = result["diagram"]
    yield {"event": "tool_end", "data": tool_end}

    if not ok:
        err = result.get("error", "出题失败，请重试")
        yield {"event": "delta", "data": {"content": err}}
        yield {
            "event": "done",
            "data": {
                "answer": err,
                "tool_calls": [
                    {
                        "tool": "generate_practice",
                        "ok": False,
                        "ms": elapsed_ms,
                    }
                ],
                "llm_turns": 0,
            },
        }
        return

    answer = format_practice_answer(result)
    chunk_size = 24
    for i in range(0, len(answer), chunk_size):
        yield {"event": "delta", "data": {"content": answer[i : i + chunk_size]}}

    done_payload = {
        "answer": answer,
        "diagram": result.get("diagram"),
        "tool_calls": [
            {
                "tool": "generate_practice",
                "ok": True,
                "ms": elapsed_ms,
            }
        ],
        "llm_turns": 0,
    }
    yield {"event": "done", "data": done_payload}
