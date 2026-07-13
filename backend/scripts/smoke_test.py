"""冒烟：list_lessons + 可选 LLM 对话。"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.loop import run_agent_from_messages
from app.agent.prompts import build_system_prompt
from app.curriculum.loader import list_lessons
from app.database import SessionLocal
from app.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只测课程数据，不调 LLM")
    parser.add_argument("--lesson", type=int, default=5)
    args = parser.parse_args()

    lessons = list_lessons()
    assert len(lessons) == 21, f"expected 21 lessons, got {len(lessons)}"
    print(f"[OK] 课程目录 {len(lessons)} 讲")

    if args.dry:
        print("[dry] 跳过 LLM")
        return

    settings = get_settings()
    if not settings.deepseek_api_key:
        print("[SKIP] 无 API Key，加 --dry 可只测本地数据")
        sys.exit(0)

    db = SessionLocal()
    try:
        system = build_system_prompt(
            db, mode="child", lesson_id=args.lesson, difficulty="interest"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "请出一道练习题"},
        ]
        result = run_agent_from_messages(messages, db)
        print("[OK] Agent 回答片段:", (result.answer or "")[:120])
        print("[OK] 工具链:", [t["tool"] for t in result.tool_trace])
    finally:
        db.close()


if __name__ == "__main__":
    main()
