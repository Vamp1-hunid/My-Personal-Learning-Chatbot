"""
QuantaKai - documents attached to one conversation (its "context").

You attach files to a chat; their text is read once and saved next to that chat.
For every question in that chat, the most relevant parts are given to the model
along with your question, so it can answer from them. Other chats don't see them.

Reads: PDF, EPUB, Word (.docx, and old .doc as best it can), PowerPoint (.pptx, old .ppt),
Excel (.xlsx, old .xls), OpenDocument (.odt .ods .odp), RTF, HTML/XML, CSV/TSV, JSON,
Jupyter notebooks, Markdown/plain text, subtitles, logs, and source code of any language.
Anything else that is mostly text is read as text too.
"""
from __future__ import annotations

import base64
import html
import json
import math
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from .settings import DATA_DIR

CHARS_PER_TOKEN = 3.5

DOCS_DIR = DATA_DIR / "chat_docs"
MAX_FILE_BYTES = 18 * 1024 * 1024          # about 18 MB per file
MAX_TEXT_CHARS = 3_000_000                 # very long files are cut after this
MAX_DOCS_PER_CHAT = 12

ZIP_XML = {".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp"}


class DocError(Exception):
    pass


# --------------------------------------------------------------------------- reading files
def _decode(data: bytes) -> str:
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


def _looks_like_text(data: bytes) -> bool:
    head = data[:8192]
    if not head:
        return False
    if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return True
    if b"\x00" in head:
        return False
    printable = sum(32 <= b < 127 or b in (9, 10, 13) or b >= 128 for b in head)
    return printable / len(head) > 0.92


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|section|article)>", "\n", text)
    text = re.sub(r"(?i)</t[dh]>", "\t", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


_RTF_SKIP = ("fonttbl", "colortbl", "stylesheet", "info", "listtable", "listoverridetable", "pict",
             "themedata", "colorschememapping", "latentstyles", "datastore", "xmlnstbl", "rsidtbl", "generator")


def _strip_rtf(text: str) -> str:
    # first drop whole groups that hold fonts, colours, styles, pictures and other settings
    out, i, n = [], 0, len(text)
    skip = re.compile(r"\{\\(\*|(%s)\b)" % "|".join(_RTF_SKIP))
    while i < n:
        ch = text[i]
        if ch == "\\":
            out.append(text[i:i + 2]); i += 2; continue
        if ch == "{" and skip.match(text, i):
            depth = 0
            while i < n:
                c = text[i]
                if c == "\\":
                    i += 2; continue
                depth += (c == "{") - (c == "}")
                i += 1
                if depth == 0:
                    break
            continue
        out.append(ch); i += 1
    text = "".join(out)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "replace"), text)
    text = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), text)
    text = re.sub(r"\\(par|line|row)\b ?", "\n", text)
    text = re.sub(r"\\tab\b ?|\\cell\b ?", "\t", text)
    text = re.sub(r"\\([{}\\])", r"\1", re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text))
    return re.sub(r"(?<!\\)[{}]", "", text)


def _xml_text(xml: bytes, para_tags=("p", "h", "list-item"), cell_tags=("table-cell",)) -> str:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    out: list[str] = []

    def walk(el, in_cell=False):
        tag = el.tag.split("}")[-1]
        cell = in_cell or tag in cell_tags
        if el.text:
            out.append(el.text)
        for child in el:
            walk(child, cell)
            if child.tail:
                out.append(child.tail)
        if tag == "tab":
            out.append("\t")
        elif tag == "s":
            out.append(" ")
        elif tag in para_tags or tag in ("line-break", "br"):
            out.append(" " if in_cell else "\n")
        if tag in cell_tags:
            out.append("\t")
        elif tag == "table-row":
            out.append("\n")

    walk(root)
    return "".join(out)


