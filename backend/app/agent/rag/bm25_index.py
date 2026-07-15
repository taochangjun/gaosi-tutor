"""
BM25 关键词索引（混合检索实验 · 待你实现）。

与 Chroma 向量索引并行：
- Chroma：语义相似（「借位」≈「减法不熟」）
- BM25（Best Matching 25）：关键词匹配（query 含「借位」→ 命中含「借位」的 chunk）

学习文档：docs/rag-hybrid-exercise.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

try:
    from .store import list_all_chunks
except ImportError:
    from backend.app.agent.rag.store import list_all_chunks

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi


@dataclass
class BM25Corpus:
    """
    内存 BM25 语料。

    records: 与 Chroma chunk 一一对应，每项含 id / text / metadata
    tokenized: 每条 record 的分词结果，供 BM25Okapi 使用
    """

    records: list[dict] = field(default_factory=list)
    tokenized: list[list[str]] = field(default_factory=list)
    _bm25: BM25Okapi | None = field(default=None, repr=False)

    @property
    def size(self) -> int:
        return len(self.records)

    def is_built(self) -> bool:
        return self._bm25 is not None and self.size > 0


# 进程内缓存：避免每次检索都 get() 全量 Chroma
_corpus_cache: BM25Corpus | None = None


def tokenize_for_bm25(text: str) -> list[str]:
    """
    （练习 1）：实现中文分词。

    建议两档：
    - 入门：按字切分 list(text.replace(" ", ""))，去掉空白
    - 进阶：接入 jieba.cut_for_search

    返回非空 token 列表；空文本返回 []。
    """
    # 去掉空白
    text = text.replace(" ", "").strip()
    return list(text) if text else []


def build_bm25_corpus(*, force_rebuild: bool = False) -> BM25Corpus:
    """
    （练习 2）：从 Chroma 加载全部 chunk，构建 BM25 语料。

    步骤提示：
    1. collection.get(include=["documents", "metadatas"])
    2. 遍历 id + document + metadata，组装 records
    3. 对每条 document 调用 tokenize_for_bm25 → tokenized
    4. from rank_bm25 import BM25Okapi; corpus._bm25 = BM25Okapi(tokenized)
    5. 使用模块级 _corpus_cache，force_rebuild 时重建

    可参考 store.list_all_chunks()（已实现辅助函数）。
    """
    global _corpus_cache
    if not force_rebuild and _corpus_cache is not None and _corpus_cache.is_built():
        return _corpus_cache

    records = list_all_chunks()
    if not records:
        _corpus_cache = BM25Corpus()
        return _corpus_cache

    tokenized = [tokenize_for_bm25(c['text']) for c in records]
    corpus = BM25Corpus()
    corpus.records = records
    corpus.tokenized = tokenized
    from rank_bm25 import BM25Okapi
    corpus._bm25 = BM25Okapi(tokenized)
    _corpus_cache = corpus
    return corpus


def get_bm25_corpus() -> BM25Corpus:
    """获取（或懒加载）BM25 语料。"""
    global _corpus_cache
    if _corpus_cache is None or not _corpus_cache.is_built():
        _corpus_cache = build_bm25_corpus(force_rebuild=True)
    return _corpus_cache


def invalidate_bm25_cache() -> None:
    """
    索引变更后清空 BM25 缓存。

    （练习 6）：在 indexer 写入 Chroma 成功后调用此函数。
    """
    global _corpus_cache
    _corpus_cache = None


def bm25_search(
    query: str,
    *,
    lesson_id: int | None = None,
    top_k: int = 10,
) -> list[dict]:
    """
    （练习 3）：BM25 检索，返回与 retriever 相同结构的 hits。

    每条 hit 建议字段：
        chunk_id, lesson_id, title, topic, snippet, score, channel="bm25"

    步骤提示：
    1. corpus = get_bm25_corpus()
    2. q_tokens = tokenize_for_bm25(query)
    3. scores = corpus._bm25.get_scores(q_tokens)
    4. 按 score 降序，可选 lesson_id 过滤 metadata
    5. 归一化 score 到 0~1 便于与向量分对比（max 归一化或 sigmoid）

    无命中时返回 []。
    """
    corpus = get_bm25_corpus()
    if not corpus.is_built():
        return []

    q_tokens = tokenize_for_bm25(query)
    if not q_tokens:
        return []

    raw = corpus._bm25.get_scores(q_tokens)
    max_s = float(max(raw)) if len(raw) else 0.0

    indexed = []
    for i, s in enumerate(raw):
        rec = corpus.records[i]
        meta = rec.get("metadata") or {}
        if lesson_id is not None and meta.get("lesson_id") != lesson_id:
            continue
        indexed.append((float(s), i))

    indexed.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for s, i in indexed[: top_k]:
        rec = corpus.records[i]
        meta = rec.get('metadata') or {}
        hits.append({
            "chunk_id": rec['id'],
            "lesson_id": meta.get('lesson_id'),
            "title": meta.get('title'),
            "topic": meta.get('topic'),
            "snippet": rec.get('text', ""),
            "score": round(s / max_s, 4) if max_s > 0 else 0.0,
            "channel": "bm25",
        })

    return hits
