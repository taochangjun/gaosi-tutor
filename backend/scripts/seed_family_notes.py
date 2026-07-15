"""
写入一批「有对比度」的家庭笔记，方便测 Hybrid / Rerank。

用法：
  cd backend && ./venv/bin/python -m scripts.seed_family_notes
  make seed-notes   # 若已加入 Makefile

设计意图（故意制造差异）：
  - 第5讲：强调「借位」「小动物」，少提「竖式」→ 问「竖式」时向量可能误伤，BM25 偏弱
  - 第18讲：明确「竖式」「退位减」→ 问「竖式不对」时 BM25 应强
  - 多讲噪音笔记：兴趣、习惯、情绪，无关计算干扰精排
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.rag.bm25_index import invalidate_bm25_cache
from app.agent.rag.indexer import index_all_notes, rag_stats
from app.curriculum.loader import update_family_notes
from app.database import SessionLocal


# lesson_id -> 家长笔记（多段，便于切块）
SEED_NOTES: dict[int, str] = {
    1: (
        "比较大小时孩子常只看数字表面，容易忽略「谁多谁少」的图意。\n"
        "建议用实物硬币、糖块对照，先说再说写。\n"
        "情绪上怕答错，要多鼓励「先说想法再改」。"
    ),
    2: (
        "左右、前后还经常混，特别是被提问「谁在左边」时反应慢。\n"
        "回家可用玩具排队练位置词：左、右、前、后、中间。\n"
        "不要一次塞太多方位词，每天巩固一两个。"
    ),
    3: (
        "拼图耐心一般，复杂轮廓容易放弃。\n"
        "先给边框图示，让他自己找角与边，少代动手。\n"
        "完成一幅就拍下来留进步感，比批评更有效。"
    ),
    4: (
        "立体图形：正方体和长方体还能分清，圆柱圆锥容易混。\n"
        "家里找易拉罐、魔方对照摸棱角。\n"
        "画立体时喜欢用平面表达，可先搭积木再画。"
    ),
    5: (
        "孩子减法还不太熟练，尤其是借位。\n"
        "退位时总忘记被减数减一，个位却又改对一半。\n"
        "平时喜欢用小动物情境出题，多鼓励，少打断。\n"
        "口算尚可，遇到较大数差就会慌；可以拆成十以内再合。\n"
        "（本讲笔记故意几乎不提「竖式」二字，方便对比检索。）"
    ),
    6: (
        "找规律：图形循环还能跟，数字间隔规律要提示才发现。\n"
        "可先让他说「下一个会是什么」，再说理由。\n"
        "不要急着揭答案，做错一次再观察往往记得牢。"
    ),
    7: (
        "可能性：还分不清「一定」「可能」「不可能」。\n"
        "用摸球、天气、上学能不能带宠物做生活例子。\n"
        "口试比写题更敢说，可先口头再说圈关键词。"
    ),
    8: (
        "分类还按单一标准，双标准（颜色+形状）容易乱。\n"
        "整理玩具时请他说明「我按什么分的」。\n"
        "分类讲清楚标准比分得快更重要。"
    ),
    13: (
        "基数与序数：第几和有几个还混。\n"
        "排队、楼层、日历上指「第几天」专门练。\n"
        "题干出现「第」字就先圈出来再算。"
    ),
    17: (
        "角的认识：直角能指出来，锐角钝角还模糊。\n"
        "用书本角、三角板对照。\n"
        "画角时射线画得很短，提醒两边要画长一点。"
    ),
    18: (
        "加减法竖式练习要多练，位数对齐是硬伤。\n"
        "竖式不对时多半是个位与十位串行，或退位减漏改上面。\n"
        "建议每天三道竖式：一道不退位、一道退位、一道加法进位。\n"
        "和「借位」同一套运算，但本题强调书写格式与竖式步骤。\n"
        "孩子说怕竖式，其实是怕对齐；用格子本对齐帮助很大。"
    ),
    19: (
        "单位换算：米和厘米还要扳手指。\n"
        "卷尺量家门、桌面，先估再量。\n"
        "做题先写单位再写数，减少漏单位。"
    ),
    20: (
        "钟面：整点半点还行，差几分到还不稳。\n"
        "可用旧闹钟拨针模拟「还有五分钟上课」。\n"
        "和时间焦虑无关，主要是刻度还不熟。"
    ),
    21: (
        "趣题更吃兴趣。孩子喜欢故事型，讨厌纯符号长题。\n"
        "陪练时可先听他把「已知、所求」讲清楚。\n"
        "这类题检索噪音较多，适合看精排是否压下弱相关。"
    ),
}


def main() -> None:
    db = SessionLocal()
    try:
        print(f"写入 {len(SEED_NOTES)} 讲家庭笔记…")
        for lesson_id, notes in sorted(SEED_NOTES.items()):
            out = update_family_notes(db, lesson_id, notes)
            assert out.get("ok"), out
            print(f"  ✅ 第 {lesson_id} 讲  notes={len(notes)} 字")

        print("同步向量库（index_all_notes）…")
        indexed = index_all_notes(db)
        invalidate_bm25_cache()
        print("index:", indexed)
        stats = rag_stats(db)
        print("rag_stats:", stats)
        print("\n[PASS] 家庭笔记已写入 MySQL 并索引到 Chroma")
        print("建议在家长面板试 query：借位 / 竖式不对 / 小动物 / 左右还混")
    finally:
        db.close()


if __name__ == "__main__":
    main()
