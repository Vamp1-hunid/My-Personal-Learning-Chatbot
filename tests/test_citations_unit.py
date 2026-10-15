"""Unit tests for src\\citations.py — the four hard rules.

1. Invented chunk_ids are dropped even if they exist in the store.
2. Real-but-not-retrieved chunk_ids are dropped.
3. Book/page drift is rejected.
4. Duplicates collapse to one entry ordering by first mention.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def cite():
    spec = importlib.util.spec_from_file_location("citations_tested", ROOT / "src" / "citations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["citations_tested"] = mod
    spec.loader.exec_module(mod)
    return mod


STORE = {
    "G014_BOOK_003_P143_C02": {"book_id": "G014_BOOK_003", "page": 143,
                               "title": "Fundamentals"},
    "G014_BOOK_004_P078_C01": {"book_id": "G014_BOOK_004", "page": 78,
                               "title": "Circuits II"},
}
HITS = [{"chunk_id": "G014_BOOK_003_P143_C02", "book_id": "G014_BOOK_003",
         "page": 143, "title": "Fundamentals"}]


def test_extract_citations_dedupes(cite):
    text = "One [G014_BOOK_003_P143_C02] two [G014_BOOK_003_P143_C02] three."
    assert cite.extract_citations(text) == ["G014_BOOK_003_P143_C02"]


def test_invented_id_dropped_even_if_in_store(cite):
    text = "Claim [G014_BOOK_004_P078_C01]."
    assert cite.validate_citations(text, HITS, STORE) == []


def test_real_and_retrieved_id_kept(cite):
    text = "Ohm's law is V = I * R [G014_BOOK_003_P143_C02]."
    out = cite.validate_citations(text, HITS, STORE)
    assert out == [{"book_id": "G014_BOOK_003", "page": 143,
                    "chunk_id": "G014_BOOK_003_P143_C02", "title": "Fundamentals"}]


def test_drift_book_or_page_dropped(cite):
    drifted = [dict(HITS[0], page=999)]
    text = "Claim [G014_BOOK_003_P143_C02]."
    assert cite.validate_citations(text, drifted, STORE) == []
    drifted_book = [dict(HITS[0], book_id="G014_BOOK_999")]
    assert cite.validate_citations(text, drifted_book, STORE) == []


def test_mixed_text_keeps_only_valid(cite):
    text = ("A [G014_BOOK_003_P143_C02]; invented [G014_BOOK_009_P001_C01]; "
            "unretrieved [G014_BOOK_004_P078_C01].")
    out = cite.validate_citations(text, HITS, STORE)
    assert [s["chunk_id"] for s in out] == ["G014_BOOK_003_P143_C02"]


def test_no_citation_means_empty_sources(cite):
    assert cite.validate_citations("No bracket cites here.", HITS, STORE) == []
