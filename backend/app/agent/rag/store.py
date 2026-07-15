"""
Chroma 向量库封装（RAG 持久化层）。

职责：
- 管理 PersistentClient（数据落盘 backend/data/chroma，可配 RAG_CHROMA_PATH）
- 维护单一 collection「family_notes」
- upsert / delete / count / query 的薄封装

MySQL lesson_progress 存原文（source of truth）；
本模块存 embedding 副本，可随时删目录后 reindex 重建。

Collection 使用 cosine 距离（hnsw:space），与 bge 类模型常见配置一致。

详见 docs/fastembed-learning.md、docs/chroma-learning.md。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from ...settings import get_settings

# 全项目只用一个逻辑集合：家庭笔记向量
COLLECTION_NAME = "family_notes"

# 关闭 Chroma 匿名遥测
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")


def get_chroma_path() -> Path:
    """
    解析 Chroma 持久化目录。

    相对路径相对于 backend/ 根目录（与 settings 默认值 data/chroma 一致）。
    目录不存在时自动创建。
    """
    settings = get_settings()
    path = Path(settings.rag_chroma_path)
    if not path.is_absolute():
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        path = backend_dir / path
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache()
def _get_client():
    """
    进程级单例 Chroma 客户端。

    PersistentClient：向量存在本地 SQLite + 文件，重启后无需重建索引。
    多 worker 部署时各进程各写各的目录，生产应换 Qdrant 等共享存储。
    """
    return chromadb.PersistentClient(path=str(get_chroma_path()))


def get_collection() -> Collection:
    """
    获取或创建 family_notes 集合。

    metadata hnsw:space=cosine：ANN 检索时用余弦距离，越小越相似。
    """
    return _get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(chunks: list[dict], vectors: list[list[float]]) -> int:
    """
    写入或更新 chunk 向量。

    chunks 来自 chunker（含 id / text / metadata）；
    vectors 来自 embedder，与 chunks 一一对应、等长。

    upsert 语义：同 id 覆盖旧记录，适合笔记修改后 reindex。
    """
    if not chunks:
        return 0
    collection = get_collection()
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],  # 原文冗余存储，检索时直接返回 snippet
        embeddings=vectors,
        metadatas=[c["metadata"] for c in chunks],
    )
    return len(chunks)


def delete_lesson_chunks(lesson_id: int) -> None:
    """
    删除某一讲在 Chroma 中的全部 chunk。

    单讲 reindex 前先删后写，避免旧段落残留；
    笔记清空时只删不写。
    """
    collection = get_collection()
    try:
        collection.delete(where={"lesson_id": lesson_id})
    except Exception:
        # 集合为空、或 chroma 版本对 where 行为差异时，忽略即可
        pass


def count_chunks() -> int:
    """当前 collection 中的向量条数（health / rag_stats / 检索上限用）。"""
    collection = get_collection()
    return collection.count()


def list_all_chunks() -> list[dict]:
    """
    读取 Chroma 中全部 chunk（构建 BM25 语料用）。

    返回：[{id, text, metadata}, ...]
    空库返回 []。
    """
    collection = get_collection()
    if collection.count() == 0:
        return []
    result = collection.get(include=["documents", "metadatas"])
    chunks: list[dict] = []
    for chunk_id, doc, meta in zip(
        result.get("ids") or [],
        result.get("documents") or [],
        result.get("metadatas") or [],
    ):
        chunks.append(
            {
                "id": chunk_id,
                "text": doc or "",
                "metadata": meta or {},
            }
        )
    return chunks


def list_indexed_lesson_ids() -> set[int]:
    """
    Chroma 中当前存有 chunk 的讲次 id 集合。

    全量索引收尾时与 MySQL 有笔记讲次做差集，只删「库里有、笔记已空」的残留。
    """
    collection = get_collection()
    if collection.count() == 0:
        return set()
    result = collection.get(include=["metadatas"])
    lesson_ids: set[int] = set()
    for meta in result.get("metadatas") or []:
        if not meta or "lesson_id" not in meta:
            continue
        lesson_ids.add(int(meta["lesson_id"]))
    return lesson_ids
