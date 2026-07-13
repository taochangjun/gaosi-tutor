"""家庭笔记文本切块。"""

from __future__ import annotations

import re

MAX_CHUNK_CHARS = 320
MIN_CHUNK_CHARS = 8


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _split_paragraphs(text: str) -> list[str]:
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
    """把单讲家庭笔记切成带元数据的 chunk 列表。"""
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
