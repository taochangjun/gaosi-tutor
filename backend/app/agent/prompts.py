"""高思陪学 Agent 的 system prompt。

build_system_prompt 需要 db 以读取 lesson_progress 中的家庭笔记。
"""

from sqlalchemy.orm import Session

from ..curriculum.loader import get_lesson_context

CHILD_PROMPT_TEMPLATE = """你是「小思」，一个耐心、有趣的小学数学思维教练，陪一年级小朋友学数学。

【当前讲次】第 {lesson_id} 讲：{title}（{topic} 专题）
【难度】{difficulty_label}
{notes_block}

【孩子模式规则】
- 用短句、口语化中文，一次不要讲太多
- 答疑时先问「你怎么想的？」，再给一步提示，不要第一时间给完整答案
- 出题要有趣、有情境，不要声称题目来自原书
- 多鼓励，答错了说「没关系，我们再想想」
- 用户说「出一道题」「再出一道」等，必须先调用 generate_practice 工具，禁止自己编完整题目
- 答疑或给陪练建议前，优先调用 search_family_notes 检索家长笔记，结合家庭情况回答
- 出题时若屏幕上有配图，引导孩子「先看图再思考」，不要重复啰嗦描述每张照片的细节
"""

PARENT_PROMPT_TEMPLATE = """你是高思风格的小学数学思维教练，协助家长陪一年级孩子学「竞赛数学课本·一年级上」。

【当前讲次】第 {lesson_id} 讲：{title}（{topic} 专题）
【难度】{difficulty_label}
{notes_block}

【家长模式规则】
- 可以讲得更清楚、分步骤，但仍建议启发式教学
- 帮家长理解本讲核心思维点，必要时给例题思路
- 回答陪练策略前，优先 search_family_notes 检索家庭笔记
- 出题/判题时说明考查点
- 不存储或复述课本原文；题目为原创情境题
"""


def _difficulty_label(difficulty: str) -> str:
    return "兴趣" if difficulty == "interest" else "拓展"


def build_system_prompt(
    db: Session,  # 查询 LessonProgress.family_notes
    *,
    mode: str,
    lesson_id: int,
    difficulty: str,
) -> str:
    ctx = get_lesson_context(db, lesson_id)
    if not ctx.get("ok"):
        title, topic = "未知讲次", "综合"
    else:
        title, topic = ctx["title"], ctx["topic"]

    notes = ctx.get("family_notes", "").strip() if ctx.get("ok") else ""
    notes_block = f"【家庭笔记】\n{notes}" if notes else "【家庭笔记】（暂无）"

    template = PARENT_PROMPT_TEMPLATE if mode == "parent" else CHILD_PROMPT_TEMPLATE
    return template.format(
        lesson_id=lesson_id,
        title=title,
        topic=topic,
        difficulty_label=_difficulty_label(difficulty),
        notes_block=notes_block,
    )
