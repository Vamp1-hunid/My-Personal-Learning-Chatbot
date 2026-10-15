"""src/chunk.py — Cleaning and chunking stage.

Reads data/artifacts/fulltext/*.jsonl, cleans each page (soft hyphens, joined
blocks, headings, page numbers of print vs PDF — PDF physical page is kept
canonical and printed page is stored separately for citations), then chunks per
page (never across books/pages) using overlapping word windows from
config/chunking.yaml. Saves artifacts/passages.jsonl in the shared passage
schema.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "chunking.yaml").read_text(encoding="utf-8"))
MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
FULLTEXT = ROOT / "artifacts" / "fulltext"
MANIFEST = ROOT / "data" / "book_manifest.json"
OUT = ROOT / "artifacts" / "passages.jsonl"

CHUNK_WORDS = CFG["chunk_words"]
OVERLAP_WORDS = CFG["overlap_words"]
MIN_WORDS = CFG["min_words"]
GROUP_ID = "G014"  # replace with your assigned group id


def clean_text(text: str) -> str:
    """Conservative cleanup: soft hyphens, de-hyphenate across line breaks,
    normalise whitespace, keep equations/table glyphs (do NOT strip symbols)."""
    text = text.replace("\u00ad", "")  # remove soft hyphens
    text = re.sub(r"-\n(\w)", r"\1", text)  # re-join words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_page(text: str):
    """Split one page's text into overlapping word windows (no cross-page span)."""
    words = text.split()
    if len(words) < MIN_WORDS:
        return
    start = 0
    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        piece = " ".join(words[start:end]).strip()
        if piece:
            yield piece
        if end == len(words):
            break
        start = max(start + 1, end - OVERLAP_WORDS)


def build_passages(pages_by_book: dict[str, list[dict]]):
    """pages_by_book: book_id -> list of page records from ingest.py."""
    rows = []
    for book_id, pages in pages_by_book.items():
        for pg in pages:
            cleaned = clean_text(pg["text"])
            for ci, piece in enumerate(chunk_page(cleaned), start=1):
                rows.append({
                    "group_id": GROUP_ID,
                    "subject": "",  # filled from manifest below
                    "book_id": book_id,
                    "title": "",  # filled from manifest below
                    "edition": "",  # filled from manifest below
                    "publisher": "",
                    "year": None,
                    "page": pg["page"],
                    "chunk_id": f"{book_id}_P{pg['page']}_C{ci:03d}",
                    "text": piece,
                    "lang": "en",
                    "extraction_method": pg.get("extraction_method", "pymupdf-text"),
                    "needs_review": False,
                })
    return rows


def main() -> None:
    manifest = {b["book_id"]: b for b in
                json.loads(MANIFEST.read_text(encoding="utf-8"))}
    pages_by_book: dict[str, list[dict]] = {}
    for f in FULLTEXT.glob("*.jsonl"):
        book_id = f.stem
        pages = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        pages_by_book[book_id] = pages
    rows = build_passages(pages_by_book)
    for r in rows:
        b = manifest.get(r["book_id"], {})
        r["subject"] = b.get("subject", "")
        r["title"] = b.get("title", "")
        r["edition"] = b.get("edition", "")
        r["publisher"] = b.get("publisher", "")
        r["year"] = b.get("year")
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"chunks written: {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
