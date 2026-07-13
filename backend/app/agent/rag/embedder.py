"""本地中文 Embedding（fastembed，无需额外 API Key）。"""

from __future__ import annotations

from functools import lru_cache

from ...settings import get_settings


@lru_cache()
def _get_model():
    from fastembed import TextEmbedding

    settings = get_settings()
    return TextEmbedding(model_name=settings.rag_embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_query(query: str) -> list[float]:
    vectors = embed_texts([query])
    return vectors[0] if vectors else []
