"""Chroma 向量库封装。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from ...settings import get_settings

COLLECTION_NAME = "family_notes"

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def get_chroma_path() -> Path:
    settings = get_settings()
    path = Path(settings.rag_chroma_path)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        path = backend_dir / path
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache()
def _get_client():
    return chromadb.PersistentClient(path=str(get_chroma_path()))


def get_collection() -> Collection:
    return _get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks: list[dict], vectors: list[list[float]]) -> int:
    if not chunks:
        return 0
    collection = get_collection()
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=vectors,
        metadatas=[c["metadata"] for c in chunks],
    )
    return len(chunks)


def delete_lesson_chunks(lesson_id: int) -> None:
    collection = get_collection()
    try:
        collection.delete(where={"lesson_id": lesson_id})
    except Exception:
        # 集合为空或旧版本 chroma 无匹配时忽略
        pass


def count_chunks() -> int:
    collection = get_collection()
    return collection.count()
