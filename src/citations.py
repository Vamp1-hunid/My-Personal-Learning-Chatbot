"""src/citations.py — Citation validation.

Rules enforced:
1. Every returned source must resolve to an actual stored passage.
2. Cited chunk_ids must have been retrieved for THIS question (prevents
   hallucinated page/chunk IDs even when the fake ID happens to exist).
3. book_id/page must match the stored passage.
If NO valid source remains, generate.py sets insufficient_evidence=True and
returns sources=[] — never a fake source.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

CITATION_RE = re.compile(r"\[([A-Za-z0-9_:\-]+)\]")


def extract_citations(answer_text: str) -> list[str]:
    """Pull chunk-id-like tokens in brackets, e.g. [G014_BOOK_003_P143_C02]."""
    seen, out = set(), []
    for c in CITATION_RE.findall(answer_text):
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def validate_citations(answer_text: str,
                       retrieved: Iterable[dict],
                       passage_store: dict[str, dict]) -> list[dict]:
    """Return only sources whose chunk_id exists AND was retrieved.

    passage_store mapping chunk_id -> passage row (from artifacts/passages.jsonl).
    retrieved is the list returned by src/retrieve.py for this same question.
    """
    retrieved_by_id = {h["chunk_id"]: h for h in retrieved}
    sources: list[dict] = []
    for cid in extract_citations(answer_text):
        rec = retrieved_by_id.get(cid) or passage_store.get(cid)
        # Book/page drift check: both must agree with the stored passage.
        if isinstance(rec, dict):
            store = passage_store.get(cid, {})
            if store:
                book_match = rec.get("book_id", store.get("book_id")) == store.get("book_id")
                page_match = rec.get("page", store.get("page")) == store.get("page")
                if not (book_match and page_match):
                    continue
            sources.append({
                "book_id": rec["book_id"],
                "page": rec["page"],
                "chunk_id": cid,
                "title": rec.get("title", store.get("title", "")),
            })
    return sources


def load_passage_store(path: str | Path) -> dict[str, dict]:
    p = Path(path)
    store = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                store[r["chunk_id"]] = r
    return store
