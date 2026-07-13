"""家庭笔记语义检索。"""

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
    where = {"lesson_id": lesson_id} if lesson_id else None
    query_vec = embed_query(query)

    try:
        result = collection.query(
            query_embeddings=[query_vec],
            n_results=min(k, stats["chunks_in_store"]),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        return {"ok": False, "error": f"检索失败: {exc}"}

    hits = []
    docs = result.get("documents") or [[]]
    metas = result.get("metadatas") or [[]]
    dists = result.get("distances") or [[]]

    for doc, meta, dist in zip(docs[0], metas[0], dists[0]):
        # cosine distance: 越小越相似；转成 0~1 的 score 便于展示
        score = round(max(0.0, 1.0 - float(dist)), 4)
        hits.append(
            {
                "lesson_id": meta.get("lesson_id"),
                "title": meta.get("title"),
                "topic": meta.get("topic"),
                "snippet": doc,
                "score": score,
            }
        )

    return {"ok": True, "query": query, "hits": hits, "count": len(hits)}