def _xlsx_text(z: zipfile.ZipFile) -> str:
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
    names = {}
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for i, sh in enumerate(wb.iter(f"{{{ns['m']}}}sheet"), start=1):
            names[i] = sh.get("name")
    except (KeyError, ET.ParseError):
        pass
    sheets = sorted((n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
    parts = []
    for n in sheets:
        idx = int(re.search(r"(\d+)\.xml$", n).group(1))
        rows = []
        for row in ET.fromstring(z.read(n)).iter(f"{{{ns['m']}}}row"):
            cells = []
            for c in row.findall("m:c", ns):
                t, v = c.get("t"), c.find("m:v", ns)
                if t == "s" and v is not None and v.text and v.text.isdigit() and int(v.text) < len(shared):
                    cells.append(shared[int(v.text)])
                elif t == "inlineStr":
                    cells.append("".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t")))
                elif v is not None and v.text is not None:
                    cells.append(v.text)
                else:
                    cells.append("")
            if any(x.strip() for x in cells):
                rows.append("\t".join(cells).rstrip())
        if rows:
            parts.append(f"## Sheet: {names.get(idx, idx)}\n" + "\n".join(rows))
    return "\n\n".join(parts)


_OFFICE_JUNK = re.compile(
    r"^(Microsoft.*|Times New Roman|Arial.*|Calibri.*|Cambria.*|Symbol|Wingdings.*|Courier New|Liberation .*|DejaVu .*|"
    r"OpenSymbol|Lucida .*|Normal.*|Default Paragraph Font|Table Normal|No List|Root Entry|WordDocument|"
    r"(Document)?SummaryInformation|CompObj|Workbook|Book|[01]Table|Data|ObjectPool|Header.*|Footer.*|Heading( \d)?( Char)?|"
    r".* Char|ListLabel \d+|Title|Subtitle|Body Text.*|Caption|Index|List.*|Strong|Emphasis|Intense .*|Subtle .*|"
    r"Book Title|Quote|Macro Text|General|openpyxl|AppVersion|Calc|Sheet\d*|PowerPoint Document|Current User|Pictures|Biff8|Ole|3\.1)$", re.I)


def _legacy_office_text(data: bytes, ext: str = "") -> str:
    """Old .doc / .xls / .ppt files: pull out the readable text (best effort)."""
    u16 = [(m.start(), m.group().decode("utf-16-le", "ignore"))
           for m in re.finditer(rb"(?:[\x20-\x7e\xa0-\xff\r\t\x07\x0b]\x00){3,}", data)]
    if ext in (".doc", ".dot", ".wps"):
        # Word keeps the whole body as one long run of text; settings and style names are short runs
        longest = max((len(t) for _, t in u16), default=0)
        runs = [r for r in u16 if len(r[1]) >= max(30, longest * 0.25)] or u16
    else:
        a8 = [(m.start(), m.group().decode("cp1252", "ignore"))
              for m in re.finditer(rb"[\x20-\x7e\t]{3,}", data)]
        runs = sorted(u16 + a8)
    lines, seen = [], set()
    for _, t in runs:
        for line in t.replace("\x07", "\t").replace("\x0b", "\n").replace("\r", "\n").split("\n"):
            line = line.strip()
            if len(line) < 2 or _OFFICE_JUNK.match(line) or not re.search(r"[A-Za-z0-9]", line):
                continue
            if sum(ch.isalnum() or ch in " .,;:'\"-()!?%/&\t=+" for ch in line) / len(line) < 0.8:
                continue
            if max(line.count(c) for c in set(line)) > len(line) * 0.6 and len(line) > 6:   # 'ÿÿÿÿ' style filler
                continue
            if ext not in (".doc", ".dot", ".wps"):
                if line in seen:
                    continue
                seen.add(line)
            lines.append(line)
    return "\n".join(lines)


def _via_library(name: str, data: bytes) -> str:
    """PDF, EPUB, DOCX, PPTX: use the same readers as the book library."""
    from . import library
    folder = Path(tempfile.mkdtemp(dir=str(DATA_DIR)))
    try:
        p = folder / ("doc" + Path(name).suffix.lower())
        p.write_bytes(data)
        pages, _ = library.extract_pages(p)
        suffix = p.suffix
        label = "Slide" if suffix == ".pptx" else "Page"
        if suffix in (".pdf", ".pptx"):
            return "\n\n".join(f"[{label} {n}]\n{t}" for n, t in pages if t.strip())
        return "\n\n".join(t for _, t in pages if t.strip())
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def extract_text(name: str, data: bytes) -> str:
    ext = Path(name).suffix.lower()
    if ext in (".pdf", ".epub", ".docx", ".pptx", ".xps", ".fb2", ".mobi", ".cbz"):
        try:
            if ext in (".pdf", ".epub", ".docx", ".pptx"):
                return _via_library(name, data)
            import pymupdf
            with pymupdf.open(stream=data, filetype=ext[1:]) as doc:
                return "\n\n".join(p.get_text("text") for p in doc)
        except Exception as e:
            raise DocError(f"Could not read {name}: {e}")
    if ext in ZIP_XML or (data[:2] == b"PK" and ext in (".odg", ".ott", ".dotx", ".potx", ".xltx")):
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(data)) as z:
                if ext == ".xlsx" or ext == ".xltx":
                    return _xlsx_text(z)
                return _xml_text(z.read("content.xml"))
        except (zipfile.BadZipFile, KeyError) as e:
            raise DocError(f"{name} looks damaged ({e}).")
    if ext in (".doc", ".xls", ".ppt", ".dot", ".pps", ".wps"):
        text = _legacy_office_text(data, ext)
        if len(text) < 20:
            raise DocError(f"Could not read the old-style file {name}. Save it as .docx/.xlsx/.pptx and attach it again.")
        return "(Read from an old-style Office file; some formatting or tables may be jumbled.)\n" + text
    if ext == ".ipynb":
        try:
            nb = json.loads(_decode(data))
            cells = []
            for c in nb.get("cells", []):
                src = "".join(c.get("source", []))
                cells.append(f"```python\n{src}\n```" if c.get("cell_type") == "code" else src)
            return "\n\n".join(cells)
        except ValueError:
            pass
    if not _looks_like_text(data):
        raise DocError(f"{name} doesn't look like a text document, so it can't be read. "
                       "Pictures go in as pictures; other files can be saved as PDF, Word or text first.")
    text = _decode(data)
    if ext in (".html", ".htm", ".xhtml", ".mhtml") or (ext in ("", ".xml") and "<html" in text[:2000].lower()):
        return _strip_html(text)
    if ext == ".rtf" or text.startswith("{\\rtf"):
        return _strip_rtf(text)
    if ext == ".svg":
        return _strip_html(text)
    return text


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\u00a0]+\n", "\n", text)
    text = re.sub(r" +\t", "\t", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


# --------------------------------------------------------------------------- storage per chat
def _folder(conv_id: str) -> Path:
    return DOCS_DIR / re.sub(r"[^a-zA-Z0-9_-]", "", conv_id)


def decode_upload(data: str) -> bytes:
    if data.startswith("data:"):
        data = data.split(",", 1)[1] if "," in data else ""
    try:
        raw = base64.b64decode(data, validate=False)
    except (ValueError, TypeError):
        raise DocError("The file did not arrive correctly. Try attaching it again.")
    if not raw:
        raise DocError("That file is empty.")
    if len(raw) > MAX_FILE_BYTES:
        raise DocError(f"That file is {len(raw) / 1048576:.0f} MB. Files up to {MAX_FILE_BYTES // 1048576} MB can be attached.")
    return raw


def add(conv: dict, name: str, raw: bytes) -> dict:
    docs = conv.setdefault("docs", [])
    if len(docs) >= MAX_DOCS_PER_CHAT:
        raise DocError(f"A chat can hold up to {MAX_DOCS_PER_CHAT} documents. Remove one first.")
    name = Path(name or "document.txt").name[:120]
    text = _clean(extract_text(name, raw))
    if len(text) < 2:
        raise DocError(f"No readable text was found in {name}. If it is a scanned PDF, attach the pages as pictures instead.")
    doc = {"id": uuid.uuid4().hex[:10], "name": name, "chars": len(text),
           "words": len(text.split()), "added": time.strftime("%Y-%m-%d %H:%M")}
    folder = _folder(conv["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{doc['id']}.txt").write_text(text, encoding="utf-8")
    docs.append(doc)
    return doc


def remove(conv: dict, doc_id: str) -> bool:
    docs = conv.get("docs", [])
    keep = [d for d in docs if d["id"] != doc_id]
    if len(keep) == len(docs):
        return False
    conv["docs"] = keep
    try:
        (_folder(conv["id"]) / f"{re.sub(r'[^a-z0-9]', '', doc_id)}.txt").unlink()
    except OSError:
        pass
    return True


def delete_all(conv_id: str) -> None:
    shutil.rmtree(_folder(conv_id), ignore_errors=True)


def _read(conv_id: str, doc: dict) -> str:
    try:
        return (_folder(conv_id) / f"{doc['id']}.txt").read_text(encoding="utf-8")
    except OSError:
        return ""


# --------------------------------------------------------------------------- choosing what to show the model
def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", text.lower()) if len(w) > 1]


def _chunks(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):                                     # finish at a line or sentence end if close by
            cut = max(text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
            if cut > 0:
                end = cut + 1
        out.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]


STORY_HEADER = ("Reference material the user attached for this story. Treat it as canon: use its characters, names, "
                "places, events, rules of the world, tone and writing style. If asked to continue it, pick up exactly where "
                "it ends. If asked to adapt, retell, or write a sequel, prequel or spin-off, stay faithful to it. Write new "
                "prose in your own words and never copy long passages from it. Anything the reference does not cover, "
                "invent so that it fits.\n")


def context_block(conv: dict, question: str, token_budget: int, story: bool = False) -> tuple[str, list[str]]:
    """The attached documents (or their most relevant parts) as text for the model.
    story=True (Create mode): the documents are a story's source material, and when they are too long
    the opening and the ending (where a story to be continued stops) are favoured.
    Returns (text, names of the documents used)."""
    docs = conv.get("docs") or []
    if not docs or token_budget < 80:
        return "", []
    char_budget = int(token_budget * CHARS_PER_TOKEN)
    texts = [(d, _read(conv["id"], d)) for d in docs]
    texts = [(d, t) for d, t in texts if t]
    if not texts:
        return "", []
    header = STORY_HEADER if story else (
        "Documents attached to this conversation by the user. Use them as background context and as the "
        "main source when the question is about them; say which document you used. "
        "If the answer is not in them, say so and answer from general knowledge.\n")
    if sum(len(t) for _, t in texts) + 40 * len(texts) <= char_budget:      # small enough: send everything
        body = "\n\n".join(f"=== {d['name']} ===\n{t}" for d, t in texts)
        return header + body, [d["name"] for d, _ in texts]

    # too big: pick the most relevant parts (keyword scoring, like the book search)
    pieces = []   # (doc index, chunk index, text)
    last_chunk = {}
    for di, (d, t) in enumerate(texts):
        for ci, c in enumerate(_chunks(t)):
            pieces.append((di, ci, c))
            last_chunk[di] = ci
    q = set(_terms(question))
    df: dict[str, int] = {}
    toks = []
    for _, _, c in pieces:
        ts = _terms(c)
        toks.append(ts)
        for w in set(ts) & q:
            df[w] = df.get(w, 0) + 1
    n = len(pieces)
    avg = sum(len(t) for t in toks) / max(1, n)
    scores = []
    for i, ts in enumerate(toks):
        s, counts = 0.0, {}
        for w in ts:
            if w in q:
                counts[w] = counts.get(w, 0) + 1
        for w, f in counts.items():
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(ts) / max(1, avg)))
        name_bonus = 0.6 if q & set(_terms(texts[pieces[i][0]][0]["name"])) else 0.0
        start = 0.35 if pieces[i][1] == 0 else 0.0               # the start of a document often says what it is
        if story:                                                 # a story's opening and its last pages matter most
            start = 1.5 if pieces[i][1] == 0 else (2.0 if pieces[i][1] == last_chunk[pieces[i][0]] else 0.0)
        scores.append(s + name_bonus + start)
    order = sorted(range(n), key=lambda i: -scores[i])
    chosen, used = [], 40 * len(texts)
    for i in order:
        cost = len(pieces[i][2]) + 8
        if used + cost > char_budget:
            continue
        chosen.append(i)
        used += cost
    chosen.sort(key=lambda i: (pieces[i][0], pieces[i][1]))
    blocks, last_doc, names = [], None, []
    for i in chosen:
        di, ci, c = pieces[i]
        if di != last_doc:
            blocks.append(f"=== {texts[di][0]['name']} (relevant parts) ===")
            names.append(texts[di][0]["name"])
            last_doc = di
        blocks.append(c + "\n[...]")
    return header + "\n".join(blocks), names
