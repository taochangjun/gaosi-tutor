"""高思陪学 Agent 工具。

需要读写信 DB 的工具通过参数 db: Session 接收数据库会话（由 loop/router 传入）。
纯静态工具（如 list_lessons）不碰数据库。
"""

import json
import re

from sqlalchemy.orm import Session

from ..diagram.schema import (
    apply_lesson_diagram_overrides,
    default_diagram_for_lesson,
    diagram_prompt_help,
    lesson_needs_diagram,
    normalize_diagram,
)
from ..curriculum.loader import get_lesson_context, list_lessons
from ..models import PracticeRecord
from ..settings import get_llm_model
from .llm import chat
from .rag.retriever import search_family_notes as rag_search

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_lessons",
            "description": "列出一年级上册全部 21 讲目录（序号、标题、专题）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lesson_context",
            "description": "获取当前或指定讲次的上下文：标题、专题、家庭笔记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_id": {
                        "type": "integer",
                        "description": "讲次序号 1～21",
                    }
                },
                "required": ["lesson_id"],
            },
        },
    },
    # --- RAG：向量检索家庭笔记（Chroma + fastembed），见 app/agent/rag/ ---
    {
        "type": "function",
        "function": {
            "name": "search_family_notes",
            "description": "从家庭笔记知识库语义检索家长写的要点、薄弱点、陪练提醒。答疑或陪练建议前优先调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索问题，如「孩子哪里薄弱」「本讲要注意什么」",
                    },
                    "lesson_id": {
                        "type": "integer",
                        "description": "可选，限定讲次 1～21",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_practice",
            "description": "生成一道练习题（含配图数据）。用户说「出题」「出一道题」「再出一道」时必须调用，禁止自己编造完整题目。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_id": {"type": "integer", "description": "讲次 1～21"},
                    "difficulty": {
                        "type": "string",
                        "enum": ["interest", "extend"],
                        "description": "interest=兴趣，extend=拓展",
                    },
                },
                "required": ["lesson_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_answer",
            "description": "评判孩子对某道题的回答，给出对错和分步反馈。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson_id": {"type": "integer"},
                    "question": {"type": "string", "description": "题目全文"},
                    "student_answer": {"type": "string", "description": "孩子的答案"},
                    "reference_answer": {
                        "type": "string",
                        "description": "可选，标准答案（若 generate_practice 已给出）",
                    },
                },
                "required": ["lesson_id", "question", "student_answer"],
            },
        },
    },
]


def _parse_json_from_llm(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise


def _tool_list_lessons() -> dict:
    lessons = list_lessons()
    return {"ok": True, "lessons": lessons, "count": len(lessons)}


def _tool_get_lesson_context(db: Session, lesson_id: int) -> dict:
    """委托 curriculum.loader，内部会 query LessonProgress。"""
    return get_lesson_context(db, lesson_id)


def _tool_search_family_notes(
    db: Session,
    query: str,
    lesson_id: int | None = None,
) -> dict:
    """
    RAG 检索工具：语义搜索家庭笔记 top-K 片段。

    LLM 在答疑/陪练建议前调用；结果 JSON 作为 role=tool 消息回传。
    lesson_id 可选：限定当前讲或跨讲搜索。
    """
    return rag_search(db, query, lesson_id=lesson_id)


def _tool_generate_practice(
    db: Session,
    lesson_id: int,
    difficulty: str = "interest",
    session_id: str | None = None,
) -> dict:
    ctx = get_lesson_context(db, lesson_id)
    if not ctx.get("ok"):
        return ctx

    diff_label = "兴趣" if difficulty == "interest" else "拓展"
    needs_diagram = lesson_needs_diagram(ctx["id"], ctx["topic"])
    diagram_help = diagram_prompt_help(ctx["id"], ctx["topic"])

    model = get_llm_model()
    prompt = f"""你是小学数学出题老师。请为一年级学生出一道原创练习题。

讲次：第{ctx['id']}讲《{ctx['title']}》（{ctx['topic']}专题）
难度：{diff_label}
要求：情境有趣、适合一年级、不要抄袭任何教材原题。
{diagram_help}
只返回 JSON，不要 markdown：
{{"question": "题目正文", "hint": "提示", "answer": "标准答案", "diagram": null或{{...}}}}
"""
    message = chat(
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=700 if needs_diagram else 400,
    )
    try:
        data = _parse_json_from_llm(message.content or "")
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "出题失败，请重试"}

    question = data.get("question", "").strip()
    if not question:
        return {"ok": False, "error": "出题失败，请重试"}

    diagram = normalize_diagram(data.get("diagram"))
    if needs_diagram and not diagram:
        diagram = default_diagram_for_lesson(ctx["id"])

    question, diagram = apply_lesson_diagram_overrides(ctx["id"], question, diagram)

    # 持久化出题记录；refresh 在 commit 后重新加载行，拿到数据库自增的 id
    record = PracticeRecord(
        session_id=session_id,
        lesson_id=lesson_id,
        difficulty=difficulty,
        question=question,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "ok": True,
        "practice_id": record.id,
        "lesson_id": lesson_id,
        "difficulty": difficulty,
        "question": question,
        "hint": data.get("hint", ""),
        "answer": data.get("answer", ""),
        "diagram": diagram,
    }


