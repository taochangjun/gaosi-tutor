"""
Rerank 精排：本地 Cross-Encoder / 智谱 API / off。

粗排（向量 / BM25 / Hybrid）负责高 Recall；
本模块对短名单候选做 query↔doc 打分，提高 Top-N Precision。

Provider（环境变量 RERANK_PROVIDER，见练习 7）：
  local — fastembed TextCrossEncoder（默认）
  zhipu — 智谱 POST /paas/v4/rerank（需 ZHIPU_API_KEY）
  off   — 不调模型，按粗排原序截断并标 channel=rerank

学习文档：docs/rag-rerank-exercise.md
理论参考：docs/rag-rerank.md
"""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _ssl_context() -> ssl.SSLContext:
    """macOS 官方 Python 常缺系统 CA；优先用 certifi 证书包。"""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# 进程内缓存 Cross-Encoder，避免每次检索重新加载
_encoder: Any = None

DEFAULT_TOP_N = 3
DEFAULT_MAX_DOC_CHARS = 1024
VALID_PROVIDERS = frozenset({"local", "zhipu", "off"})


def _doc_text_from_hit(hit: dict) -> str:
    """
    （练习 1）：取出要送给 reranker 的文档文本。

    优先 snippet，其次 text；strip；过长截断到 DEFAULT_MAX_DOC_CHARS。
    """
    text = (hit.get("snippet") or hit.get("text") or "").strip()
    return text[:DEFAULT_MAX_DOC_CHARS]


def resolve_rerank_provider(provider: str | None = None) -> str:
    """规范化 provider；非法值回退 local。"""
    from ...settings import get_settings

    raw = (provider if provider is not None else get_settings().rerank_provider) or "local"
    name = str(raw).strip().lower()
    return name if name in VALID_PROVIDERS else "local"


def _get_encoder():
    """懒加载 fastembed TextCrossEncoder（练习 2a 可改模型名）。"""
    global _encoder
    if _encoder is None:
        from ...settings import configure_hf_endpoint, get_settings

        endpoint = configure_hf_endpoint()
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        settings = get_settings()
        model_name = settings.rag_rerank_model
        print(f"[RAG] 加载 Rerank 模型 {model_name}（HF_ENDPOINT={endpoint}）")
        _encoder = TextCrossEncoder(model_name=model_name)
    return _encoder


def score_pairs_zhipu(query: str, docs: list[str]) -> list[float]:
    """
    智谱 Rerank API：POST {base}/rerank。

    返回与 docs 等长的分数（按原始下标填入 relevance_score）。
    """
    from ...settings import get_settings

    if not docs:
        return []
    settings = get_settings()
    api_key = (settings.zhipu_api_key or "").strip()
    if not api_key:
        raise RuntimeError("RERANK_PROVIDER=zhipu 需要配置 ZHIPU_API_KEY")

    base = (settings.zhipu_base_url or "").rstrip("/")
    url = f"{base}/rerank"
    body = {
        "model": settings.zhipu_rerank_model or "rerank",
        "query": query,
        "documents": docs,
        "top_n": len(docs),
        "return_documents": False,
    }
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"智谱 Rerank HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"智谱 Rerank 网络错误: {exc.reason}") from exc

    scores = [0.0] * len(docs)
    for item in payload.get("results") or []:
        idx = int(item["index"])
        if 0 <= idx < len(docs):
            scores[idx] = float(item["relevance_score"])
    return scores


def score_pairs(
    query: str,
    docs: list[str],
    *,
    provider: str | None = None,
) -> list[float]:
    """
    （练习 2a / 7）：对 (query, docs) 成对打分，返回与 docs 等长的分数列表。

    provider:
      local — TextCrossEncoder
      zhipu — 智谱 API
      off   — 按原序递减假分（仅保持顺序，交给 rerank_hits 截断）
    """
    if not docs:
        return []
    prov = resolve_rerank_provider(provider)
    if prov == "off":
        # 降序假分：保持粗排原序
        n = len(docs)
        return [float(n - i) for i in range(n)]
    if prov == "zhipu":
        return score_pairs_zhipu(query, docs)
    return list(_get_encoder().rerank(query, docs))


def rerank_hits(
    query: str,
    hits: list[dict],
    *,
    top_n: int = DEFAULT_TOP_N,
    score_fn: Callable[[str, list[str]], list[float]] | None = None,
    provider: str | None = None,
) -> list[dict]:
    """
    （练习 2b / 7）：对粗排 hits 精排，返回长度 ≤ top_n 的新列表。

    score_fn: 可选注入（冒烟测试用）；默认按 RERANK_PROVIDER 选打分后端。
    provider: 覆盖 settings.rerank_provider（单测 / 临时切换）。
    """
    query = (query or "").strip()
    if not query or not hits or top_n <= 0:
        return []

    docs = [_doc_text_from_hit(h) for h in hits]
    if score_fn is not None:
        scores = list(score_fn(query, docs))
    else:
        scores = score_pairs(query, docs, provider=provider)
    if len(scores) != len(hits):
        raise ValueError(
            f"score_fn 返回长度 {len(scores)} 与 hits {len(hits)} 不一致"
        )

    ranked = sorted(
        zip(hits, scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    results: list[dict] = []
    for hit, score in ranked[:top_n]:
        out = dict(hit)
        out["score"] = float(score)
        out["channel"] = "rerank"
        results.append(out)
    return results
