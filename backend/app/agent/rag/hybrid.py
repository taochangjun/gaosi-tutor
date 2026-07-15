"""
混合检索：向量 + BM25 + RRF 融合（待你实现）。

对标公司项目 chat-test 的 ES Hybrid + RRF，在本地用 Chroma + rank_bm25 复刻思路。

学习文档：docs/rag-hybrid-exercise.md
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ...settings import get_settings
from .bm25_index import bm25_search
from .indexer import rag_stats
from .retriever import search_family_notes


def _hit_key(hit: dict) -> str:
    """RRF 去重键：优先 chunk_id，否则 snippet 前缀。"""
    if hit.get("chunk_id"):
        return str(hit["chunk_id"])
    snippet = (hit.get("snippet") or "")[:80]
    lesson = hit.get("lesson_id", "")
    return f"{lesson}:{snippet}"


def rrf_merge(
    *ranked_lists: list[dict],
    rrf_k: int = 60,
    top_k: int = 5,
) -> list[dict]:
    """
    （练习 4）：Reciprocal Rank Fusion 融合多路检索结果。

    公式（经典 RRF）：
        score(doc) = Σ 1 / (rrf_k + rank_i)
        rank_i 从 1 开始（第一名 rank=1）

    步骤提示：
    1. 对每个 ranked_list 枚举 (rank, hit)，rank 从 1 起
    2. 用 _hit_key(hit) 聚合到 dict[key] = {hit, rrf_score}
    3. 合并时保留 hit 元数据，channel 可标 "hybrid"
    4. 按 rrf_score 降序，取 top_k
    5. 输出 hit 的 score 字段填 rrf_score（或再归一化）

    参数：
        ranked_lists: 如 [vector_hits, bm25_hits]
        rrf_k: 平滑常数，chat-test 用 max(10, top_k)，默认 60 是常见论文值
    """
    merged: dict[str, dict] = {}
    for ranked_list in ranked_lists:
        for i, hit in enumerate(ranked_list):
            rank = i + 1
            key = _hit_key(hit)
            contribution = 1.0/ (rrf_k + rank)
            if key not in merged:
                merged[key] = {
                    # RRF 融合的是排名，不是整份 hit，只存第一次见到的 hit。任一路的 hit 通常够用（同一 chunk，snippet/title 本应一致）
                    "hit": dict(hit),
                    "rrf_score": 0.0
                }
            merged[key]['rrf_score'] += contribution

    items = sorted(merged.values(), key=lambda x: x.get('rrf_score'), reverse=True)

    results = []
    for item in items[:top_k]:
        hit = item["hit"]
        hit['score'] = round(item["rrf_score"], 6)
        hit["channel"] = "hybrid"
        results.append(hit)

    return results


def hybrid_search_family_notes(
    db: Session,
    query: str,
    *,
    lesson_id: int | None = None,
    top_k: int | None = None,
    rrf_k: int = 60,
    vector_top_k: int | None = None,
    bm25_top_k: int | None = None,
) -> dict:
    """
    （练习 5）：混合检索入口，对比三路结果。

    返回结构（实现后）：
    {
        "ok": True,
        "query": "...",
        "vector": {"hits": [...], "count": n},
        "bm25": {"hits": [...], "count": n},
        "hybrid": {"hits": [...], "count": n},
    }

    步骤提示：
    1. 空 query / 空知识库 → 与 search_family_notes 一致处理
    2. vector_hits = search_family_notes(..., top_k=vector_top_k)["hits"]
       给每条加 chunk_id（若无）、channel="vector"
    3. bm25_hits = bm25_search(..., top_k=bm25_top_k)
    4. hybrid_hits = rrf_merge(vector_hits, bm25_hits, rrf_k=rrf_k, top_k=top_k)
    5. 返回三路结果供 API / 脚本对比
    """
    query = query.strip()
    if not query:
        return {"ok": False, "error": "检索问题不能为空"}

    settings = get_settings()
    k = top_k or settings.rag_top_k
    v_k = vector_top_k or max(k * 2, 10)
    b_k = bm25_top_k or max(k * 2, 10)

    stats = rag_stats(db)
    if stats["chunks_in_store"] == 0:
        empty = {
            "hits": [],
            "message": "知识库为空，请先同步家庭笔记",
        }
        return {
            "ok": True,
            "query": query,
            "vector": empty,
            "bm25": empty,
            "hybrid": empty,
        }

    vector_out = search_family_notes(db, query, lesson_id=lesson_id, top_k=v_k)
    vector_hits = vector_out.get("hits") or []
    for h in vector_hits:
        h["channel"] = "vector"
    bm25_hits = bm25_search(query, lesson_id=lesson_id, top_k=b_k)
    hybrid_hits = rrf_merge(vector_hits, bm25_hits, rrf_k=rrf_k, top_k=k)

    return {
        "ok": True,
        "query": query,
        "vector": {"hits": vector_hits, "count": len(vector_hits)},
        "bm25": {"hits": bm25_hits, "count": len(bm25_hits)},
        "hybrid": {"hits": hybrid_hits, "count": len(hybrid_hits)},
    }
