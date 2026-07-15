"""
批量生成约 2000 条「可对比」家庭笔记，并保证金标句可被召回。

用法：
  make seed-notes-bulk

相对上一版的修复：
  - 每讲开头注入自然语言金标（含「孩子减法还不太熟练，尤其是借位。」）
  - 噪音 / 干扰句 **禁止**再塞主题关键词（避免「借位做饭」冲掉 BM25）
  - 关键词相关句只占少数、措辞自然；同义句不含关键词（测向量）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.rag.bm25_index import invalidate_bm25_cache
from app.agent.rag.chunker import chunk_family_note
from app.agent.rag.indexer import index_all_notes, rag_stats
from app.curriculum.loader import list_lessons, update_family_notes
from app.database import SessionLocal

# 自然语言金标（检索应优先召回）
GOLD_LINES: dict[int, list[str]] = {
    1: [
        "比较大小时孩子常只看数字表面，容易忽略「谁多谁少」的图意。",
        "建议用实物硬币、糖块对照，先说再说写。",
    ],
    2: [
        "左右、前后还经常混，特别是被提问「谁在左边」时反应慢。",
        "回家可用玩具排队练位置词：左、右、前、后、中间。",
    ],
    3: [
        "拼图耐心一般，复杂轮廓容易放弃。",
        "先给边框图示，让他自己找角与边，少代动手。",
    ],
    4: [
        "立体图形：正方体和长方体还能分清，圆柱圆锥容易混。",
        "家里找易拉罐、魔方对照摸棱角。",
    ],
    5: [
        "孩子减法还不太熟练，尤其是借位。",
        "退位时总忘记被减数减一，个位却又改对一半。",
        "平时喜欢用小动物情境出题，多鼓励，少打断。",
        "口算尚可，遇到较大数差就会慌；可以拆成十以内再合。",
    ],
    6: [
        "找规律：图形循环还能跟，数字间隔规律要提示才发现。",
        "可先让他说「下一个会是什么」，再说理由。",
    ],
    7: [
        "可能性：还分不清「一定」「可能」「不可能」。",
        "用摸球、天气做生活例子更敢开口。",
    ],
    8: [
        "分类还按单一标准，双标准（颜色+形状）容易乱。",
        "整理玩具时请他说明「我按什么分的」。",
    ],
    9: [
        "用尺子、天平比较时，孩子常跳过估测直接读数。",
        "量一量之后再下结论，习惯还没养成。",
    ],
    10: [
        "找路线容易绕远，最短路径讲不清楚。",
        "迷宫题先让他说怎么走，再动手画。",
    ],
    11: [
        "多角度观察：侧面、俯视还不熟，只认正面。",
        "换角度看同一物体，需要多练几次。",
    ],
    12: [
        "骰子点数和相对面规律还不熟。",
        "掷出数字后反应慢，可先口头报点再算。",
    ],
    13: [
        "基数与序数：第几和有几个还混。",
        "题干出现「第」字就先圈出来再算。",
    ],
    14: [
        "图文算式里缺数总靠猜，图画和算式对不上。",
        "看图列式要先说已知再写式子。",
    ],
    15: [
        "图形规律的重复单元容易跟丢。",
        "涂色规律跳格时，让他指着单元再说一遍。",
    ],
    16: [
        "数图形时重叠、嵌套容易漏数。",
        "数三角形可以按大小分层数，少漏。",
    ],
    17: [
        "直角能指出来，锐角钝角还模糊。",
        "画角时射线太短，提醒两边画长一点。",
    ],
    18: [
        "加减法竖式练习要多练，位数对齐是硬伤。",
        "竖式不对时多半是个位与十位串行，或退位减漏改上面。",
        "建议每天三道竖式：一道不退位、一道退位、一道加法进位。",
        "孩子说怕竖式，其实是怕对齐；用格子本对齐帮助很大。",
    ],
    19: [
        "单位换算：米和厘米还要扳手指。",
        "做题先写单位再写数，减少漏单位。",
    ],
    20: [
        "钟面：整点半点还行，差几分到还不稳。",
        "可用旧闹钟拨针模拟，主要是刻度还不熟。",
    ],
    21: [
        "趣题更吃兴趣。孩子喜欢故事型，讨厌纯符号长题。",
        "陪练时可先听他把「已知、所求」讲清楚。",
    ],
}

# kw=应出现在少数正例；syn=不含 kw（向量）；noise=也不含 kw
LESSON_BANK: dict[int, dict] = {
    1: {
        "kw": ["比较大小", "谁多谁少"],
        "syn": ["数目对照还看不清", "图意和数对不上号"],
        "noise": ["今天想画画心情不错", "跳绳后更能坐得住"],
    },
    2: {
        "kw": ["左右", "前后"],
        "syn": ["方位词反应慢", "排队搞不清站哪边"],
        "noise": ["晚饭后散步十分钟", "睡前少看动画"],
    },
    3: {
        "kw": ["拼图", "轮廓"],
        "syn": ["复杂图形耐心不够", "拼版总想放弃"],
        "noise": ["作品贴上展示墙", "完成一项就鼓掌"],
    },
    4: {
        "kw": ["正方体", "长方体"],
        "syn": ["立体和平面仍易混", "摸棱角才认出罐子"],
        "noise": ["积木收纳需要帮助", "动手课兴趣很高"],
    },
    5: {
        "kw": ["借位", "减法"],
        "syn": ["退位减法总搞错", "被减数十位忘记减一", "较大数差就会慌"],
        "noise": ["今天情绪平稳", "分享绘本很开心", "写完作业去骑车"],
    },
    6: {
        "kw": ["找规律", "循环"],
        "syn": ["下一个说不出理由", "图形序列跟不紧"],
        "noise": ["贴纸换到新本子", "周末全家户外"],
    },
    7: {
        "kw": ["一定", "可能", "不可能"],
        "syn": ["可能性词语还混", "摸球例子才敢说"],
        "noise": ["口语练习更大声", "小组发言敢举手"],
    },
    8: {
        "kw": ["分类", "双标准"],
        "syn": ["按什么分说不清", "整理标准经常变"],
        "noise": ["书桌清扫很认真", "收纳盒贴了标签"],
    },
    9: {
        "kw": ["尺子", "天平"],
        "syn": ["量一量才敢下结论", "估测和实测差很多"],
        "noise": ["工具箱自己收拾", "动手实验很兴奋"],
    },
    10: {
        "kw": ["路线", "最短路径"],
        "syn": ["迷宫易绕远", "方向说明含糊"],
        "noise": ["公园散步认路牌", "地铁站认出口"],
    },
    11: {
        "kw": ["多角度", "俯视"],
        "syn": ["换角度看物体还不会", "只认正面轮廓"],
        "noise": ["拍照记录作品", "展览参观有收获"],
    },
    12: {
        "kw": ["骰子", "点数"],
        "syn": ["色子对面规律不熟", "掷点后反应慢"],
        "noise": ["桌游限时二十分钟", "输赢情绪要照顾"],
    },
    13: {
        "kw": ["基数", "序数"],
        "syn": ["第几和有几个老混", "排队楼层要圈关键字"],
        "noise": ["日历打卡坚持中", "早晚读十分钟"],
    },
    14: {
        "kw": ["图文算式", "看图列式"],
        "syn": ["图画和算式对不上", "填空数总凭猜"],
        "noise": ["错题本整理整齐", "红笔订正更清楚"],
    },
    15: {
        "kw": ["图形规律", "涂色规律"],
        "syn": ["图案循环跟丢", "涂色顺序易跳格"],
        "noise": ["彩铅需要削尖", "作品送给爷爷"],
    },
    16: {
        "kw": ["数图形", "数三角形"],
        "syn": ["交叉图形漏数", "嵌套形状数不全"],
        "noise": ["草稿纸要大方用", "坐姿提醒一次"],
    },
    17: {
        "kw": ["直角", "锐角", "钝角"],
        "syn": ["角的种类还模糊", "射线画太短看不清"],
        "noise": ["三角板自己保管", "练习本不卷角"],
    },
    18: {
        "kw": ["竖式", "位数对齐"],
        "syn": ["列着算总串行", "格子本才写整齐", "退位改上面漏掉"],
        "noise": ["文具摆放整齐", "草稿纸分区使用"],
    },
    19: {
        "kw": ["米厘米", "单位换算"],
        "syn": ["量完忘写单位", "倍数关系还懵"],
        "noise": ["卷尺出门记得带", "客厅量一量好玩"],
    },
    20: {
        "kw": ["钟面", "整点", "半点"],
        "syn": ["看表还读不准", "拨针模拟才明白"],
        "noise": ["作息表贴冰箱", "闹钟自己设"],
    },
    21: {
        "kw": ["趣题", "已知所求"],
        "syn": ["长题读不懂条件", "要先讲再算才敢动手"],
        "noise": ["阅读打卡三页", "分享题给弟弟听"],
    },
}


def _paragraphs_for_lesson(lesson_id: int, title: str, n: int) -> list[str]:
    """生成 n 条：金标优先；关键词正例极少且互异，避免塞满向量 Top。"""
    bank = LESSON_BANK.get(lesson_id) or {
        "kw": [title],
        "syn": [f"{title}还需要多练"],
        "noise": ["今天状态还可以", "鼓励多于批评"],
    }
    gold = list(GOLD_LINES.get(lesson_id) or [f"{title}：本讲重点还需要巩固。"])
    if n <= len(gold):
        return gold[:n]

    kws = bank["kw"]
    syns = bank["syn"]
    noises = bank["noise"]
    lines = list(gold)
    remain = n - len(lines)

    # 关键词正例最多 3 条（且措辞不同），其余同义 + 无关键词噪音
    # 旧版 ~20% 雷同「做题时「借位」仍易错」会占满向量 Top，把金标挤出 RRF
    n_kw = min(3, max(1, remain // 20))
    n_syn = max(1, (remain - n_kw) // 2)
    n_noise = remain - n_kw - n_syn

    kw_templates = [
        "陪练时发现孩子在「{token}」上仍吃力，需要再拆例讲解。",
        "家庭作业里与「{token}」相关的错题已圈出，明天复盘。",
        "口头提问「{token}」时反应慢半拍，建议用实物辅助。",
    ]
    for i in range(n_kw):
        token = kws[i % len(kws)]
        tpl = kw_templates[i % len(kw_templates)]
        lines.append(f"第{lesson_id}讲：{tpl.format(token=token)}")

    for i in range(n_syn):
        phrase = syns[i % len(syns)]
        # 变化更多，减少近重复向量
        tails = [
            "先听完想法再提示。",
            "用生活情境代入效果更好。",
            "错误本身就是讲解材料。",
            "当晚只练两道即可。",
            "家长少打断多追问为什么。",
        ]
        lines.append(
            f"第{lesson_id}讲观察{i + 1}：{phrase}；{tails[i % len(tails)]}"
        )

    for i in range(n_noise):
        phrase = noises[i % len(noises)]
        extras = [
            "记录心情备查。",
            "与课程知识点无直接关系。",
            "属于习惯养成备忘。",
            "可作为鼓励素材。",
        ]
        lines.append(
            f"第{lesson_id}讲日常{i + 1}：{phrase}；{extras[i % len(extras)]}"
        )
    return lines[:n]


def build_notes_by_lesson(*, total: int) -> dict[int, str]:
    lessons = list_lessons()
    if not lessons:
        raise RuntimeError("课程列表为空，请先 make init-db")
    lesson_ids = [int(x["id"]) for x in lessons]
    n_lessons = len(lesson_ids)
    base, rem = divmod(total, n_lessons)
    counts = {
        lid: base + (1 if idx < rem else 0) for idx, lid in enumerate(lesson_ids)
    }
    meta = {int(x["id"]): x for x in lessons}
    out: dict[int, str] = {}
    for lid, n in counts.items():
        title = meta[lid].get("title") or f"第{lid}讲"
        out[lid] = "\n".join(_paragraphs_for_lesson(lid, title, n))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2000, help="目标段落/chunk 数")
    args = parser.parse_args()
    total = max(21, int(args.count))

    notes_map = build_notes_by_lesson(total=total)
    preview_chunks = 0
    lessons_meta = {int(x["id"]): x for x in list_lessons()}
    for lid, text in notes_map.items():
        meta = lessons_meta[lid]
        preview_chunks += len(
            chunk_family_note(
                lesson_id=lid,
                title=meta.get("title") or "",
                topic=meta.get("topic") or "",
                notes=text,
            )
        )
    print(f"计划写入 {len(notes_map)} 讲，预估 chunks={preview_chunks}（目标 {total}）")

    db = SessionLocal()
    try:
        for lid in sorted(notes_map):
            text = notes_map[lid]
            update_family_notes(db, lid, text)
            print(f"  ✅ 第 {lid} 讲  lines={text.count(chr(10)) + 1}")

        print("同步向量库 index_all_notes…")
        indexed = index_all_notes(db)
        invalidate_bm25_cache()
        print("index:", indexed)
        print("rag_stats:", rag_stats(db))

        # 快速验收：金标应进第5讲 BM25/向量前列
        from app.agent.rag.hybrid import hybrid_search_family_notes

        check = hybrid_search_family_notes(
            db, "借位哪里薄弱", lesson_id=5, top_k=5, with_rerank=False
        )
        snips = [
            (h.get("snippet") or "")
            for ch in ("vector", "bm25", "hybrid")
            for h in (check.get(ch) or {}).get("hits") or []
        ]
        ok = any("尤其是借位" in s for s in snips)
        print(
            "\n验收 query「借位哪里薄弱」@第5讲：",
            "金标已召回 ✅" if ok else "金标未进 Top ❌",
        )
        for ch in ("vector", "bm25", "hybrid"):
            top = ((check.get(ch) or {}).get("hits") or [{}])[0]
            print(f"  {ch}#1:", (top.get("snippet") or "")[:48])
        print("\n[PASS] 批量家庭笔记已写入（含金标）")
    finally:
        db.close()


if __name__ == "__main__":
    main()
