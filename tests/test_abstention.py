"""Abstention tests without real retrieval model (monkeypatched)."""
import json

import src.generate as gen
from src import answer_schema


def _stub_retrieve(monkeypatch, hits):
    def fake_retrieve(question, top_k=5):
        return hits
    monkeypatch.setattr(gen, "retrieve", fake_retrieve)


def _fake_hits(ids_with_scores):
    return [{"chunk_id": cid, "book_id": "G014_BOOK_003", "page": 143,
             "title": "Fundamentals of Electric Circuits",
             "text": f"text for {cid}",
             "score": score}
            for cid, score in ids_with_scores]


PASSAGE_STORE = {
    "G014_BOOK_003_P143_C02": {"book_id": "G014_BOOK_003", "page": 143,
                               "title": "Fundamentals", "chapter": "On"},
}


def test_low_score_abstains(monkeypatch, tmp_path):
    _stub_retrieve(monkeypatch, _fake_hits([("G014_BOOK_003_P143_C02", 0.12)]))
    monkeypatch.setattr(gen, "MIN_SCORE", 0.35)
    monkeypatch.setattr(gen, "PASSAGE_STORE_PATH", tmp_path / "empty.jsonl")
    payload = gen.answer("Who won the 2010 football World Cup?")
    assert payload["insufficient_evidence"] is True
    assert payload["sources"] == []
    assert answer_schema.validate_answer(payload) == []


def test_no_source_when_invalid_generated_citation(monkeypatch, tmp_path):
    hits = _fake_hits([("G014_BOOK_003_P143_C02", 0.9)])
    _stub_retrieve(monkeypatch, hits)
    # Force the "no valid source" branch: fake cite returns [].
    monkeypatch.setattr(gen.cite, "validate_citations", lambda *a, **k: [])
    monkeypatch.setattr(gen, "_extractive_answer",
                        lambda question, hits: "INSUFFICIENT-EVIDENCE")
    answer = gen.answer("What is the temperature dependence of metals?")
    assert answer["insufficient_evidence"] is True
    assert answer["sources"] == []


def test_valid_citations_kept(monkeypatch, tmp_path):
    hits = _fake_hits([("G014_BOOK_003_P143_C02", 0.91)])
    _stub_retrieve(monkeypatch, hits)
    monkeypatch.setattr(gen, "MIN_SCORE", 0.35)
    monkeypatch.setattr(gen, "PASSAGE_STORE_PATH", tmp_path / "empty.jsonl")
    monkeypatch.setattr(gen, "_load_passage_store", dict)
    # Shim generation internals with a canned grounded reply.
    monkeypatch.setattr(gen, "_local_generate_ollama",
                        lambda prompt: f"Found [G014_BOOK_003_P143_C02] — grounded.")
    payload = gen.answer("What is Ohm's law?")
    assert payload["insufficient_evidence"] is False
    assert payload["sources"][0]["chunk_id"] == "G014_BOOK_003_P143_C02"
