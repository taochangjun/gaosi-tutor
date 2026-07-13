"""练习题配图规范：LLM 返回语义化 diagram，前端 SVG 渲染。"""

from __future__ import annotations

ALLOWED_ICONS = frozenset(
    {
        "circle",
        "circle_dot",
        "rect",
        "rect_eraser_top",
        "rect_tip_bottom",
        "square",
        "triangle",
        "dice_1",
        "dice_2",
        "dice_3",
        "dice_4",
        "dice_5",
        "dice_6",
        "tree_trunk_only",
        "tree_full",
        "tree_crown_nest",
    }
)

ALLOWED_REFERENCES = frozenset(
    {
        "pencil_horizontal",
        "box",
        "cube",
        "tree_side",
    }
)

ALLOWED_SCENES = frozenset({"tree_cats", "pencil_views"})

VISUAL_TOPICS = frozenset({"几何", "组合", "计数"})

LESSON_11_QUESTION = """🐱 三只小猫在花园看一棵大树，各拍了一张照片（见下图）。

照片1、照片2、照片3 在图下方。

• 小猫 A：站在大树正下方，抬头往上看
• 小猫 B：站在大树正前方，离得稍远一点
• 小猫 C：在大树后面，身体贴着树干

👉 连一连：每张照片是谁拍的？说说你怎么想的。"""


def lesson_needs_diagram(lesson_id: int, topic: str) -> bool:
    if topic in VISUAL_TOPICS:
        return True
    return lesson_id in {3, 4, 11, 12, 16, 17, 20}


def normalize_observe_match(raw) -> dict | None:
    if not raw or not isinstance(raw, dict):
        return None
    if raw.get("type") != "observe_match":
        return None
    scene = raw.get("scene")
    if scene not in ALLOWED_SCENES:
        return None
    title = str(raw.get("title") or "").strip()[:30]
    return {"type": "observe_match", "scene": scene, "title": title}


def normalize_diagram(raw) -> dict | None:
    if not raw or not isinstance(raw, dict):
        return None

    matched = normalize_observe_match(raw)
    if matched:
        return matched

    if raw.get("type") != "views":
        return None

    panels_in = raw.get("panels") or []
    if not panels_in or len(panels_in) > 4:
        return None

    panels = []
    for idx, panel in enumerate(panels_in[:4]):
        if not isinstance(panel, dict):
            continue
        icon = panel.get("icon") or "rect"
        if icon not in ALLOWED_ICONS:
            icon = "rect"
        label = str(panel.get("label") or f"图{idx + 1}").strip()[:20]
        caption = str(panel.get("caption") or "").strip()[:40]
        item = {"label": label, "icon": icon}
        if caption:
            item["caption"] = caption
        panels.append(item)

    if not panels:
        return None

    reference = raw.get("reference")
    if reference not in ALLOWED_REFERENCES:
        reference = None

    title = str(raw.get("title") or "").strip()[:30]
    out = {"type": "views", "reference": reference, "panels": panels}
    if title:
        out["title"] = title
    return out


def default_diagram_for_lesson(lesson_id: int) -> dict | None:
    if lesson_id == 11:
        return normalize_observe_match(
            {"type": "observe_match", "scene": "tree_cats", "title": "小猫看大树"}
        )

    presets: dict[int, dict] = {
        4: {
            "type": "views",
            "title": "立体图形",
            "reference": "cube",
            "panels": [
                {"label": "图1", "icon": "square", "caption": "正面"},
                {"label": "图2", "icon": "rect", "caption": "侧面"},
                {"label": "图3", "icon": "square", "caption": "上面"},
            ],
        },
        12: {
            "type": "views",
            "title": "骰子",
            "panels": [{"label": "骰子", "icon": "dice_3", "caption": "3 点朝上"}],
        },
    }
    raw = presets.get(lesson_id)
    if raw:
        return normalize_diagram(raw)
    return normalize_diagram(
        {
            "type": "observe_match",
            "scene": "pencil_views",
            "title": "铅笔三视图",
        }
    )


def apply_lesson_diagram_overrides(lesson_id: int, question: str, diagram: dict | None) -> tuple[str, dict | None]:
    """讲次专用：固定高质量场景图 + 配套题干。"""
    if lesson_id == 11:
        return LESSON_11_QUESTION, default_diagram_for_lesson(11)
    return question, diagram


def diagram_prompt_help(lesson_id: int, topic: str) -> str:
    if not lesson_needs_diagram(lesson_id, topic):
        return '\n纯计算/文字题设 "diagram": null。\n'

    if lesson_id == 11:
        return """
本讲为多角度观察，diagram 用：{"type":"observe_match","scene":"tree_cats","title":"小猫看大树"}
question 只写连一连、谁在哪里，不要逐条描述照片里有什么（图上有）。
"""

    return """
本题涉及图形/空间想象，必须包含 diagram；question 里写情境和提问即可，视图细节交给 diagram。
可用 type=views 或 type=observe_match（scene: pencil_views）。
"""
