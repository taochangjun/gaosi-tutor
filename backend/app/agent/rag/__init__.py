"""
家庭笔记 RAG 包入口。

管线分工：
  chunker.py   — 文本切块
  embedder.py  — 本地向量（fastembed）
  store.py     — Chroma 读写
  indexer.py   — MySQL → 索引（Index）
  retriever.py — 语义检索（Retrieve）
  bm25_index.py — BM25 关键词索引（混合检索练习）
  hybrid.py      — RRF 融合检索（混合检索练习）
  reranker.py    — Cross-Encoder 精排（Rerank 练习 · TODO）

对外常用 API（供 router / tools / 脚本）：
  index_lesson_notes, index_all_notes, rag_stats, search_family_notes

Augment + Generate 在 Agent loop 中完成（tool message → LLM）。

学习文档：docs/fastembed-learning.md、docs/chroma-learning.md、docs/vector-db-learning.md、
docs/rag-hybrid-exercise.md、docs/rag-rerank-exercise.md
"""

from .indexer import index_all_notes, index_lesson_notes, rag_stats
from .retriever import search_family_notes

__all__ = [
    "index_all_notes",
    "index_lesson_notes",
    "rag_stats",
    "search_family_notes",
]
