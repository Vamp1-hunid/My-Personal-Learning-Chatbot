"""Retrieval contract test.

Skips gracefully if faiss / sentence-transformers are missing (e.g. doctor
says CPU-only box without them installed yet), but when present validates the
assignment's integration contract:
    retrieve(question, top_k) -> [{text, score, book_id, title, page, chunk_id}]
"""
import pytest

faiss = pytest.importorskip("faiss")
st = pytest.importorskip("sentence_transformers")
np = pytest.importorskip("numpy")

from src.retrieve import Retriever  # noqa: E402


def test_fields_present_and_top_k_respected():
    r = Retriever()
    hits = r.retrieve("What is Ohm's law?", top_k=3)
    assert len(hits) <= 3
    for h in hits:
        assert {"text", "score", "book_id", "title", "page", "chunk_id"} <= set(h)
        assert h["score"] >= -1.0 and h["score"] <= 1.0


def test_empty_question_returns_empty_list():
    r = Retriever()
    assert r.retrieve("   ", top_k=3) == []
