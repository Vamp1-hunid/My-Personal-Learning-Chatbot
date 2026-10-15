"""Unit tests for src\\chunk.py — pure logic, runs with pytest on the target laptop.

The module imports PyYAML at load time; these tests force a deterministic stub
config (chunk_words=5, overlap=2, min_words=4) so the expected chunk counts and
overlaps are exact on both a minimal environment and the laptop with real
requirements installed.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FAKE_CFG = {"chunk_words": 5, "overlap_words": 2, "min_words": 4}


@pytest.fixture(scope="module")
def chunk():
    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda *_a, **_k: dict(FAKE_CFG)
    sys.modules["yaml"] = fake_yaml          # force deterministic config for this module
    spec = importlib.util.spec_from_file_location("chunk_tested", ROOT / "src" / "chunk.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chunk_tested"] = mod
    spec.loader.exec_module(mod)
    yield mod


def test_clean_text_fixes_hyphens_and_whitespace(chunk):
    raw = "oppression\u00ad test-\nword.   lots of    spaces\n\n\n\nmore"
    out = chunk.clean_text(raw)
    assert "testword" in out and "oppression" in out
    assert "lots of spaces" in out
    assert "\n\n\n" not in out


def test_pages_below_min_words_yield_no_chunks(chunk):
    words3 = " ".join("w%d" % i for i in range(3))          # < min_words
    assert list(chunk.chunk_page(words3)) == []


def test_page_at_min_words_yields_one_chunk(chunk):
    words4 = " ".join("w%d" % i for i in range(4))          # == min_words
    pieces = list(chunk.chunk_page(words4))
    assert len(pieces) == 1 and pieces[0].startswith("w0")


def test_windows_stride_and_overlap(chunk):
    words = " ".join("w%02d" % i for i in range(12))
    pieces = [p.split() for p in chunk.chunk_page(words)]
    # window 5, overlap 2 → stride 3: chunk starts at word 0, 3, 6, 9
    assert pieces[0][0] == "w00"
    assert pieces[1][0] == "w03"
    assert pieces[-1][-1] == "w11"
    for prev, nxt in zip(pieces, pieces[1:]):
        assert set(prev) & set(nxt), "consecutive chunks must overlap"


def test_chunks_never_cross_pages_and_ids_are_unique(chunk):
    pages = {"BK": [{"page": 1, "text": " ".join("a%d" % i for i in range(10))},
                    {"page": 2, "text": " ".join("b%d" % i for i in range(10))}]}
    rows = chunk.build_passages(pages)
    p1 = [r for r in rows if r["page"] == 1]
    p2 = [r for r in rows if r["page"] == 2]
    assert p1 and p2
    assert all(r["text"].startswith("a") for r in p1)        # page-2 words never leak in
    assert all(r["text"].startswith("b") for r in p2)
    ids = [r["chunk_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_chunk_id_and_group_contract(chunk):
    rows = chunk.build_passages(
        {"G014_BOOK_003": [{"page": 143, "text": " ".join("c%d" % i for i in range(50))}]})
    for r in rows:
        assert r["chunk_id"].startswith("G014_BOOK_003_P143_C")
        assert r["group_id"] == "G014"
        assert r["text"] == " ".join(r["text"].split()), "no stray whitespace in chunks"


def test_empty_page_text_is_skipped(chunk):
    rows = chunk.build_passages({"BK": [{"page": 1, "text": ""}]})
    assert rows == []
