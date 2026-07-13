"""
本地中文 Embedding（RAG Index / Retrieve 共用）。

库：fastembed（ONNX 推理，CPU 可跑，无需 Embedding API Key）
默认模型：BAAI/bge-small-zh-v1.5（settings.rag_embedding_model）

重要约束：
- 索引（embed_texts）与查询（embed_query）必须用同一模型，否则向量空间不一致
- 更换模型后必须删 data/chroma 并全量 reindex

模型实例用 @lru_cache 单例，避免每次请求重复加载权重。

详见 docs/fastembed-learning.md。
"""

from __future__ import annotations

from functools import lru_cache

from ...settings import get_settings


@lru_cache()
def _get_model():
    """懒加载 TextEmbedding；首次调用会下载模型文件，略慢。"""
    from fastembed import TextEmbedding

    settings = get_settings()
    return TextEmbedding(model_name=settings.rag_embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    批量把文本转为向量（索引阶段使用）。

    入参：chunk 的 text 列表
    出参：与 texts 等长的 float 列表，每个约 512 维（取决于模型）
    """
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_query(query: str) -> list[float]:
    """
    单条用户问题转向量（检索阶段使用）。

    与 embed_texts 走同一模型；语义上 query 与 document 在同一空间比距离。
    """
    vectors = embed_texts([query])
    return vectors[0] if vectors else []
