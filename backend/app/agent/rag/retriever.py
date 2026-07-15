"""
家庭笔记语义检索（RAG Retrieve）。

流程：
  用户 query → embed_query() → Chroma collection.query(top-K)
  → 返回 hits（snippet + score + 讲次元数据）

db 用途：
- rag_stats() 判断知识库是否为空、统计有笔记讲数
- 检索本身不查 MySQL（向量已在 Chroma）

调用方：
- Agent tool search_family_notes（tools.py）
- POST /api/rag/search（调试用）
- scripts/smoke_rag.py

详见 docs/agent-rag.md §8。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...settings import get_settings
from .embedder import embed_query
from .indexer import rag_stats
from .store import get_collection


def search_family_notes(
    db: Session,
    query: str,
    *,
    lesson_id: int | None = None,
    top_k: int | None = None,
) -> dict:
    """
    按语义相似度检索家庭笔记片段。

    参数：
        query: 自然语言问题，如「孩子减法哪里薄弱」
        lesson_id: 可选，限定只搜某一讲（Chroma metadata 过滤）
        top_k: 返回条数，默认 settings.rag_top_k（通常 3）

    返回：
        ok, query, hits[], count
        hits 每项：chunk_id, lesson_id, title, topic, snippet, score
        score ≈ 1 - cosine_distance，越大越相似（仅本库内可比）

    知识库为空时 ok=True 但 hits=[]，并带引导家长同步的 message。
    """
    query = query.strip()
    if not query:
        return {"ok": False, "error": "检索问题不能为空"}

    settings = get_settings()
    k = top_k or settings.rag_top_k

    stats = rag_stats(db)
    if stats["chunks_in_store"] == 0:
        return {
            "ok": True,
            "hits": [],
            "message": "知识库为空，请家长在「家庭笔记」填写内容后点击「同步知识库」",
        }

    collection = get_collection()
    # lesson_id 有值时：先按 metadata 过滤，再在子集内 ANN（HNSW）
    where = {"lesson_id": lesson_id} if lesson_id else None
    query_vec = embed_query(query)

    try:
        result = collection.query(
            query_embeddings=[query_vec],
            # 向量总数可能小于 k，取较小值
            n_results=min(k, stats["chunks_in_store"]),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        return {"ok": False, "error": f"检索失败: {exc}"}

    hits = []
    # Chroma 返回二维列表（支持多 query）；本项目每次只查 1 条 query
    ids = result.get("ids") or [[]]
    docs = result.get("documents") or [[]]
    metas = result.get("metadatas") or [[]]
    dists = result.get("distances") or [[]]

    for chunk_id, doc, meta, dist in zip(ids[0], docs[0], metas[0], dists[0]):
        # cosine distance：0 最相似；转成 score 便于前端/LLM 阅读
        score = round(max(0.0, 1.0 - float(dist)), 4)
        hits.append(
            {
                "chunk_id": chunk_id,
                "lesson_id": meta.get("lesson_id"),
                "title": meta.get("title"),
                "topic": meta.get("topic"),
                "snippet": doc,
                "score": score,
            }
        )

    return {"ok": True, "query": query, "hits": hits, "count": len(hits)}
