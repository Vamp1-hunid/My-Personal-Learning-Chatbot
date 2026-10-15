"""src/ingest.py — Extraction stage.

Reads approved PDFs declared in data/book_manifest.json, extracts text page by
page with PyMuPDF (import fitz), and writes one JSONL record per page:
{book_id, filename, page, text, extraction_method, char_count}.
Pages with few characters are flagged as scanned candidates.
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "book_manifest.json"
BOOKS_DIR = ROOT / "data" / "books"
OUT_DIR = ROOT / "artifacts" / "fulltext"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_TEXT_CHARS = 40  # char threshold for "this page looks scanned"


def extract_pages_with_meta(pdf_path: Path, book_id: str) -> list[dict]:
    out = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            out.append({
                "book_id": book_id,
                "filename": pdf_path.name,
                "page": i,
                "text": text.replace("\x00", " "),
                "char_count": len(text.strip()),
                "needs_ocr": len(text.strip()) < MIN_TEXT_CHARS,
                "extraction_method": "pymupdf-text",
            })
    return out


def looks_scanned(pages: list[dict]) -> bool:
    if not pages:
        return True
    empty = sum(1 for p in pages if p["char_count"] < MIN_TEXT_CHARS)
    return empty / len(pages) > 0.5


def main() -> None:
    books = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = []
    for book in books:
        pdf_path = BOOKS_DIR / book["filename"]
        if not pdf_path.is_file():
            problems.append(f"missing file: {book['filename']}")
            book["processing_status"] = "failed"
            continue
        try:
            pages = extract_pages_with_meta(pdf_path, book["book_id"])
            out_path = OUT_DIR / f"{book['book_id']}.jsonl"
            with out_path.open("w", encoding="utf-8") as f:
                for p in pages:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
            if looks_scanned(pages):
                book["processing_status"] = "needs_ocr"
            else:
                book["processing_status"] = "processed"
        except Exception as exc:
            problems.append(f"{book['filename']}: {exc}")
            book["processing_status"] = "failed"
    MANIFEST.write_text(json.dumps(books, indent=2, ensure_ascii=False), encoding="utf-8")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    print(f"Ingestion complete. Output dir: {OUT_DIR}")


if __name__ == "__main__":
    main()