def _tool_evaluate_answer(
    db: Session,
    lesson_id: int,
    question: str,
    student_answer: str,
    reference_answer: str = "",
    session_id: str | None = None,
) -> dict:
    ctx = get_lesson_context(db, lesson_id)
    title = ctx.get("title", "") if ctx.get("ok") else ""

    model = get_llm_model()
    prompt = f"""你是小学数学教练，帮一年级孩子检查答案。

讲次：第{lesson_id}讲 {title}
题目：{question}
孩子回答：{student_answer}
{"标准答案：" + reference_answer if reference_answer else ""}

请判断对错，用孩子能懂的话反馈。若错了只给一步提示，不要直接给完整解法。
只返回 JSON：
{{"is_correct": true或false, "feedback": "给孩子的反馈", "next_hint": "可选的下一步提示"}}
"""
    message = chat(
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=400,
    )
    try:
        data = _parse_json_from_llm(message.content or "")
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "error": "评判失败，请重试"}

    is_correct = bool(data.get("is_correct"))
    feedback = data.get("feedback", "我们再想想～")

    # 优先更新同 session 下同一道题的最新记录，避免重复 INSERT
    record = (
        db.query(PracticeRecord)
        .filter(
            PracticeRecord.session_id == session_id,
            PracticeRecord.question == question,
        )
        .order_by(PracticeRecord.id.desc())
        .first()
        if session_id
        else None
    )
    if record:
        record.student_answer = student_answer
        record.is_correct = is_correct
        record.feedback = feedback
    else:
        db.add(
            PracticeRecord(
                session_id=session_id,
                lesson_id=lesson_id,
                question=question,
                student_answer=student_answer,
                is_correct=is_correct,
                feedback=feedback,
            )
        )
    db.commit()

    return {
        "ok": True,
        "is_correct": is_correct,
        "feedback": feedback,
        "next_hint": data.get("next_hint", ""),
    }


def execute_tool(
    name: str,
    args: dict,
    db: Session,  # Agent loop 传入的同一 Session，贯穿整轮 tool 调用
    *,
    session_id: str | None = None,
) -> str:
    if name == "list_lessons":
        result = _tool_list_lessons()
    elif name == "get_lesson_context":
        result = _tool_get_lesson_context(db, args["lesson_id"])
    elif name == "search_family_notes":
        result = _tool_search_family_notes(
            db,
            args["query"],
            args.get("lesson_id"),
        )
    elif name == "generate_practice":
        result = _tool_generate_practice(
            db,
            args["lesson_id"],
            args.get("difficulty", "interest"),
            session_id=session_id,
        )
    elif name == "evaluate_answer":
        result = _tool_evaluate_answer(
            db,
            args["lesson_id"],
            args["question"],
            args["student_answer"],
            args.get("reference_answer", ""),
            session_id=session_id,
        )
    else:
        result = {"ok": False, "error": f"未知工具: {name}"}
    return json.dumps(result, ensure_ascii=False)
