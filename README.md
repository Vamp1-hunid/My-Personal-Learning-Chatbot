# QuantaKai

A private, offline AI assistant for a Windows laptop. It chats and remembers you, answers from your own books with page numbers, searches the web when asked, writes stories and characters, runs the code it writes, reads pictures and documents, and talks and listens. Everything runs from one portable folder with its own Python, engine and models.

**Full rebuild guide:** open [`BUILD_GUIDE.html`](BUILD_GUIDE.html) in a browser (download the file, then double-click it). It lists every program, link, folder, command and the complete code of every file, in build order, with a file checker and an automatic test.
**Project report:** [`docs/REPORT.html`](docs/REPORT.html) covers design, technology choices, security, testing, results and future work.

## Features

| Area | What you get |
|---|---|
| Modes | **Chat** (personal, with long-term memory), **Offline** (answers only from your books, cited with pages), **Online** (DuckDuckGo search, cited links), **Create** (stories and character sheets) |
| Answer styles | Detailed (default), Quick, Code (with a Run button for Python and Java), Teach (full lessons), Quiz (interactive quiz, flashcards, printable study guide) |
| Library | PDF, EPUB, Word, PowerPoint, .txt and .md; hybrid search (meaning vectors + BM25 keywords, fused with reciprocal rank fusion); 80 subjects in 11 groups; spelling correction; only new or changed books are processed |
| Memory | "remember that …", automatic learning after chat replies, and an editable Memory page |
| Extras | Pictures (Windows OCR, vision models), documents attached to a chat, highlight any text to read it aloud or explain it |
| Voice | Offline voice typing (whisper.cpp); reading aloud with Piper or Kokoro, sentence by sentence while the answer streams; Stop or Esc |
| Look | Light (default) and dark themes, custom wallpaper, a nickname, and an animated mascot that dresses for each mode and style |
| Models | Any GGUF chat model up to 5 GB, switched by hand; default Qwen2.5-3B-Instruct Q4_K_M; search model bge-small-en-v1.5 |

## Quick start (Windows 10/11)

1. Copy this repository into a folder, for example `C:\Users\<you>\Desktop\QuantaKai`.
2. Put the numpy (cp314) and PyMuPDF `.whl` files in `runtime\wheels` (links in the guide).
3. Double-click **SETUP.bat**: it fetches portable Python 3.14, the llama.cpp CPU engine and both models (about 2.1 GB), then runs a speed test.
4. Optional: double-click **VOICE_SETUP.bat** for voice typing and the reading voice (about 230 MB).
5. Double-click **START.bat**. The app opens at <http://127.0.0.1:8000>. Put books in `books`, then press **Add all new** on the Library page.

To stop: close the black window or double-click **STOP.bat**.

## Check a build

```powershell
runtime\python\python.exe tools\verify_files.py   # every source file matches the guide (SHA-256)
runtime\python\python.exe tests\smoke_test.py     # the whole app, with a fake engine: ALL TESTS PASSED
```

## Repository layout

```
app/        Python program: server, chat, library, memory, engines, web, voice, documents, OCR, code runner
ui/         index.html - the complete interface (HTML, CSS, JavaScript; no libraries)
scripts/    setup.ps1 and setup_voice.ps1 (used by SETUP.bat and VOICE_SETUP.bat)
tests/      smoke_test.py and the fake llama-server it uses
tools/      build_docs.py (regenerates the guide, report and manifest from the code), verify_files.py
docs/       REPORT.html and manifest.json (every file's size, lines and SHA-256)
*.bat       START, STOP, SETUP, VOICE_SETUP
config.json all settings; requirements.txt; README.txt (the in-folder reminder)
```

Not in the repository (downloaded or private): `runtime/`, `engine/`, `models/`, `voice/`, `books/`, `data/`, `logs/`.

## Rebuilding the documents

After changing any file, run `python tools/build_docs.py`. It regenerates `BUILD_GUIDE.html`, `docs/REPORT.html`, `docs/manifest.json` and `tools/verify_files.py` from the real source, so the guide always shows the current code.

## History

This repository previously held the Group G014 book-grounded RAG chatbot (FAISS, Qwen2.5-0.5B). That code is preserved on the `g014-final` branch.
