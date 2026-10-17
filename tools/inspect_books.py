"""tools/inspect_books.py — Corpus audit before writing the manifest.

For every file in data/books/ reports: whether it opens as a PDF at all, page
count, embedded metadata (title/author), how much text the first pages yield,
and what fraction of pages look scanned. Read-only; changes nothing.

Usage:
    python tools\\inspect_books.py
    python tools\\inspect_books.py --json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT / "data" / "books"
MIN_TEXT_CHARS = 40


def first_meaningful_lines(doc: fitz.Document, max_pages: int = 6) -> list[str]:
    """Grabs the opening text so a human can confirm title/author on the cover."""
    lines: list[str] = []
    for i in range(min(max_pages, doc.page_count)):
        for raw in doc[i].get_text("text").splitlines():
            line = " ".join(raw.split())
            if len(line) >= 3:
                lines.append(line)
        if len(lines) >= 12:
            break
    return lines[:12]


def inspect(path: Path) -> dict:
    rec = {"filename": path.name, "size_mb": round(path.stat().st_size / 2**20, 1)}
    try:
        with fitz.open(path) as doc:
            if doc.page_count == 0:
                rec["status"] = "empty_or_invalid"
                return rec
            empty = 0
            total_chars = 0
            for page in doc:
                n = len(page.get_text("text").strip())
                total_chars += n
                if n < MIN_TEXT_CHARS:
                    empty += 1
            rec.update({
                "status": "pdf",
                "pages": doc.page_count,
                "meta_title": (doc.metadata or {}).get("title") or "",
                "meta_author": (doc.metadata or {}).get("author") or "",
                "chars_per_page": round(total_chars / doc.page_count, 1),
                "scanned_page_ratio": round(empty / doc.page_count, 3),
                "opening_lines": first_meaningful_lines(doc),
            })
            rec["needs_ocr"] = rec["scanned_page_ratio"] > 0.5
    except Exception as exc:  # noqa: BLE001 — a bad file must not stop the audit
        rec["status"] = f"unreadable: {type(exc).__name__}: {exc}"
    return rec


def copyright_lines(path: Path, max_pages: int = 14) -> list[str]:
    """Pulls the lines that carry edition / year / publisher / ISBN."""
    keys = ("isbn", "copyright", "\u00a9", "edition", "publisher", "press",
            "springer", "o'reilly", "wiley", "elsevier", "apress", "packt",
            "cambridge", "mit press", "de gruyter")
    hits: list[str] = []
    with fitz.open(path) as doc:
        for i in range(min(max_pages, doc.page_count)):
            for raw in doc[i].get_text("text").splitlines():
                line = " ".join(raw.split())
                low = line.lower()
                if 4 <= len(line) <= 160 and any(k in low for k in keys):
                    hits.append(f"p{i + 1}: {line}")
    return hits[:20]


def spotcheck(max_chars: int = 420) -> list[str]:
    """Three sampled pages per book (front/middle/back) with their real text.

    Step 2 of the assignment requires opening each sampled PDF page and
    comparing it against the extracted text. Writes a report so the reader can
    open `book_id` page N and check it directly.
    """
    lines: list[str] = []
    manifest = json.loads((ROOT / "data" / "book_manifest.json").read_text(encoding="utf-8"))
    for book in manifest:
        path = BOOKS_DIR / book["filename"]
        lines.append("\n## " + book["book_id"] + " — " + book["title"])
        try:
            with fitz.open(path) as doc:
                n = doc.page_count
                # Front / middle / back, avoiding the very first and last pages
                # which are often blank or image-only covers.
                picks = sorted({max(0, int(n * f)) for f in (0.15, 0.5, 0.85)})
                for i in picks:
                    text = doc[i].get_text("text").strip()
                    lines.append(f"\n### PDF page {i + 1} of {n}  ({len(text)} chars)")
                    lines.append("```" + text[:max_chars].replace("```", "'''") + "```")
        except Exception as exc:  # noqa: BLE001 — keep auditing the other books
            lines.append(f"(unreadable: {type(exc).__name__})")
    return lines


def main() -> None:
    # Book covers contain typographic glyphs cp1252 cannot encode; never crash on them.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/embedded streams have no reconfigure
        pass
    files = sorted(p for p in BOOKS_DIR.iterdir() if p.is_file())
    if "--spotcheck" in sys.argv:
        out = ROOT / "artifacts" / "spotcheck.md"
        body = ["# Extraction spot-check", "",
                "Three sampled pages per book. Open the PDF at the stated PDF page "
                "(1-based, not the printed page number) and compare with the text here."]
        body += spotcheck()
        out.write_text("\n".join(body), encoding="utf-8")
        print(f"wrote {out}")
        return
    if "--copyright" in sys.argv:
        for path in files:
            print("=" * 78)
            print(path.name)
            try:
                for line in copyright_lines(path):
                    print(f"  {line}")
            except Exception as exc:  # noqa: BLE001 — report and keep going
                print(f"  unreadable: {type(exc).__name__}")
        return
    records = [inspect(p) for p in files]
    if "--json" in sys.argv:
        (ROOT / "artifacts" / "corpus_audit.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote artifacts/corpus_audit.json ({len(records)} files)")
        return
    for r in records:
        print("=" * 78)
        print(f"{r['filename']}  [{r['status']}]  {r['size_mb']} MB")
        if r["status"] == "pdf":
            print(f"  pages={r['pages']}  chars/page={r['chars_per_page']}  "
                  f"scanned={r['scanned_page_ratio']:.0%}  needs_ocr={r['needs_ocr']}")
            print(f"  meta title: {r.get('meta_title') or '(none)'}")
            print(f"  meta author: {r.get('meta_author') or '(none)'}")
            for line in r["opening_lines"][:6]:
                print(f"    | {line}")


if __name__ == "__main__":
    main()
