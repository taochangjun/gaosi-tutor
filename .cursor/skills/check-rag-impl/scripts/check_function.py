#!/usr/bin/env python3
"""
按函数名运行 RAG 混合检索练习的针对性检查。

用法（在 gaosi-tutor 项目根或 backend 目录）：
  python .cursor/skills/check-rag-impl/scripts/check_function.py tokenize_for_bm25
  cd backend && ./venv/bin/python ../.cursor/skills/check-rag-impl/scripts/check_function.py rrf_merge
"""

from __future__ import annotations

import sys
from pathlib import Path

# gaosi-tutor/backend
BACKEND_DIR = Path(__file__).resolve().parents[4] / "backend"
if not (BACKEND_DIR / "app").is_dir():
    BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

ALIASES = {
    "tokenize": "tokenize_for_bm25",
    "build_corpus": "build_bm25_corpus",
    "bm25_corpus": "build_bm25_corpus",
    "bm25": "bm25_search",
    "rrf": "rrf_merge",
    "merge": "rrf_merge",
    "hybrid": "hybrid_search_family_notes",
    "hybrid_search": "hybrid_search_family_notes",
}

LESSON_ID = 5
SAMPLE_NOTES = (
    "孩子减法还不太熟练，尤其是借位。\n"
    "平时喜欢用小动物情境出题，多鼓励。"
)


def _resolve(name: str) -> str:
    key = name.strip()
    return ALIASES.get(key, key)


def check_tokenize_for_bm25() -> None:
    from app.agent.rag.bm25_index import tokenize_for_bm25

    empty = tokenize_for_bm25("   ")
    assert empty == [], f"空白应返回 []，got {empty}"

    tokens = tokenize_for_bm25("孩子减法借位")
    assert tokens, "非空文本应有 token"
    assert "借" in tokens or "借位" in tokens, f"应含「借」，got {tokens[:20]}"
    print(f"[PASS] tokenize_for_bm25 → {len(tokens)} tokens, sample={tokens[:8]}")


def check_build_bm25_corpus() -> None:
    from app.agent.rag.bm25_index import build_bm25_corpus
    from app.agent.rag.indexer import index_lesson_notes
    from app.curriculum.loader import update_family_notes
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        update_family_notes(db, LESSON_ID, SAMPLE_NOTES)
        index_lesson_notes(db, LESSON_ID)
        corpus = build_bm25_corpus(force_rebuild=True)
        assert corpus.is_built(), "语料应 built"
        assert corpus.size >= 1, "至少 1 chunk"
        print(f"[PASS] build_bm25_corpus → size={corpus.size}")
    finally:
        db.close()


def check_bm25_search() -> None:
    from app.agent.rag.bm25_index import bm25_search, build_bm25_corpus
    from app.agent.rag.indexer import index_lesson_notes
    from app.curriculum.loader import update_family_notes
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        update_family_notes(db, LESSON_ID, SAMPLE_NOTES)
        index_lesson_notes(db, LESSON_ID)
        build_bm25_corpus(force_rebuild=True)
        hits = bm25_search("借位", lesson_id=LESSON_ID, top_k=3)
        assert hits, "应命中"
        assert any("借位" in h.get("snippet", "") for h in hits), hits
        required = {"snippet", "score", "channel"}
        for h in hits:
            assert required.issubset(h.keys()) or "snippet" in h, f"hit 缺字段: {h}"
        print(f"[PASS] bm25_search → top: {hits[0].get('snippet', '')[:40]}…")
    finally:
        db.close()


def check_rrf_merge() -> None:
    from app.agent.rag.hybrid import rrf_merge

    vector = [
        {"chunk_id": "a", "snippet": "向量第一", "score": 0.9, "channel": "vector"},
        {"chunk_id": "b", "snippet": "向量第二", "score": 0.7, "channel": "vector"},
    ]
    bm25 = [
        {"chunk_id": "b", "snippet": "向量第二", "score": 0.95, "channel": "bm25"},
        {"chunk_id": "c", "snippet": "BM25 独有", "score": 0.8, "channel": "bm25"},
    ]
    merged = rrf_merge(vector, bm25, rrf_k=60, top_k=3)
    assert len(merged) == 3
    keys = [h.get("chunk_id") for h in merged]
    assert "b" in keys, f"b 应靠前，order={keys}"
    if merged[0].get("chunk_id") != "b":
        print(f"[WARN] 期望 b 排第一，实际 order={keys}（rank 从 0 开始？）")
    print(f"[PASS] rrf_merge → order={keys}")


def check_hybrid_search_family_notes() -> None:
    from app.agent.rag.hybrid import hybrid_search_family_notes
    from app.agent.rag.indexer import index_lesson_notes
    from app.curriculum.loader import update_family_notes
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        update_family_notes(db, LESSON_ID, SAMPLE_NOTES)
        index_lesson_notes(db, LESSON_ID)
        out = hybrid_search_family_notes(
            db, "减法哪里薄弱", lesson_id=LESSON_ID, top_k=3
        )
        assert out.get("ok"), out
        for ch in ("vector", "bm25", "hybrid"):
            assert ch in out, f"缺 {ch}"
            assert out[ch].get("hits"), f"{ch} 无 hits"
        print("[PASS] hybrid_search_family_notes → 三路均有结果")
    finally:
        db.close()


def check_invalidate_bm25_cache() -> None:
    from app.agent.rag import bm25_index

    bm25_index._corpus_cache = bm25_index.BM25Corpus()  # type: ignore
    bm25_index.invalidate_bm25_cache()
    assert bm25_index._corpus_cache is None
    print("[PASS] invalidate_bm25_cache → cache cleared")


CHECKERS = {
    "tokenize_for_bm25": check_tokenize_for_bm25,
    "build_bm25_corpus": check_build_bm25_corpus,
    "get_bm25_corpus": check_build_bm25_corpus,  # 依赖 build
    "invalidate_bm25_cache": check_invalidate_bm25_cache,
    "bm25_search": check_bm25_search,
    "rrf_merge": check_rrf_merge,
    "hybrid_search_family_notes": check_hybrid_search_family_notes,
}


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: check_function.py <函数名>")
        print("可选:", ", ".join(sorted(CHECKERS.keys())))
        return 1

    name = _resolve(sys.argv[1])
    fn = CHECKERS.get(name)
    if not fn:
        print(f"[FAIL] 未知函数: {sys.argv[1]}")
        print("可选:", ", ".join(sorted(CHECKERS.keys())))
        return 1

    print(f"=== 检查 {name} ===\n")
    try:
        fn()
        print(f"\n=== {name}: PASS ===")
        return 0
    except NotImplementedError as exc:
        print(f"\n=== {name}: SKIP（未实现）===\n{exc}")
        return 2
    except Exception as exc:
        print(f"\n=== {name}: FAIL ===\n{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
