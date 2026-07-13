"""
家庭笔记文本切块（RAG Index 第一步）。

为什么切块：
- 整篇笔记 embed 成一个向量会「语义平均」，细粒度问题（如只问「借位」）召回差
- LLM 只需要 top-K 段片段，不必全文塞进 context

切块策略：按换行分段 → 单段超过 MAX_CHUNK_CHARS 再硬切（无 overlap）

输出结构供 indexer 与 Chroma upsert 使用：
  id, text, metadata(lesson_id, title, topic, chunk_index)

强制关键字参数（`def f(*, a, b)`）见 docs/python-basics-learning.md §3。
"""

from __future__ import annotations

import re

# 单 chunk 最大字符数：家庭笔记通常几条 bullet，320 字足够且控制 embedding 噪声
MAX_CHUNK_CHARS = 320
# 过短片段（如「好」「嗯」）无检索价值，丢弃
MIN_CHUNK_CHARS = 8


def _normalize(text: str) -> str:
    """统一换行符、去掉首尾空白、合并多余空行。"""
    # 统一处理不同系统的换行符 (Windows 换行符：如果文本中包含 \r\n（Windows 换行符），需要先统一处理)
    text = text.replace("\r\n", "\n").strip()
    # re.sub Python 正则替换函数，在字符串中查找匹配模式并替换
    # 将 text 中连续出现 3 个或以上的换行符 \n，替换为 2 个换行符 \n\n
    # 不会影响单个或双个换行：代码只压缩 3 个及以上的连续换行，保留正常的段落间距（2 个换行）不变
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _split_paragraphs(text: str) -> list[str]:
    """按一个或多个换行切成段落（家长笔记常见：每行一条要点）。
    re.split(r"\n+", text): 使用一个或多个连续换行符 \n 作为分隔符，将 text 字符串拆分成一个列表
    re.split()	Python 正则分割函数，根据匹配的模式切割字符串
    r"\n+"	正则模式：匹配 1 个或多个连续换行符

    import re
    # 原始文本
    text = "第一段\n第二段\n\n第三段\n\n\n第四段"

    # 使用 re.split
    result = re.split(r"\n+", text)
    print(result)
    # 输出: ['第一段', '第二段', '第三段', '第四段']

    # 对比普通的 str.split('\n')
    print(text.split('\n'))
    # 输出: ['第一段', '第二段', '', '第三段', '', '', '第四段']
    """

    parts = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    if not parts:
        return []
    return parts


def chunk_family_note(
    *,
    lesson_id: int,
    title: str,
    topic: str,
    notes: str,
) -> list[dict]:
    """
    把单讲家庭笔记切成带元数据的 chunk 列表。

    返回空列表的情况：
    - 全文短于 MIN_CHUNK_CHARS
    - 各段切完后均短于 MIN_CHUNK_CHARS

    chunk id 规则：lesson-{讲次}-chunk-{序号}
    同一讲 reindex 时 id 稳定，Chroma upsert 会覆盖同 id 旧向量。
    """
    notes = _normalize(notes)
    if len(notes) < MIN_CHUNK_CHARS:
        return []

    chunks: list[dict] = []
    paragraphs = _split_paragraphs(notes)
    chunk_idx = 0

    for para in paragraphs:
        if len(para) <= MAX_CHUNK_CHARS:
            pieces = [para]
        else:
            # 超长段落按固定窗口滑动切分（本项目笔记很少触发）
            pieces = []
            start = 0
            while start < len(para):
                end = min(start + MAX_CHUNK_CHARS, len(para))
                piece = para[start:end].strip()
                if piece:
                    pieces.append(piece)
                start = end

        for piece in pieces:
            if len(piece) < MIN_CHUNK_CHARS:
                continue
            chunks.append(
                {
                    "id": f"lesson-{lesson_id}-chunk-{chunk_idx}",
                    "text": piece,
                    # metadata 会写入 Chroma，检索时可按 lesson_id 过滤
                    "metadata": {
                        "lesson_id": lesson_id,
                        "title": title,
                        "topic": topic,
                        "chunk_index": chunk_idx,
                    },
                }
            )
            chunk_idx += 1

    return chunks
