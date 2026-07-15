"""
Rerank 精排冒烟 — 实现 reranker + hybrid 接入后应全绿。

用法：
  make smoke-rerank

前置：
  1. 已完成 docs/rag-hybrid-exercise.md（make smoke-hybrid 通过）
  2. 已实现 rag/reranker.py 中 TODO
  3. 已按 docs/rag-rerank-exercise.md 练习 3 让 hybrid 返回 rerank 字段
  4. fastembed 已安装（TextCrossEncoder）；首次真实打分会下载模型
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agent.rag.hybrid import hybrid_search_family_notes
from app.agent.rag.reranker import _doc_text_from_hit, rerank_hits
from app.curriculum.loader import get_family_notes, update_family_notes
from app.database import SessionLocal
from app.agent.rag.indexer import index_lesson_notes


LESSON_ID = 5
SAMPLE_NOTES = (
    "孩子减法还不太熟练，尤其是借位。\n"
    "平时喜欢用小动物情境出题，多鼓励。"
)


def _seed(db):
    """确保第 5 讲有「借位」可测数据；已有笔记则不覆盖。"""
    existing = (get_family_notes(db, LESSON_ID) or "").strip()
    if "借位" in existing:
        out = index_lesson_notes(db, LESSON_ID)
    else:
        update_family_notes(db, LESSON_ID, SAMPLE_NOTES)
        out = index_lesson_notes(db, LESSON_ID)
    assert out.get("ok") and out.get("chunks_indexed", 0) >= 1, out


def test_doc_text():
    assert _doc_text_from_hit({"snippet": "借位"}) == "借位"
    assert _doc_text_from_hit({"text": "  小动物  "}) == "小动物"
    long = "甲" * 2000
    out = _doc_text_from_hit({"snippet": long})
    assert len(out) <= 1024, "过长文本应截断"
    print("[OK] _doc_text_from_hit")


def test_rerank_empty():
    assert rerank_hits("", [{"snippet": "x"}]) == []
    assert rerank_hits("借位", []) == []
    print("[OK] rerank_hits 空输入")


def test_rerank_with_injected_scorer():
    hits = [
        {"chunk_id": "a", "snippet": "喜欢小动物出题", "score": 0.9, "channel": "hybrid"},
        {"chunk_id": "b", "snippet": "孩子减法借位还不熟练", "score": 0.5, "channel": "hybrid"},
        {"chunk_id": "c", "snippet": "多鼓励", "score": 0.4, "channel": "hybrid"},
    ]
    out = rerank_hits(
        "借位",
        hits,
        top_n=2,
        score_fn=lambda _q, docs: [0.1, 0.95, 0.2],
    )
    assert len(out) == 2, out
    assert out[0]["chunk_id"] == "b", out
    assert out[0]["channel"] == "rerank"
    assert out[0]["score"] == 0.95
    print(f"[OK] rerank_hits 注入打分: {[h['chunk_id'] for h in out]}")


def test_provider_off_preserves_order():
    """RERANK_PROVIDER=off：不按内容打分，保持粗排原序截断。"""
    hits = [
        {"chunk_id": "a", "snippet": "第一"},
        {"chunk_id": "b", "snippet": "第二（其实更相关借位）"},
        {"chunk_id": "c", "snippet": "第三"},
    ]
    out = rerank_hits("借位", hits, top_n=2, provider="off")
    assert [h["chunk_id"] for h in out] == ["a", "b"], out
    assert all(h["channel"] == "rerank" for h in out)
    print("[OK] provider=off 保持原序")


def test_hybrid_has_rerank(db):
    # provider=off：不下载本地 CE，仍验证接入字段
    out = hybrid_search_family_notes(
        db,
        "减法哪里薄弱",
        lesson_id=LESSON_ID,
        top_k=3,
        with_rerank=True,
        rerank_provider="off",
    )
    assert out.get("ok"), out
    assert "rerank" in out, "hybrid 出口应含 rerank 字段（练习 3）"
    rerank = out["rerank"]
    assert "hits" in rerank, rerank
    hits = rerank.get("hits") or []
    # 有知识库时应有 hits；失败 fallback 也应非空（若 hybrid 有候选）
    hybrid_hits = (out.get("hybrid") or {}).get("hits") or []
    if hybrid_hits:
        assert hits, "有 hybrid 候选时 rerank 不应为空（含 fallback）"
        assert len(hits) <= 3
        assert all(h.get("channel") == "rerank" for h in hits), hits
    print(f"[OK] hybrid+rerank count={len(hits)}")
    if hits:
        print(f"  rerank top: {hits[0].get('snippet', '')[:40]}…")


def main():
    db = SessionLocal()
    try:
        _seed(db)
        test_doc_text()
        test_rerank_empty()
        test_rerank_with_injected_scorer()
        test_provider_off_preserves_order()
        test_hybrid_has_rerank(db)
        print("\n[PASS] smoke-rerank 全部通过")
    except NotImplementedError as exc:
        print(f"\n[SKIP] 尚未实现: {exc}")
        sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
