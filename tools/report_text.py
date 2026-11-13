"""report_text.py - the written content of docs/REPORT.html (the QuantaKai project report)."""
from __future__ import annotations

from docshell import Doc, E


def write(d: Doc, files: list[dict]) -> None:
    py = [f for f in files if f["path"].endswith(".py")]
    total = sum(f["lines"] for f in files)
    d.raw("<h1>QuantaKai: a private, offline, book-grounded assistant for a student laptop</h1>")
    d.raw("<p class='lead'>Project report by Mulenga Mwamba, Bachelor of Science in Data Science, Mulungushi University. "
          "November 2026.</p>")

    # ------------------------------------------------------------------ 1
    d.section("Summary", "summary")
    d.p("QuantaKai is a personal AI assistant that runs completely on an ordinary Windows laptop (AMD Ryzen 5 PRO 3500U, "
        "16 GB RAM, no dedicated graphics card). It combines a local language model (Qwen2.5-3B-Instruct, 4-bit) served by "
        "llama.cpp with a hybrid search engine over the owner's own books, a long-term memory, web search on demand, "
        "creative writing, code execution, picture and document reading, and offline speech in both directions. "
        "Everything lives in one portable folder with its own Python runtime, so it can be copied to another drive or PC "
        "and still run.")
    d.table(["Fact", "Value"], [
        ["Source files", f"{len(files)} files, {total:,} lines ({len(py)} Python modules, 1 HTML interface, scripts and tests)"],
        ["Dependencies beyond Python", "numpy, pymupdf"],
        ["Chat model", "Qwen2.5-3B-Instruct Q4_K_M (1.93 GB), any GGUF up to 5 GB swappable"],
        ["Search model", "bge-small-en-v1.5 Q8_0 (37 MB, 384-dimensional vectors)"],
        ["Generation speed", "about 11.8 tokens/s (CPU only)"],
        ["Library", "80 subjects in 11 groups; books, notes, Word and PowerPoint files"],
        ["Tests", "Automatic smoke test with a fake engine; feature checks; browser tests with no page errors"],
    ])

    # ------------------------------------------------------------------ 2
    d.section("Background and goals", "goals")
    d.p("An earlier group project (Group G014, a book-grounded RAG chatbot using FAISS, Qwen2.5-0.5B and a Python 3.11 "
        "virtual environment) stopped working on the author's new laptop: its virtual environment pointed at a Python "
        "installation that no longer existed, and FAISS had no wheels for newer Python versions. QuantaKai was built from "
        "scratch as a personal project with these goals, set by the owner:")
    d.ul([
        "A more premium-looking, faster and sharper offline chatbot that runs smoothly on this laptop.",
        "Answers questions from many books (20 to start, more later) in a way the owner can understand.",
        "More than a notes bot: personal conversations, learning new facts as conversations go on, and a study mode on request.",
        "Manual switching between models inside the app, each model at most 5 GB; the option to load an abliterated model.",
        "A portable folder on the Desktop that keeps working if moved.",
        "A complete HTML build guide listing every program, link, folder and file.",
        "Later additions: a nickname, faster stoppable voice, a light default theme, custom wallpaper, story and character writing, an animated mascot that dresses for each mode, highlight-to-read/explain, and a much richer subject list.",
    ])

    # ------------------------------------------------------------------ 3
    d.section("Requirements and status", "requirements")
    d.table(["Requirement", "How it is met", "Status"], [
        ["Runs offline on the laptop", "llama.cpp CPU engine; all data in the folder; only Online mode uses the internet", "Done"],
        ["Portable folder", "Embeddable Python with a relative ._pth; all paths from the code's own location", "Done"],
        ["Chat with memory that learns", "memory.json with vectors; \"remember that\"; automatic extraction after each reply; editable page", "Done"],
        ["Study from books", "Offline mode: hybrid search, citations with page numbers, refusal when not found, five answer styles", "Done"],
        ["Many books, added incrementally", "Per-book index files; only new or changed files processed; queue with progress and time estimates", "Done"],
        ["Manual model switching, 5 GB limit", "Models page and picker; GGUF header and size checked before loading", "Done"],
        ["Abliterated model option", "Any GGUF loads the same way; documented in the guide", "Done"],
        ["Premium look", "Single-file interface, light/dark themes, wallpaper, animated Blob mascot", "Done"],
        ["Voice", "whisper.cpp typing; Piper or Kokoro reading aloud, sentence by sentence while streaming; stoppable", "Done"],
        ["Story and character writing", "Create mode with dedicated instructions", "Done"],
        ["Build guide", "BUILD_GUIDE.html generated from the real files, with a file checker", "Done"],
        ["Faster first word in Offline mode", "Prompt reading is about 22 tokens/s, so long prompts wait about 40 s", "Open (see Future work)"],
    ])

    # ------------------------------------------------------------------ 4
    d.section("Architecture", "architecture")
    d.p("Four processes cooperate on the same machine. The browser shows a single HTML page served by a small Python web "
        "server. The server owns all logic (prompt building, search, memory, persistence) and talks over HTTP to two "
        "llama-server processes: one for the chat model and one for the embedding model. Optional helper processes "
        "provide speech recognition (whisper.cpp), speech synthesis (Piper, Kokoro) and picture text recognition "
        "(Windows OCR through PowerShell).")
    d.table(["Layer", "Modules", "Responsibility"], [
        ["Interface", "ui/index.html", "Pages, streaming display, Markdown, quiz, voice capture and playback, mascot"],
        ["HTTP", "server.py", "Routing, Host/Origin checks, Server-Sent Events, uploads"],
        ["Orchestration", "chat.py, prompts.py", "Modes and styles, context assembly, token budgeting, persistence, auto-learn"],
        ["Knowledge", "library.py, memory.py, docs.py, web.py", "Books, long-term memory, per-chat documents, web extracts"],
        ["Engines", "engine.py, llm.py", "Process lifecycle, OpenAI-compatible HTTP client, embeddings"],
        ["Tools", "runner.py, ocr.py, voice.py, kokoro_worker.py, organize.py", "Code execution, OCR, speech, file tidying"],
        ["Foundation", "settings.py, config.json", "Paths, settings, atomic writes, state"],
    ])

    # ------------------------------------------------------------------ 5
    d.section("Technology choices", "choices")
    d.table(["Decision", "Chosen", "Why", "Alternatives considered"], [
        ["Inference engine", "llama.cpp llama-server (CPU build)", "Fast on CPUs, GGUF quantized models, OpenAI-compatible API, prebuilt Windows binaries", "Ollama (extra service), Python bindings (compilation on Windows)"],
        ["Chat model", "Qwen2.5-3B-Instruct Q4_K_M", "Best quality that keeps about 12 tok/s on 4 cores; follows citation rules well", "0.5B (too weak, used in G014), 7B (half the speed)"],
        ["Embeddings", "bge-small-en-v1.5 Q8_0 in a second llama-server", "37 MB, strong retrieval quality, no PyTorch", "sentence-transformers (needs PyTorch, hundreds of MB)"],
        ["Vector search", "numpy matrix product + BM25 + RRF", "A few thousand passages per book: exact search takes milliseconds; no compiled dependency", "FAISS (no wheels for new Python versions: the G014 failure)"],
        ["Python", "Embeddable 3.14 in the folder", "No installer, survives moving and Python upgrades on the PC", "System Python + venv (broke when Python was removed)"],
        ["Web server", "http.server ThreadingHTTPServer", "Zero dependencies, enough for one local user", "Flask, FastAPI"],
        ["Interface", "One HTML file, vanilla JavaScript", "No build step, no internet fonts or libraries, easy to copy", "React, Electron"],
        ["Web search", "DuckDuckGo HTML endpoint", "No API key, plain HTML", "Paid search APIs"],
        ["Picture text", "Windows.Media.Ocr", "Built into Windows, offline, no download", "Tesseract (large install)"],
        ["Speech", "whisper.cpp; Piper; Kokoro via sherpa-onnx", "Offline, CPU-friendly; Piper for speed, Kokoro for naturalness", "Cloud speech APIs"],
    ])

    # ------------------------------------------------------------------ 6
    d.section("Implementation", "implementation")
    d.sub("Engine management")
    d.p("engine.py starts each llama-server with an explicit command line, waits for /health, and records the process "
        "number. A Windows Job Object with kill-on-close guarantees that closing the console window also ends the engines, "
        "preventing gigabytes of orphaned memory. Leftover processes from a crash are stopped at the next start, but only "
        "after checking the process name, because Windows reuses process numbers. Models are validated by their GGUF magic "
        "bytes and size before loading; vision projector files are matched to their model by name.")
    d.sub("Retrieval")
    d.p("Books are split into 180-word passages with 40 words of overlap, keeping page ranges. Retrieval combines dense "
        "similarity (bge vectors, with the query instruction prefix) and BM25 keyword scores using reciprocal rank fusion, "
        "which fixes the two typical failures of each method alone: vectors miss exact names and formulas, keywords miss "
        "paraphrases. Results are restricted to the most relevant subject(s), near-duplicate overlapping passages are "
        "removed, and a spelling corrector built from the books' own vocabulary repairs typos in queries. Passages below a "
        "minimum meaning score are dropped unless they have a strong keyword match, and the prompt instructs the model to "
        "refuse when the passages do not contain the answer.")
    d.sub("Subjects")
    d.p("80 subjects in 11 groups (Cybersecurity, Data & AI, Programming & Software, Computers & Electronics, Maths & "
        "Science, Faith, Fiction & Literature, Non-fiction, Life & Skills, Study, Other). A book's subject comes from, in "
        "order: the owner's choice; title keywords for technical subjects (ordered from specific to broad, so \"Python for "
        "Cybersecurity\" is Cybersecurity); otherwise the nearest subject description to the book's average vector. All "
        "file names in the owner's books folder were used to test the title rules.")
    d.sub("Memory")
    d.p("A language model cannot update its weights during use, so memory is retrieval: short facts with vectors in "
        "memory.json, the most relevant of which are inserted into the system prompt. Facts are added explicitly "
        "(\"remember that…\") or by a background extraction prompt after each chat reply, with near-duplicates rejected at "
        "cosine similarity 0.92.")
    d.sub("Prompting and context budgeting")
    d.p("Each mode and style has its own system prompt. The context window (4096 tokens) is budgeted with a 3.5 "
        "characters-per-token estimate: system prompt, retrieved context, question and the answer's token cap are reserved "
        "first, and older history is dropped from the start until everything fits. Voice-mode answers are capped at 220 "
        "tokens and instructed to sound spoken; long-form styles (Code, Teach, Quiz, Create) are never shortened.")
    d.sub("Streaming, stopping and editing")
    d.p("Answers stream as Server-Sent Events. Closing the connection stops the engine from generating, and the partial "
        "answer is still saved. Every question and answer share a turn tag, so Retry and Edit rewind the conversation "
        "precisely. A global lock serialises generation, which suits a single local engine.")
    d.sub("Voice")
    d.p("The page records 16 kHz mono WAV and whisper.cpp transcribes it. For reading aloud, the page sends each finished "
        "sentence while the answer is still streaming, and plays the returned WAV clips gaplessly with the Web Audio API, "
        "so speech starts after the first sentence instead of after the whole answer. Piper stays loaded as a long-lived "
        "process; Kokoro is kept loaded by a separate worker process that calls the sherpa-onnx C library through ctypes, "
        "which removed a reload of the 114 MB model for every sentence. Kokoro is disabled automatically in Auto mode if it "
        "runs slower than 2.5 times real time.")
    d.sub("Interface")
    d.p("The interface is one HTML file with five pages. All model output is HTML-escaped before a small Markdown renderer "
        "runs, so model text cannot execute in the browser. Quiz answers follow a strict text format that the page parses "
        "into an interactive quiz with flashcards and a printable study guide. Any text on the page can be highlighted to "
        "be read aloud or explained in detail. The Blob mascot is drawn on canvas; its colour follows the mode and its "
        "accessories (monocle and mustache, lightning bolt, hacker faceplate, glasses and tie, cube, masquerade mask) "
        "follow the style, all eased smoothly between states.")

    # ------------------------------------------------------------------ 7
    d.section("Security review", "security")
    d.p("Because the app can execute code (/api/run), a local web server is an attack surface: any website open in the "
        "same browser could try to send requests to 127.0.0.1. Two defences are in place: a Host-header allow-list "
        "(against DNS rebinding) and an Origin-header check on all state-changing requests (against cross-site request "
        "forgery). The Origin check was added after a review found that the Host check alone did not stop a cross-site "
        "POST; tests confirm a foreign origin now receives 403 while the app's own page still runs code. Other measures: "
        "binding to 127.0.0.1, HTML escaping of model output, sanitised ids in file paths, upload limits, magic-byte checks "
        "for wallpapers, isolated and time-limited code runs, and name-checked process termination.")

    # ------------------------------------------------------------------ 8
    d.section("Testing", "testing")
    d.table(["Test", "What it covers", "Result"], [
        ["tests/smoke_test.py", "Whole app in a temporary copy with a fake engine: start-up, 5 GB limit, broken downloads, model switching, adding a book, Offline answer with sources and citations, Simpler please, remember-that, chat streaming, auto-learn, memory edit/delete, saved chats, cross-site blocking", "All pass"],
        ["Feature checks (fake engine with request dump)", "Nickname in prompts, voice-mode instruction and 220-token cap, normal mode unchanged, story and character prompts, wallpaper upload and type checks, settings ranges, CSRF on /api/run and DELETE", "All pass"],
        ["Browser tests (Playwright, Chrome)", "Chat and Library pages in light and dark themes; mode and style switching; mascot accessories; highlight menu (Read aloud and Explain) - checked for JavaScript errors and captured as screenshots", "No page errors"],
        ["File checker", "tools/verify_files.py compares each file's SHA-256 with the guide", "Used after any rebuild"],
        ["Title-rule test", "Subject chosen for every file name in the owner's books folder", "All sensible; two vague titles fall back to content"],
    ])

    # ------------------------------------------------------------------ 9
    d.section("Results", "results")
    d.table(["Measure", "Value (Ryzen 5 PRO 3500U, CPU only)"], [
        ["Writing speed, Qwen2.5-3B Q4_K_M", "about 11.8 tokens/s"],
        ["Prompt reading speed", "about 22 tokens/s"],
        ["Time to first word, Chat", "a few seconds (prompt cache)"],
        ["Time to first word, Offline with 4 passages", "about 40 s"],
        ["Adding a book", "about 4 to 12 minutes for 300 to 900 pages"],
        ["Search time", "milliseconds for a library of tens of books"],
    ])
    d.p("Answer quality is highest in Offline mode with the Detailed style, where the model is constrained to cited "
        "passages. The small model occasionally over-summarises long passages and can follow the Quiz format imperfectly; "
        "the page tolerates small deviations when parsing.")

    # ------------------------------------------------------------------ 10
    d.section("Development timeline", "timeline")
    d.table(["Date", "Work"], [
        ["12 Nov 2026", "Analysis of the old group chatbot and its broken Python 3.11 environment. New design for a personal, portable QuantaKai. First build guide. Folder, portable Python, engine and models set up (large downloads through Free Download Manager). Books copied from the old project. Chat, memory, Offline mode, Library, Models pages; smoke test passing."],
        ["12 Nov 2026", "Feature growth: Online mode, Teach/Quiz/Code styles, pictures, attached documents, code runner, voice typing, Piper and Kokoro voices, BM25 hybrid search, subjects, spelling correction; review of all changes."],
        ["13 Nov 2026", "Security fix (Origin check). Nickname, faster stoppable live voice, light theme default, custom wallpaper with fade and blur, Create mode (stories and characters)."],
        ["13 Nov 2026", "Blob mascot: gold colour and masquerade mask in Create, white hacker faceplate for Code, fix for Offline styles leaking into Create, lightning bolt for Quick, monocle and mustache for Detailed."],
        ["13 Nov 2026", "Highlight any text to read aloud or explain. Subjects expanded from 45 to 80 in 11 groups with grouped menus. Repository replaced with QuantaKai; documentation regenerated from source."],
    ])

    # ------------------------------------------------------------------ 11
    d.section("Limitations and future work", "future")
    d.ul([
        "<b>Prompt reading speed.</b> Reduce Offline prompts (3 passages, shorter chunks), try the Vulkan build on the Vega 8, or keep a warm prompt cache per book.",
        "<b>Scanned books.</b> Pages without a text layer are skipped; an OCR pass at indexing time would include them.",
        "<b>Model size.</b> 3B models reason less reliably than larger ones; the 5 GB limit allows 7B/8B models at about half the speed.",
        "<b>Evaluation.</b> A fixed question set with expected pages would measure retrieval accuracy over time (the G014 project had one).",
        "<b>Windows-only parts.</b> OCR, the Job Object and some voice paths are Windows-specific; the rest runs on Linux and macOS.",
        "<b>Memory curation.</b> Auto-learn can save trivial facts; a periodic merge or review step would keep memory tidy.",
    ])

    # ------------------------------------------------------------------ 12
    d.section("Repository contents", "repo")
    d.table(["Path", "Lines", "Purpose"], [[f"<code>{E(f['path'])}</code>", f"{f['lines']:,}", E(f["purpose"])] for f in files])
    d.p("Also in the repository: <code>BUILD_GUIDE.html</code> (rebuild everything from scratch), <code>docs/manifest.json</code> "
        "(every file's size and SHA-256), <code>tools/</code> (the scripts that generate these documents and the file "
        "checker). The previous Group G014 code is kept in the repository history under the tag <code>g014-final</code>.")
