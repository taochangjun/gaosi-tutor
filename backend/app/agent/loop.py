"""Agent 主循环（精简版，无确认门）。"""

import json
import time
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy.orm import Session

from ..settings import get_llm_model, get_settings
from .llm import chat, chat_stream, chat_with_tools
from .tools import TOOLS, execute_tool

MAX_TURNS = 8


@dataclass
class AgentRunResult:
    answer: str
    tool_trace: list[dict]
    llm_turns: int = 0


def assistant_message_to_dict(message) -> dict:
    d = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return d


def run_agent_from_messages(
    messages: list[dict],
    db: Session,
    *,
    session_id: str | None = None,
) -> AgentRunResult:
    tool_trace: list[dict] = []
    llm_turns = 0
    settings = get_settings()
    model = get_llm_model()

    for _ in range(MAX_TURNS):
        llm_turns += 1
        message = chat_with_tools(messages, model=model, tools=TOOLS)

        if message.tool_calls:
            messages.append(assistant_message_to_dict(message))

            for call in message.tool_calls:
                args = json.loads(call.function.arguments)
                started = time.perf_counter()
                result_str = execute_tool(
                    call.function.name, args, db, session_id=session_id
                )
                result = json.loads(result_str)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                tool_ok = bool(result.get("ok"))
                tool_trace.append(
                    {
                        "tool": call.function.name,
                        "args": args,
                        "ms": elapsed_ms,
                        "ok": tool_ok,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_str,
                    }
                )
            continue

        llm_turns += 1
        final = chat(messages, model=model)
        return AgentRunResult(
            answer=final.content or "",
            tool_trace=tool_trace,
            llm_turns=llm_turns,
        )

    return AgentRunResult(
        answer="处理超时，请简化问题。",
        tool_trace=tool_trace,
        llm_turns=llm_turns,
    )


def run_agent_stream_from_messages(
    messages: list[dict],
    db: Session,
    *,
    session_id: str | None = None,
) -> Iterator[dict]:
    tool_trace: list[dict] = []
    llm_turns = 0
    settings = get_settings()
    model = get_llm_model()

    for _ in range(MAX_TURNS):
        llm_turns += 1
        message = chat_with_tools(messages, model=model, tools=TOOLS)

        if message.tool_calls:
            messages.append(assistant_message_to_dict(message))

            for call in message.tool_calls:
                args = json.loads(call.function.arguments)
                tool_name = call.function.name
                yield {"event": "tool_start", "data": {"tool": tool_name, "args": args}}

                started = time.perf_counter()
                result_str = execute_tool(
                    tool_name, args, db, session_id=session_id
                )
                result = json.loads(result_str)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                tool_ok = bool(result.get("ok"))
                tool_trace.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "ms": elapsed_ms,
                        "ok": tool_ok,
                    }
                )
                tool_payload = {
                        "tool": tool_name,
                        "ok": tool_ok,
                        "ms": elapsed_ms,
                    }
                if tool_name == "generate_practice" and result.get("diagram"):
                    tool_payload["diagram"] = result["diagram"]
                yield {"event": "tool_end", "data": tool_payload}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_str,
                    }
                )
            continue

        llm_turns += 1
        parts: list[str] = []
        for delta in chat_stream(messages, model=model):
            parts.append(delta)
            yield {"event": "delta", "data": {"content": delta}}
        answer = "".join(parts)
        yield {
            "event": "done",
            "data": {
                "answer": answer,
                "tool_calls": tool_trace,
                "llm_turns": llm_turns,
            },
        }
        return

    timeout = "处理超时，请简化问题。"
    yield {"event": "delta", "data": {"content": timeout}}
    yield {
        "event": "done",
        "data": {
            "answer": timeout,
            "tool_calls": tool_trace,
            "llm_turns": llm_turns,
        },
    }
