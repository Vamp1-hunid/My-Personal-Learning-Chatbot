"""Manifest + ingestion integrity tests (pure stdlib — no heavy deps)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "book_manifest.json"
VALID_STATUS = {"pending", "processed", "needs_ocr", "failed", "approved_exception"}
VALID_TYPES = {"PDF text", "scanned PDF", "approved format"}


def manifest_books():
    if not MANIFEST.is_file():
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_has_at_least_15_books():
    books = manifest_books()
    assert len(books) >= 15, f"got {len(books)} books; need at least 15"


def test_manifest_fields_present():
    required = {"book_id", "filename", "title", "author", "edition",
                "subject", "source_type", "permission_status",
                "processing_status"}
    for b in manifest_books():
        missing = required - set(b.keys())
        assert not missing, f"{b.get('book_id')} missing {missing}"


def test_book_ids_unique_and_well_formed():
    books = manifest_books()
    ids = [b["book_id"] for b in books]
    assert len(ids) == len(set(ids))
    for i in ids:
        assert i.startswith("G014_BOOK_"), i


def test_processing_status_is_valid():
    for b in manifest_books():
        assert b["processing_status"] in VALID_STATUS, b["book_id"]


def test_source_type_is_valid():
    for b in manifest_books():
        assert b["source_type"] in VALID_TYPES, b["book_id"]


def test_pdf_files_present():
    books = manifest_books()
    if not books:  # template-only checkout still passes basic validation
        return
    missing = [b["filename"] for b in books
               if not (ROOT / "data" / "books" / b["filename"]).is_file()]
    assert not missing, f"missing PDFs: {missing}"
