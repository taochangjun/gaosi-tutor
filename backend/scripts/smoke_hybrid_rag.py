"""
混合检索冒烟（BM25 + RRF）— 实现 hybrid 模块后取消 skip。

用法：
  make smoke-hybrid

前置：
  1. 已实现 bm25_index.py / hybrid.py 中全部 TODO
  2. pip install rank-bm25（见 requirements 注释）
  3. 知识库有测试数据（可先 make smoke-rag）
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.rag.bm25_index import bm25_search, build_bm25_corpus, tokenize_for_bm25
from app.agent.rag.hybrid import hybrid_search_family_notes, rrf_merge
from app.curriculum.loader import update_family_notes
from app.database import SessionLocal
from app.agent.rag.indexer import index_lesson_notes


LESSON_ID = 5
SAMPLE_NOTES = (
    "孩子减法还不太熟练，尤其是借位。\n"
    "平时喜欢用小动物情境出题，多鼓励。"
)


def _seed(db):
    update_family_notes(db, LESSON_ID, SAMPLE_NOTES)
    out = index_lesson_notes(db, LESSON_ID)
    assert out.get("ok") and out.get("chunks_indexed", 0) >= 1, out


def test_tokenize():
    tokens = tokenize_for_bm25("孩子减法借位")
    assert tokens, "分词结果不应为空"
    assert "借" in tokens or "借位" in tokens, f"应保留关键词，got {tokens}"
    print(f"[OK] tokenize: {tokens[:12]}...")


def test_bm25_corpus():
    corpus = build_bm25_corpus(force_rebuild=True)
    assert corpus.is_built(), "BM25 语料应构建成功"
    assert corpus.size >= 1, "至少 1 条 chunk"
    print(f"[OK] BM25 corpus size={corpus.size}")


def test_bm25_search():
    hits = bm25_search("借位", lesson_id=LESSON_ID, top_k=3)
    assert hits, "BM25 应命中含「借位」的笔记"
    assert any("借位" in h.get("snippet", "") for h in hits), hits
    print(f"[OK] BM25 top snippet: {hits[0]['snippet'][:40]}…")


def test_rrf_merge():
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
    keys = [_h.get("chunk_id") for _h in merged]
    assert "b" in keys, "两路都靠前的 b 应在 hybrid 前列"
    print(f"[OK] RRF merge order: {keys}")


def test_hybrid_search(db):
    out = hybrid_search_family_notes(
        db, "减法哪里薄弱", lesson_id=LESSON_ID, top_k=3
    )
    assert out.get("ok"), out
    for channel in ("vector", "bm25", "hybrid"):
        assert channel in out, f"缺少 {channel} 字段"
        assert out[channel]["hits"], f"{channel} 应有命中"
    print("[OK] hybrid 三路检索均有结果")
    print("  vector:", out["vector"]["hits"][0]["snippet"][:36], "…")
    print("  bm25:  ", out["bm25"]["hits"][0]["snippet"][:36], "…")
    print("  hybrid:", out["hybrid"]["hits"][0]["snippet"][:36], "…")


def main():
    db = SessionLocal()
    try:
        _seed(db)
        test_tokenize()
        test_bm25_corpus()
        test_bm25_search()
        test_rrf_merge()
        test_hybrid_search(db)
        print("\n[PASS] smoke-hybrid 全部通过")
    except NotImplementedError as exc:
        print(f"\n[SKIP] 尚未实现: {exc}")
        sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
