"""guide_text.py - the written sections of BUILD_GUIDE.html (everything except the file listings)."""
from __future__ import annotations

import re

from docshell import Doc, E

ROOT_W = r"C:\Users\Mulenga Mwamba\Desktop\QuantaKai"


def c(x: str) -> str:
    return f"<code>{E(x)}</code>"


def link(url: str, text: str | None = None) -> str:
    return f'<a href="{E(url)}">{E(text or url.replace("https://", ""))}</a>'


# =========================================================================== 0
def intro(d: Doc, n_files: int, n_lines: int) -> None:
    d.raw("<h1>Build QuantaKai from scratch</h1>")
    d.raw("<p class='lead'>QuantaKai is a private assistant that runs entirely on a Windows laptop, from one folder you "
          "can move anywhere. It chats and remembers you, answers from your own books with page numbers, searches "
          "the web when you ask it to, writes stories and characters, runs the code it writes, reads pictures and "
          "documents, and talks and listens, all offline except Online mode. This guide lists every program, every "
          "download link, every folder, every command and every line of code needed to build it again from an empty "
          "folder.</p>")
    d.section("Before you start", "start")
    d.table(["You will end up with", "Details"], [
        ["Chat mode", "Personal conversations that stream word by word, with long-term memory that learns facts about you"],
        ["Offline mode", "Answers only from your books and notes (PDF, EPUB, Word, PowerPoint, text), with clickable [1] sources and page numbers; 80 subjects"],
        ["Online mode", "Searches the web (DuckDuckGo), reads the top pages, answers with numbered links"],
        ["Create mode", "Original stories and full character sheets"],
        ["Answer styles", "Detailed (default), Quick, Code (with a Run button), Teach (full lessons), Quiz (interactive quiz, flashcards, saved study guide)"],
        ["Extras", "Pictures (Windows text recognition), documents attached to a chat, voice typing, answers read aloud while they are written, highlight any text to hear or explain it"],
        ["Look and feel", "Light theme by default, dark theme, custom wallpaper, a nickname, and an animated mascot (the Blob) that dresses for each mode"],
        ["Models", "Any .gguf model up to 5 GB, switched by hand on the Models page or the picker"],
        ["Portable", "Its own Python, engine and models inside one folder; copy it to another drive or PC and it still runs"],
    ])
    d.table(["Effort", "Amount"], [
        ["Your time", "About 2 to 3 hours by hand, or about 20 minutes with SETUP.bat once the files exist"],
        ["Downloads", "About 2.1 GB required (engine, Python, two models); about 230 MB more for voice; Kokoro voice about 160 MB more"],
        ["Code", f"{n_files} files, {n_lines:,} lines, all included in this guide"],
    ])
    d.sub("How to use this guide")
    d.ul([
        "Work from top to bottom. Each step ends with a tick box; your progress shows in the menu on the left (saved in this browser).",
        "Commands go in <b>PowerShell</b> (<a href='#prepare'>Prepare Windows</a> shows how to open it). Grey boxes have a <b>Copy</b> button; file boxes also have <b>Save file</b>.",
        "Paths assume the folder <code>" + E(ROOT_W) + "</code>. If you use another place, change only that start of each path.",
        "Words in <code>this style</code> are typed exactly as shown: file names, commands, settings.",
    ])
    d.note("Rebuild protocol for AI assistants (read this first)",
           "<ol>"
           "<li>Follow the sections in order. Do not skip a section because it seems obvious.</li>"
           "<li>Create the folders in <a href='#make-folders'>Make the folders</a> exactly, including capital letters and spaces. Then download the engine, the models and the portable Python as described.</li>"
           "<li>In <a href='#files'>Create every file</a>, create every file in the listed order, copying each code box <b>exactly</b>: same text, same "
           "indentation (spaces, never tabs, in Python), same comments, same blank lines. Never write \"...rest of code...\".</li>"
           "<li>Save every file as UTF-8 without changing its name. Python files use 4-space indentation.</li>"
           "<li>Run the file checker (<a href='#verify'>Check every file</a>). Every line must say OK. Fix any file marked DIFFERENT by copying it again.</li>"
           "<li>Run the automatic test (<a href='#test'>Test without models</a>). It must end with <code>ALL TESTS PASSED</code>.</li>"
           "<li>Only then do the <a href='#first-run'>First real run</a>.</li>"
           "<li>If something fails, read the Troubleshooting section and the log files in <code>logs</code> before changing any code.</li>"
           "</ol>", "ai")
    d.tick("I read how this guide works")


# =========================================================================== 1
def architecture(d: Doc) -> None:
    d.section("How it fits together", "architecture")
    d.p("Four kinds of program work together on the laptop. The browser page talks only to QuantaKai's own small web "
        "server; the server talks to two copies of the llama.cpp engine; optional voice programs run when needed.")
    d.raw("""<div class="flow">
<div class="card"><b>Your browser</b><small>Shows ui\\index.html at http://127.0.0.1:8000. You type, talk and click here.</small></div><div class="arr">&#8644;</div>
<div class="card"><b>QuantaKai app (portable Python)</b><small>runtime\\python runs app\\server.py: finds memories, book passages, web pages and documents, builds the prompt, saves chats.</small></div><div class="arr">&#8644;</div>
<div class="card"><b>Chat engine :8090</b><small>llama-server.exe + a chat model such as Qwen2.5-3B (1.93 GB). Writes every reply.</small></div>
<div class="card"><b>Search engine :8091</b><small>llama-server.exe + bge-small (37 MB). Turns text into 384 numbers for searching.</small></div>
</div>""")
    d.table(["Program", "Started by", "Port / place", "Job"], [
        ["Browser", "server.py opens it", "http://127.0.0.1:8000", "The interface (one HTML file)"],
        ["python.exe -m app.server", "START.bat", "127.0.0.1:8000", "Web server, prompt building, search, memory, saving"],
        ["llama-server.exe (chat)", "engine.py", "127.0.0.1:8090", "Runs the chosen chat model"],
        ["llama-server.exe (search)", "engine.py", "127.0.0.1:8091", "Runs bge-small for vectors (--embeddings)"],
        ["whisper-cli.exe", "voice.py, per recording", "voice folder", "Speech to text (voice typing)"],
        ["piper.exe", "voice.py, kept running", "voice\\piper", "Text to speech, fast"],
        ["python.exe kokoro_worker.py", "voice.py, kept running", "voice\\sherpa-onnx-...", "Text to speech, most natural (optional)"],
        ["powershell.exe (OCR script)", "ocr.py, per picture", "data\\tmp", "Reads text from pictures with Windows OCR"],
    ])
    d.sub("What happens when you press Send")
    d.ul([
        "The page sends <code>POST /api/chat</code> with your message, the mode, the style and the chat's id.",
        "chat.py loads the chat from <code>data\\chats</code> and gathers context: memories (Chat), book passages (Offline), web extracts (Online), attached documents (any mode), text read from pictures.",
        "It builds the messages list: system instructions from prompts.py, as much recent history as fits, then your message with its context.",
        "llm.py sends it to the chat engine with streaming on. Each piece of text goes straight back to the page as a Server-Sent Event.",
        "When the answer ends, the chat is saved. In Chat mode the model is then asked, in the background, which new facts about you to remember.",
    ], ordered=True)
    d.sub("Design rules the code follows")
    d.ul([
        "<b>Offline first.</b> Nothing leaves the laptop except Online-mode searches and the one-time downloads.",
        "<b>Portable.</b> Every path is worked out from the folder the code is in (settings.py ROOT, START.bat <code>%~dp0</code>, relative ._pth file).",
        "<b>Few dependencies.</b> Only numpy and pymupdf beyond Python's own library. The page uses no frameworks and no internet fonts.",
        "<b>Safe by default.</b> Listens on 127.0.0.1 only, checks Host and Origin headers, escapes all model text before showing it, runs code only when you press Run.",
        "<b>One reply at a time.</b> A laptop has one engine; a lock queues requests instead of overloading it.",
        "<b>Never lose work.</b> JSON files are written atomically; one bad book never stops the others; Stop keeps the text written so far.",
    ])
    d.tick("I understand the parts")


# =========================================================================== 2
def glossary(d: Doc) -> None:
    d.section("Words you'll meet", "words")
    d.p("Every abbreviation and technical word in this guide, in plain English.")
    rows = [
        ("AI", "Artificial Intelligence: software that does tasks that normally need human thinking."),
        ("LLM", "Large Language Model: the kind of AI that reads and writes text (here Qwen2.5 3B)."),
        ("Model", "One file holding everything an AI learned. Bigger is usually smarter but slower."),
        ("3B / 2B", "3 billion / 2 billion parameters (the numbers inside the model)."),
        ("GGUF", "The model file format llama.cpp uses. Every real GGUF file starts with the 4 letters GGUF."),
        ("Q4_K_M", "A quantization level: the model's numbers are stored in about 4 bits. The usual best balance of size and quality."),
        ("Quantization", "Shrinking a model by storing its numbers less precisely: smaller and faster, slightly less accurate."),
        ("llama.cpp / llama-server", "Free program that runs GGUF models on ordinary computers; llama-server.exe is its web-server form, QuantaKai's engine."),
        ("mmproj", "Multimodal projector: a second GGUF file that lets some models see pictures."),
        ("Abliterated", "A model edited so it stops refusing requests; usually a little less accurate."),
        ("Token", "A word piece. Models read and write tokens; speed is tokens per second (tok/s)."),
        ("Context window", "How many tokens the model sees at once: instructions + history + passages + its answer. Here 4096."),
        ("Temperature", "Randomness when choosing words. Low (0.2) = careful and repeatable, high (0.9) = imaginative."),
        ("Prompt / system prompt", "The text sent to the model. The system prompt is the instructions part (prompts.py)."),
        ("RAG", "Retrieval-Augmented Generation: find relevant passages first, then let the model answer from them. Offline and Online modes are RAG."),
        ("Embedding / vector", "A list of numbers (here 384) that captures the meaning of a text. Similar meanings give similar lists."),
        ("bge-small", "BAAI General Embedding, small: the tiny model that makes the vectors. BAAI = Beijing Academy of Artificial Intelligence."),
        ("CLS pooling", "How bge turns a passage's word vectors into one: it takes the special first token's vector."),
        ("Dot product / cosine", "Multiply two vectors number by number and add up: the similarity score of two unit-length vectors (0 to 1)."),
        ("BM25", "Best Matching 25: the classic keyword-search score. Rare words that appear often in a passage score high."),
        ("RRF", "Reciprocal Rank Fusion: merges two ranked lists by adding 1/(60+rank) from each, so a passage ranked high by either rises."),
        ("Passage / chunk", "A piece of a book (about 180 words) that is searched and shown as a source."),
        ("OCR", "Optical Character Recognition: reading text from a picture."),
        ("STT / TTS", "Speech-To-Text (voice typing) and Text-To-Speech (reading aloud)."),
        ("Whisper / whisper.cpp", "OpenAI's open speech-recognition model, run by the whisper.cpp program."),
        ("Piper", "A fast offline text-to-speech program with downloadable voices (.onnx files)."),
        ("Kokoro / sherpa-onnx", "Kokoro is a natural-sounding voice model; sherpa-onnx is the program library that runs it."),
        ("ONNX", "Open Neural Network Exchange: a common file format for AI models (used by Piper and Kokoro)."),
        ("WAV", "A simple uncompressed sound file format."),
        ("CPU / GPU / iGPU", "Central Processing Unit (the processor); Graphics Processing Unit; integrated GPU built into the processor (Radeon Vega 8)."),
        ("Vulkan", "A graphics programming interface; llama.cpp's Vulkan build can use the Vega 8."),
        ("RAM", "Random Access Memory: the fast working memory. A model must fit in free RAM."),
        ("SSD / NVMe", "Solid-State Drive / Non-Volatile Memory Express: fast storage; models load in seconds."),
        ("PDF / EPUB / DOCX / PPTX", "Book and document file formats: Portable Document Format, Electronic Publication, Word, PowerPoint."),
        ("Python / embeddable Python", "The language the app is written in; the embeddable package is a complete Python in one folder that needs no installing."),
        ("._pth file", "A text file beside portable Python listing where it looks for code. QuantaKai's has only relative paths."),
        ("Wheel (.whl) / pip", "The file format Python packages come in (a zip file); pip is Python's package installer."),
        ("PyPI", "Python Package Index (pypi.org), where Python packages are published."),
        ("PATH", "The list of folders Windows searches when you type a command."),
        ("PowerShell / .ps1 / .bat", "Windows' command window; a PowerShell script file; a batch file of commands you double-click."),
        ("HTTP / API / JSON", "How a browser and server talk; the set of addresses the page uses; a simple text format for data, like {\"name\": \"Mwamba\"}."),
        ("SSE", "Server-Sent Events: the server keeps the connection open and sends the answer piece by piece as 'data:' lines."),
        ("URL / localhost / 127.0.0.1", "A web address; your own computer. Addresses starting 127.0.0.1 never leave the laptop."),
        ("Port", "A numbered door on a computer: 8000 (page), 8090 (chat engine), 8091 (search engine)."),
        ("PID", "Process ID: the number Windows gives each running program."),
        ("Job Object", "A Windows feature that groups processes; QuantaKai's job kills the engines when the app closes."),
        ("DNS rebinding", "An attack where a web page tricks the browser into talking to apps on localhost. Blocked by checking the Host header."),
        ("CSRF", "Cross-Site Request Forgery: another website quietly sending requests to a local app. Blocked by checking the Origin header."),
        ("HTML / CSS / JS", "HyperText Markup Language (structure), Cascading Style Sheets (looks), JavaScript (behaviour)."),
        ("Canvas", "An HTML element JavaScript draws on; the Blob mascot is drawn on one."),
        ("UTF-8", "The standard way of storing text characters. Save every file as UTF-8."),
        ("SHA-256", "Secure Hash Algorithm: a 64-character fingerprint of a file. Two files with the same SHA-256 are identical."),
    ]
    d.table(["Word", "Meaning"], [[f"<b>{E(a)}</b>", E(b)] for a, b in rows])


# =========================================================================== 3
def hardware(d: Doc) -> None:
    d.section("Your laptop and the space you need", "laptop")
    d.table(["Part", "This build was made on", "Why it matters"], [
        ["Laptop", "HP EliteBook 735 G6", "Any 64-bit Windows 10/11 PC with 8 GB+ RAM works; 16 GB is comfortable"],
        ["Processor", "AMD Ryzen 5 PRO 3500U, 4 cores / 8 threads", "Runs the model; sets the speed (about 12 tokens/s writing with a 3B Q4 model)"],
        ["Memory", "16 GB (13.9 GB usable)", "The model must fit in free RAM, which is why the model limit is 5 GB"],
        ["Storage", "256 GB NVMe SSD", "Models load in seconds"],
        ["Graphics", "Radeon Vega 8 (built in)", "Optional Vulkan test in the Speed section"],
        ["System", "Windows 11 Pro", "Commands here are for Windows 10 and 11"],
    ])
    d.table(["Item", "Disk space"], [
        ["Portable Python with numpy and pymupdf (plus 76 MB of wheels kept for re-setup)", "about 250 MB"],
        ["llama.cpp engine (CPU build)", "about 50 to 100 MB"],
        ["Qwen2.5-3B-Instruct Q4_K_M chat model", "1.93 GB"],
        ["bge-small search model", "37 MB"],
        ["Voice typing and Piper voice", "about 230 MB"],
        ["Kokoro voice (optional)", "about 160 MB download, 300 MB unpacked"],
        ["Book index", "about 3 to 8 MB per book"],
        ["Total to start", "about 2.5 GB, plus your books and any extra models"],
    ])
    d.tick("I have at least 6 GB free on drive C:")


# =========================================================================== 4
def downloads(d: Doc) -> None:
    d.section("Everything you will download", "downloads")
    d.p("All software is free. The first four rows are required; SETUP.bat and VOICE_SETUP.bat can fetch most of it for you.")
    req = "<b>Required</b>"
    opt = "Optional"
    d.table(["What", "Get it from", "File", "Goes in"], [
        [f"{req} llama.cpp engine (CPU build)", link("https://github.com/ggml-org/llama.cpp/releases"), "llama-bNNNN-bin-win-cpu-x64.zip", c("engine\\")],
        [f"{req} Python 3.14 embeddable package", link("https://www.python.org/downloads/windows/"), "python-3.14.x-embed-amd64.zip", c("runtime\\python\\")],
        [f"{req} numpy wheel for Python 3.14", link("https://pypi.org/project/numpy/#files"), "numpy-2.x-cp314-cp314-win_amd64.whl", c("runtime\\wheels\\")],
        [f"{req} PyMuPDF wheel", link("https://pypi.org/project/PyMuPDF/#files"), "pymupdf-…-cp311-abi3-win_amd64.whl (abi3 works on 3.14)", c("runtime\\wheels\\")],
        [f"{req} Chat model", link("https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF"), "Qwen2.5-3B-Instruct-Q4_K_M.gguf (1.93 GB)", c("models\\")],
        [f"{req} Search model", link("https://huggingface.co/ggml-org/bge-small-en-v1.5-Q8_0-GGUF"), "bge-small-en-v1.5-q8_0.gguf (37 MB)", c("models\\")],
        [f"{opt} Coding model", link("https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-GGUF"), "Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf (1.93 GB)", c("models\\")],
        [f"{opt} Small model that can see pictures", link("https://huggingface.co/unsloth/Qwen3.5-2B-GGUF"), "Qwen3.5-2B-Q4_K_M.gguf (1.28 GB) + mmproj-F16.gguf renamed to Qwen3.5-2B-mmproj-F16.gguf", c("models\\")],
        [f"{opt} Voice typing engine", link("https://github.com/ggml-org/whisper.cpp/releases"), "whisper-bin-x64.zip", c("voice\\")],
        [f"{opt} Voice typing model", link("https://huggingface.co/ggerganov/whisper.cpp"), "ggml-base.en.bin (148 MB)", c("voice\\")],
        [f"{opt} Piper (reading aloud, fast)", link("https://github.com/rhasspy/piper/releases/tag/2023.11.14-2"), "piper_windows_amd64.zip", c("voice\\piper\\")],
        [f"{opt} Piper voice", link("https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/hfc_female/medium"), "en_US-hfc_female-medium.onnx + .onnx.json", c("voice\\")],
        [f"{opt} sherpa-onnx (runs Kokoro)", link("https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.5"), "sherpa-onnx-v1.13.5-win-x64-shared-MT-Release.tar.bz2 (must be v1.13.5)", c("voice\\")],
        [f"{opt} Kokoro voice model", link("https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models"), "kokoro-int8-multi-lang-v1_0.tar.bz2", c("voice\\")],
        [f"{opt} Code editor", link("https://code.visualstudio.com/"), "Visual Studio Code", "installed normally"],
        [f"{opt} Java (to run Java code)", link("https://adoptium.net/"), "Temurin JDK 17 or newer", "installed normally"],
        [f"{opt} Download manager", link("https://www.freedownloadmanager.org/"), "Free Download Manager: resumes big downloads", "installed normally"],
    ])
    d.note("Big downloads", "<p>Downloads in a browser or Free Download Manager can be dropped into a folder named "
           "<code>new stuff</code> inside QuantaKai. At the next start, organize.py moves each one to the right folder "
           "(.gguf to models, voice files to voice) and voice.py unpacks voice archives automatically.</p>")


# =========================================================================== 5
def folders(d: Doc) -> None:
    d.section("The folder layout", "layout")
    d.p("QuantaKai lives in one folder. Everything it needs goes inside it. The folders marked <i>(made by you)</i> are "
        "created in <a href='#make-folders'>Make the folders</a>; the others are created by the app or by downloads.")
    d.code(r"""QuantaKai\
|-- START.bat  STOP.bat  SETUP.bat  VOICE_SETUP.bat
|-- config.json  requirements.txt  README.txt  BUILD_GUIDE.html
|-- app\            (made by you) the Python program: server.py, chat.py, library.py ...
|-- ui\             (made by you) index.html - the whole interface
|-- scripts\        (made by you) setup.ps1, setup_voice.ps1
|-- tests\          (made by you) smoke_test.py, fake_llama_server.py
|-- tools\          build_docs.py and friends (only to rebuild this guide), verify_files.py
|-- runtime\
|   |-- python\     portable Python 3.14 (python.exe, python314._pth, Lib\site-packages\numpy, pymupdf)
|   `-- wheels\     numpy and pymupdf .whl files
|-- engine\         llama.cpp: llama-server.exe and its .dll files
|-- models\         Qwen2.5-3B-Instruct-Q4_K_M.gguf, bge-small-en-v1.5-q8_0.gguf, other .gguf models
|-- books\          your PDFs, EPUBs, Word, PowerPoint, .txt and .md notes
|-- voice\          whisper-cli.exe + ggml-base.en.bin, piper\, Piper voices, sherpa-onnx + Kokoro (optional)
|-- new stuff\      drop downloads here; they are moved to the right folder at start-up
|-- data\           everything QuantaKai saves (never leaves the PC)
|   |-- chats\      one .json per conversation
|   |-- chat_docs\  documents attached to chats
|   |-- library\    books.json, categories.json, <book>.jsonl + <book>.npy per book
|   |-- tmp\        short-lived files (OCR, voice)
|   |-- memory.json  state.json  engine_pids.json  wallpaper.jpg
`-- logs\           chat-engine.log, embed-engine.log, setup_report.txt, voice_setup.txt""", "folder tree", short=True)
    d.note("What goes on GitHub", "<p>Only the code and documents: app, ui, scripts, tests, tools, docs, the .bat files, "
           "config.json, requirements.txt and the read-me files. Never runtime, engine, models, voice, books or data: "
           "they are huge, downloadable or private. The .gitignore file enforces this.</p>")


# =========================================================================== 6-7
def prepare(d: Doc) -> None:
    d.section("Prepare Windows", "prepare")
    d.sub("Show file extensions (do this first)")
    d.p("Windows hides endings like .bat and .txt. If they are hidden, an editor can save <code>START.bat</code> as "
        "<code>START.bat.txt</code> and it will not run.")
    d.ul(["Open File Explorer (<kbd>Windows</kbd>+<kbd>E</kbd>).", "Click <b>View</b>, then <b>Show</b>, then tick <b>File name extensions</b>."], ordered=True)
    d.sub("Open PowerShell")
    d.p("Press <kbd>Windows</kbd>, type <b>PowerShell</b>, press <kbd>Enter</kbd>. To open it inside a folder: open the folder "
        "in File Explorer, click the address bar, type <code>powershell</code> and press <kbd>Enter</kbd>. Windows already "
        "includes <code>curl.exe</code> (downloads) and <code>tar.exe</code> (unpacks .tar.bz2), which this guide uses.")
    d.sub("A code editor")
    d.p(f"{link('https://code.visualstudio.com/', 'Visual Studio Code')} is free, colours code and saves UTF-8 automatically. "
        "Notepad also works: in Save As choose <b>All files (*.*)</b> and Encoding <b>UTF-8</b>.")
    d.tick("Extensions are visible and I can open PowerShell")

    d.section("Make the folders", "make-folders")
    d.p("Run this once in PowerShell. The quotes matter because the user name has a space.")
    d.code(r"""$Q = "$HOME\Desktop\QuantaKai"
'app','ui','scripts','tests','tools','docs','runtime\python','runtime\wheels','engine','models',
'books','voice','new stuff','data','logs' | ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $Q $_) | Out-Null }
Set-Location $Q
Get-ChildItem""", "PowerShell - create the folders")
    d.tick("The folders exist")


# =========================================================================== 8-9
def engine_and_models(d: Doc) -> None:
    d.section("Download the engine (llama.cpp)", "engine")
    d.ul([
        f"Open {link('https://github.com/ggml-org/llama.cpp/releases')}. New builds appear almost daily, named b + a number; any recent one works.",
        "Under the newest release click <b>Assets</b>, then download the file ending <code>-bin-win-cpu-x64.zip</code>. "
        "(The <code>-vulkan-x64</code> file is only for the graphics test in the Speed section; CUDA files are for NVIDIA cards.)",
        "Right-click the zip, <b>Properties</b>, tick <b>Unblock</b> if it is there, OK.",
        "Right-click, <b>Extract All…</b>, into <code>" + E(ROOT_W) + "\\engine</code>. A sub-folder is fine; the app searches the whole engine folder.",
    ], ordered=True)
    d.code(r"""$exe = (Get-ChildItem .\engine -Recurse -Filter llama-server.exe | Select-Object -First 1).FullName
& $exe --version""", "PowerShell - check the engine (in the QuantaKai folder)")
    d.p("You should see a version line with a build number. If SmartScreen appears, choose <b>More info</b>, <b>Run anyway</b>.")
    d.tick("llama-server.exe --version works")

    d.section("Download the models", "models-download")
    d.p("Models come from Hugging Face. Both required files go in the models folder with exactly these names. "
        "<code>-C -</code> resumes a broken download: just run the same line again.")
    d.code(r"""curl.exe -L -C - -o models\Qwen2.5-3B-Instruct-Q4_K_M.gguf https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf
curl.exe -L -C - -o models\bge-small-en-v1.5-q8_0.gguf https://huggingface.co/ggml-org/bge-small-en-v1.5-Q8_0-GGUF/resolve/main/bge-small-en-v1.5-q8_0.gguf""",
           "PowerShell - download both models")
    d.code(r"""Get-ChildItem models\*.gguf | ForEach-Object {
  $b = [byte[]]::new(4); $f = [IO.File]::OpenRead($_.FullName); [void]$f.Read($b, 0, 4); $f.Close()
  '{0,-45} {1,8:N2} GB  {2}' -f $_.Name, ($_.Length / 1GB), ([Text.Encoding]::ASCII.GetString($b))
}""", "PowerShell - check the models (each must end with GGUF)")
    d.p("Optional now, to see the engine work before any code exists (open http://127.0.0.1:8090 in a browser, then press "
        "<kbd>Ctrl</kbd>+<kbd>C</kbd> in PowerShell to stop it):")
    d.code(r"""& $exe -m models\Qwen2.5-3B-Instruct-Q4_K_M.gguf --port 8090 -c 4096""", "PowerShell - try the engine on its own")
    d.tick("Both .gguf files are in models and start with GGUF")


def portable_python(d: Doc) -> None:
    d.section("Set up the portable Python", "python")
    d.p("Python's embeddable package is a complete Python in a zip file. Unzipped into <code>runtime\\python</code> it runs "
        "without installing anything, and keeps working when the folder moves. It must be <b>3.14</b>, because the numpy "
        "wheel is made for 3.14 (cp314).")
    d.ul([
        f"On {link('https://www.python.org/downloads/windows/')} pick the newest Python 3.14 release and download "
        "<b>Windows embeddable package (64-bit)</b>, for example <code>python-3.14.5-embed-amd64.zip</code>. "
        "Direct link pattern: <code>https://www.python.org/ftp/python/3.14.5/python-3.14.5-embed-amd64.zip</code>.",
        "Extract it into <code>runtime\\python</code>. You should see <code>python.exe</code> and <code>python314._pth</code> directly inside.",
        "Open <code>python314._pth</code> and replace everything in it with the five lines below. Save.",
        f"Download the numpy wheel ending <code>cp314-cp314-win_amd64.whl</code> from {link('https://pypi.org/project/numpy/#files')} "
        f"and the PyMuPDF wheel ending <code>win_amd64.whl</code> from {link('https://pypi.org/project/PyMuPDF/#files')} into <code>runtime\\wheels</code>.",
        "Run the unpack-and-check commands below.",
    ], ordered=True)
    d.code("python314.zip\n.\nLib\\site-packages\n..\\..\nimport site", "runtime\\python\\python314._pth")
    d.p("Line by line: the standard library zip; the Python folder; the packages folder; <code>..\\..</code> = two folders up = "
        "the QuantaKai folder, so <code>app</code> can be imported; <code>import site</code> turns on normal package loading. "
        "All relative, so moving the folder is safe. (If your zip is named differently, e.g. python315.zip, use its name.)")
    d.code(r"""New-Item -ItemType Directory -Force runtime\python\Lib\site-packages | Out-Null
Get-ChildItem runtime\wheels\*.whl | ForEach-Object {
  runtime\python\python.exe -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" $_.FullName runtime\python\Lib\site-packages
}
runtime\python\python.exe -c "import sys, numpy, pymupdf; print(sys.version.split()[0], numpy.__version__, pymupdf.__version__)" """,
           "PowerShell - unpack the wheels and check")
    d.p("The last line must print three version numbers, for example <code>3.14.5 2.5.4 1.26.x</code>.")
    d.note("Alternative with pip", "<p>Any installed Python can fetch matching packages straight into the portable one:<br>"
           "<code>py -m pip install --target runtime\\python\\Lib\\site-packages --platform win_amd64 --python-version 3.14 "
           "--only-binary=:all: -r requirements.txt</code></p>")
    d.tick("The portable Python printed three version numbers")


# =========================================================================== 12 verify
def verify_script(files: list[dict]) -> str:
    table = "\n".join(f'    "{f["path"]}": "{f["sha256"]}",' for f in files)
    return f'''r"""verify_files.py - checks that every QuantaKai source file is exactly right.

Run from the QuantaKai folder:   runtime\\python\\python.exe tools\\verify_files.py
Each file's SHA-256 fingerprint is compared with the one in the build guide.
Windows line endings (CRLF) and plain ones (LF) count as the same.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {{
{table}
}}


def fingerprint(path: Path) -> str:
    text = path.read_bytes().decode("utf-8-sig").replace("\\r\\n", "\\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


bad = 0
for rel, want in EXPECTED.items():
    p = ROOT / rel
    if not p.exists():
        print(f"MISSING    {{rel}}")
        bad += 1
    elif fingerprint(p) != want:
        print(f"DIFFERENT  {{rel}}  (copy it again from the guide)")
        bad += 1
    else:
        print(f"OK         {{rel}}")
print()
print("ALL FILES MATCH" if not bad else f"{{bad}} file(s) need fixing")
sys.exit(1 if bad else 0)
'''


def verify(d: Doc, files: list[dict]) -> None:
    d.section("Check every file", "verify")
    d.p("A typo anywhere can stop the app. This checker compares every file you created with the original using its "
        "SHA-256 fingerprint. Save it as <code>tools\\verify_files.py</code>, then run it.")
    d.code(verify_script(files), "tools\\verify_files.py", save_as="verify_files.py")
    d.code(r"runtime\python\python.exe tools\verify_files.py", "PowerShell - in the QuantaKai folder")
    d.p("Every line must start with <b>OK</b> and the last line must say <b>ALL FILES MATCH</b>. For a DIFFERENT file, "
        "use its <b>Save file</b> button instead of copy and paste, then run the checker again.")
    d.tick("ALL FILES MATCH")


# =========================================================================== 13
def smoke_test(d: Doc, test_source: str) -> None:
    d.section("Test without models", "test")
    d.p("This runs the whole app in a temporary folder with the pretend engine (tests\\fake_llama_server.py), makes a "
        "small test PDF and checks each feature. It needs no real models and never touches your folders.")
    d.code(r"runtime\python\python.exe tests\smoke_test.py", "PowerShell - in the QuantaKai folder")
    names = re.findall(r'check\(\s*"([^"]+)"', test_source)
    d.p(f"Expected: {len(names)} lines that say PASS, then <b>ALL TESTS PASSED</b>. A FAIL names the part that broke, "
        "usually a typo in the file of the same name.")
    d.table(["#", "Check"], [[str(i + 1), E(n)] for i, n in enumerate(names)])
    d.tick("ALL TESTS PASSED")


# =========================================================================== 14
def first_run(d: Doc) -> None:
    d.section("First real run", "first-run")
    d.ul([
        "Double-click <b>START.bat</b>. A black window says QuantaKai is running. Keep it open.",
        "The browser opens <code>http://127.0.0.1:8000</code>. The model picker shows Loading for a few seconds, then the model name.",
        "<b>Chat:</b> type \"Hi, I'm Mwamba, a second-year data science student\". The reply streams in; a few seconds later the Memory count goes up (auto-learn).",
        "<b>Library:</b> click <b>Open books folder</b>, copy in your books, then <b>Add all new</b> (or Add on one book). A progress bar and a time estimate show for each book.",
        "<b>Offline:</b> back in Chat, click Offline, keep Detailed, and ask a question from one of your books. The sources bar lists the exact pages; any [1] in the answer jumps to its source.",
        "Click <b>Simpler please</b> under an answer for a beginner version from the same pages.",
        "<b>Online:</b> ask about something recent; the answer cites numbered web pages.",
        "<b>Create:</b> choose Story or Character and give a prompt.",
        "<b>Models:</b> lists every .gguf; blocked files say why. Press Load, or use the picker at the top.",
        "<b>Personalise:</b> set a nickname (press Hear it to check how it sounds), theme and wallpaper.",
        "To quit: close the black window (the engines close with it) or double-click <b>STOP.bat</b>.",
    ], ordered=True)
    d.note("Shortcut: SETUP.bat", "<p>Once all files exist, <b>SETUP.bat</b> does the engine, model and portable Python steps for you: portable Python "
           "(+ the wheels in runtime\\wheels), the newest llama.cpp CPU build, both models, and a speed test. Results go "
           "to <code>logs\\setup_report.txt</code>. It is safe to run again.</p>")
    d.note("Moving QuantaKai", "<p>Quit first, then move or copy the whole folder anywhere (another drive, a USB disk, another "
           "Windows PC). START.bat works from the new place with your books, memories and chats.</p>", "ok")
    d.tick("I chatted, added books and got an Offline answer with sources")


# =========================================================================== 15 voice
def voice_setup(d: Doc) -> None:
    d.section("Voice: talking and listening", "voice")
    d.sub("Voice typing and the fast reading voice")
    d.p("Double-click <b>VOICE_SETUP.bat</b> once (internet, about 230 MB). It downloads whisper.cpp, the Whisper "
        "<code>ggml-base.en.bin</code> model, Piper and the <code>en_US-hfc_female-medium</code> voice into <code>voice</code>, "
        "plays a short test sentence, and writes <code>logs\\voice_setup.txt</code>. Then restart QuantaKai.")
    d.p("By hand instead: unzip <code>whisper-bin-x64.zip</code> into <code>voice</code>; put <code>ggml-base.en.bin</code> in "
        "<code>voice</code>; unzip <code>piper_windows_amd64.zip</code> into <code>voice\\piper</code>; put the voice's "
        "<code>.onnx</code> and <code>.onnx.json</code> in <code>voice</code>. (Or drop the zips in <code>voice</code> or "
        "<code>new stuff</code>: QuantaKai unpacks them at start-up.)")
    d.sub("Kokoro: the most natural voice (optional)")
    d.ul([
        f"Download <code>sherpa-onnx-v1.13.5-win-x64-shared-MT-Release.tar.bz2</code> from {link('https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.5')}. "
        "<b>Use v1.13.5 exactly</b>: kokoro_worker.py copies that version's C structure layouts.",
        f"Download <code>kokoro-int8-multi-lang-v1_0.tar.bz2</code> from {link('https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models')}.",
        "Put both files in <code>voice</code> (or <code>new stuff</code>) and start QuantaKai: it unpacks them (about a minute). Or unpack yourself: "
        "<code>tar -xf voice\\kokoro-int8-multi-lang-v1_0.tar.bz2 -C voice</code> and the same for sherpa-onnx.",
        "In the voice menu (the speaker button at the top) choose a Kokoro voice, for example Heart, and press Preview.",
    ], ordered=True)
    d.table(["File QuantaKai looks for (anywhere inside voice)", "Used for"], [
        [c("whisper-cli.exe") + " + " + c("ggml-base.en.bin"), "Voice typing"],
        [c("piper\\…\\piper.exe") + " + " + c("<voice>.onnx") + " + " + c("<voice>.onnx.json"), "Fast reading voice"],
        [c("sherpa-onnx-offline-tts.exe"), "Kokoro, slow per-sentence fallback"],
        [c("sherpa-onnx-c-api.dll"), "Kokoro kept in memory by kokoro_worker.py (fast)"],
        [c("voices.bin") + ", " + c("tokens.txt") + ", " + c("model.int8.onnx") + ", " + c("espeak-ng-data\\"), "The Kokoro model folder"],
    ])
    d.sub("Using voice")
    d.ul([
        "<b>Voice typing:</b> click the microphone, speak, click again. The words appear in the box (and are sent in Voice mode).",
        "<b>Voice mode</b> (the speaker button): answers are read aloud sentence by sentence while they are written, and kept short (2 to 4 sentences).",
        "<b>Read aloud</b> under any answer, or highlight any text on the page and choose Read aloud.",
        "<b>Stop:</b> the Stop talking pill, or <kbd>Esc</kbd>.",
        "Without Piper or Kokoro the page falls back to the Windows built-in voices.",
    ])
    d.tick("Voice typing and reading aloud work")


# =========================================================================== 16
def how_it_works(d: Doc) -> None:
    d.section("How each feature works", "how")
    d.sub("Chat mode and memory")
    d.ul([
        "memory.relevant() embeds your message and picks up to 4 stored facts scoring 0.55 or more; they are added to CHAT_SYSTEM under \"Things you know about…\".",
        "\"remember that …\" is caught by a regular expression and saved at once; the reply event says \"Saved to memory.\"",
        "After the reply, a background job asks the model with MEMORY_EXTRACT for new facts (temperature 0, 120 tokens). Facts 0.92 similar to existing ones are skipped.",
        "History: up to the last 12 exchanges, newest first, as many as fit in the token budget.",
    ])
    d.sub("Offline mode (your books)")
    d.ul([
        "The question is spell-checked against the words in your books (search only), turned into a vector with the bge query prefix, and compared with every passage (one matrix multiplication).",
        "The same question is scored with BM25 keywords. The two rankings are fused (RRF). Overlapping passages from the same pages are dropped.",
        "Subject: the one chosen in the subject picker, or Auto, which keeps the best-matching subject plus any within 0.03 of it.",
        "The top 4 passages scoring at least study_min_score (0.40), or with a strong keyword match, are numbered [1]-[4] with title and pages.",
        "The style's rules (Detailed, Quick, Code, Teach, Quiz) tell the model to use only those passages and cite them, or say \"I couldn't find this in your books.\"",
        "Follow-ups under 6 words are searched together with the previous question. Simpler please reuses the same passages.",
    ])
    d.sub("Adding a book")
    d.ul([
        "Text is pulled out page by page (PyMuPDF for PDF/EPUB; built-in XML readers for Word and PowerPoint).",
        "All words are cut into 180-word passages that overlap by 40, each remembering its first and last page.",
        "Passages are embedded 16 at a time; a passage the engine rejects is shortened and retried, so one odd page cannot fail the book.",
        "Files saved: <book>.jsonl, <book>.npy, an entry in books.json, and an automatic subject. Time per book: about 4 to 12 minutes for a 300 to 900 page book on this laptop.",
    ])
    d.sub("Online mode")
    d.ul(["web.gather(): DuckDuckGo HTML results, the top 3 pages fetched in parallel (8 s timeout each), the best paragraphs up to 170 words a page, numbered [1]-[3] with links."])
    d.sub("Create mode")
    d.ul(["No books, no web. STORY_RULES (600-900 words, a bold title, continue on \"continue\") or CHARACTER_RULES (a fixed character sheet). Temperature 0.9, up to 1500 / 1100 tokens."])
    d.sub("Pictures and documents")
    d.ul([
        "Pictures (paste, drag or the picture button, up to 4 per message): Windows OCR reads their text, which is added to the question; a vision model also sees the image.",
        "Documents (the paperclip): read once by docs.py and saved with that chat. Every question in that chat gets the whole text if it fits, otherwise the most relevant 1000-character chunks.",
    ])
    d.sub("Code, Teach and Quiz")
    d.ul([
        "Code: complete runnable code in a fenced block. Python and Java blocks get a Run button (POST /api/run); output appears under the code; Fix this error sends the error back.",
        "Teach: a full lesson (goals, definition, formulas, worked examples, mistakes, 3 practice questions) or a project walkthrough.",
        "Quiz: 6 multiple-choice questions and 8 flashcards in a fixed format; the page turns them into an interactive quiz and can save a printable study guide.",
    ])
    d.sub("Retry, Edit and Stop")
    d.ul(["Each question and its answer share a turn tag. Retry and Edit send rewind=<tag> so the old answer is removed before the new one is written. Stop closes the connection; the engine stops writing and the text so far is kept."])


# =========================================================================== 17
def api(d: Doc) -> None:
    d.section("HTTP API reference", "api")
    d.p("All addresses are on <code>http://127.0.0.1:8000</code>. Requests must carry <code>Host: 127.0.0.1:8000</code> "
        "(or localhost:8000); POST, PUT and DELETE are refused (403) if an Origin header from another site is present. "
        "Bodies are JSON unless stated.")
    rows = [
        ("GET", "/", "-", "The page (ui/index.html)"),
        ("GET", "/api/status", "-", "app_name, user_name, nickname, config_name, wallpaper, wall_dim, wall_blur, chat{state,model,error}, search{state,error}, books, passages, memories, auto_learn, max_model_gb, voice{…}, run{python,java}, images{ocr,vision}"),
        ("GET", "/api/models", "-", "models[{name,size_gb,allowed,reason}], active, state, max_gb"),
        ("POST", "/api/models/load", "{name}", "Starts loading in the background: {ok}"),
        ("GET", "/api/books", "-", "books[…], progress{running,book,done_books,total_books,step,percent,messages}, categories, category_groups, queue"),
        ("POST", "/api/books/scan", "-", "Queue every new or changed book (409 if the search engine is not ready)"),
        ("POST", "/api/books/add", "{files:[…]} or {file}", "{ok, queued}"),
        ("POST", "/api/books/category", "{file, category}", "Set a book's subject (a new name creates your own subject)"),
        ("POST", "/api/chat", "{conv_id, mode, style, message, simpler, book_category, images[], turn, rewind, voice}", "Server-Sent Events, one data: line each: meta, status, notice, ocr, memory, sources, context, token, done, error"),
        ("GET", "/api/chats", "-", "chats[{id,title,updated}], newest first"),
        ("GET", "/api/chats/&lt;id&gt;", "-", "The whole conversation file"),
        ("DELETE", "/api/chats/&lt;id&gt;", "-", "Deletes the chat and its documents"),
        ("POST", "/api/docs", "{conv_id, name, data (base64 or data URL)}", "{ok, conv_id, doc, docs} or {ok:false, error}"),
        ("DELETE", "/api/docs/&lt;conv&gt;/&lt;doc&gt;", "-", "{ok, docs}"),
        ("GET", "/api/memory", "-", "memories, newest first (without vectors)"),
        ("POST", "/api/memory", "{text}", "{ok, item}"),
        ("PUT", "/api/memory/&lt;id&gt;", "{text}", "{ok}"),
        ("DELETE", "/api/memory/&lt;id&gt;", "-", "{ok}"),
        ("POST", "/api/settings", "{auto_learn?, nickname?, wall_dim?, wall_blur?}", "Saves to state.json, returns status"),
        ("GET", "/api/wallpaper", "-", "The picture (404 if none)"),
        ("POST", "/api/wallpaper", "{data: data URL}", "PNG/JPG/GIF/WebP up to 15 MB"),
        ("DELETE", "/api/wallpaper", "-", "{ok}"),
        ("POST", "/api/run", "{code, language: python|java}", "{ok, output, error, exit_code, seconds}"),
        ("GET", "/api/voices", "-", "options[{engine,id,name,group}], choice, active, kokoro"),
        ("POST", "/api/voices", "{engine: auto|kokoro|piper|windows, id}", "Saves the choice and pre-makes the preview"),
        ("POST", "/api/voice/speak", "{text} or {preview: true}", "audio/wav (503 + {error} if no voice)"),
        ("POST", "/api/voice/transcribe", "raw 16 kHz mono WAV body (≤ 30 MB)", "{ok, text}"),
        ("POST", "/api/open-folder", "{which: books|models}", "Opens the folder in File Explorer"),
    ]
    d.table(["Method", "Path", "Body", "Answer"], [[m, f"<code>{p}</code>", E(b), E(a)] for m, p, b, a in rows])
    d.sub("Server-Sent Events from /api/chat")
    d.table(["type", "Fields", "Meaning"], [
        ["meta", "conv_id, title", "Always first: which chat this is"],
        ["status", "text", "Progress note (reading a picture, searching the web)"],
        ["notice", "text", "A warning to show as a toast"],
        ["ocr", "text", "Text read from the pictures"],
        ["memory", "saved[], note", "\"remember that\" result"],
        ["sources", "sources[], categories[], corrections{}", "Book passages or web pages used (Offline/Online)"],
        ["context", "names[]", "Attached documents used"],
        ["token", "text", "The next piece of the answer"],
        ["done", "stats{tokens_per_second, seconds}", "The answer finished"],
        ["error", "message", "Something went wrong; nothing more follows"],
    ])


# =========================================================================== 18
def data_files(d: Doc) -> None:
    d.section("Data files and formats", "data")
    d.table(["File", "Format"], [
        [c("data\\state.json"), "{last_model, auto_learn, nickname, wall_dim, wall_blur, voice:{engine, kokoro_sid, piper_voice}}"],
        [c("data\\memory.json"), "[{id, text, source: manual|auto, created, vec: [384 floats]}]"],
        [c("data\\chats\\<id>.json"), "{id, title, created, updated, messages:[{role, content, mode, style, turn, display?, sources?, stats?}], docs?:[{id, name, chars, words, added}]}. Ids look like 20261113-101500-a1b2."],
        [c("data\\chat_docs\\<chat id>\\<doc id>.txt"), "The extracted text of an attached document"],
        [c("data\\library\\books.json"), "{book_id: {file, title, pages, empty_pages, passages, size, mtime, added, seconds, category_auto}}"],
        [c("data\\library\\<book_id>.jsonl"), "One passage per line: {id, book_id, page, page_end, text}"],
        [c("data\\library\\<book_id>.npy"), "numpy float32 array, shape (passages, 384); row i belongs to line i"],
        [c("data\\library\\categories.json"), "{\"<file name>\": \"<subject>\", \"_custom\": [your own subjects]}"],
        [c("data\\engine_pids.json"), "{chat: pid, embed: pid, ui: pid}"],
        [c("data\\wallpaper.<png|jpg|gif|webp>"), "Your wallpaper"],
        [c("logs\\chat-engine.log, embed-engine.log"), "The exact engine command and everything it printed"],
    ])
    d.p("book_id = the file name in lower case with non-letters turned into dashes (40 characters at most), a dash, and the "
        "first 6 characters of the SHA-1 of the file name. The browser also keeps a few view settings in localStorage: "
        "mode, style2, cstyle, bookCat, theme, themeDefault, voiceMode.")
    d.note("Backups", "<p>Copy the <code>data</code> folder to keep memories, chats, attached documents and the book index. "
           "Deleting <code>data\\library</code> only means books must be added again.</p>", "ok")


# =========================================================================== 19
def interface(d: Doc) -> None:
    d.section("The interface (ui\\index.html)", "interface")
    d.p("One file of about 2,300 lines: CSS at the top, the HTML layout, then JavaScript. No libraries, no build step.")
    d.table(["Part", "What it does"], [
        ["store", "Safe wrapper around localStorage (never breaks if storage is blocked)"],
        ["S", "The page's state: mode, style, cstyle (story/character), current chat, busy flag, status"],
        ["api(), toast()", "fetch helper with JSON, and the small pop-up messages"],
        ["markdown(), inline()", "Turns answers into HTML after escaping them: headings, lists, tables, code blocks, [n] citations"],
        ["send()", "Posts /api/chat and reads the SSE stream; updates the answer as tokens arrive; handles Stop"],
        ["renderSources(), addRunButtons(), parseQuiz(), renderQuiz(), saveStudyGuide()", "Sources bar, Run buttons for Python/Java, the interactive quiz and the printable study guide"],
        ["retry(), editUser(), showResend()", "Retry, Edit and Resend using the turn tags"],
        ["Voice", "Recording (WAV), speak(), live feed() while streaming, the Stop talking pill, Esc"],
        ["SelPop", "Highlight any text: Read aloud / Explain in detail"],
        ["Pics, Docs", "Pictures and documents attached to the message or chat"],
        ["loadBooks(), catOptions()", "Library page: grouped subject menus, Add buttons, time estimates, progress"],
        ["loadMemory(), loadModels(), loadPersonal(), applyWall()", "Memory, Models and Personalise pages, wallpaper"],
        ["Blobs", "The animated mascot drawn on canvas elements with class qblob"],
    ])
    d.sub("The Blob mascot")
    d.p("A soft, wobbly ball drawn 60 times a second. Its look moves smoothly toward targets that depend on the mode and style "
        "(each value eases from 0 to 1). Styles only dress the Blob in Offline and Online modes.")
    d.table(["Mode or style", "Look"], [
        ["Chat", "Default colours and a smile"], ["Offline", "Teal"], ["Online", "Pink"],
        ["Create", "Gold, with a masquerade mask"], ["Detailed (explain)", "Gold monocle on the right eye and a curly mustache"],
        ["Quick", "A flickering lightning bolt beside the head"], ["Code", "A white hacker faceplate with slit eyes and circuit lines"],
        ["Teach", "Round glasses and a tie"], ["Quiz", "A floating cube"], ["Voice mode", "Vibrates gently while listening or speaking"],
    ])
    d.sub("Keyboard")
    d.ul(["<kbd>Enter</kbd> sends, <kbd>Shift</kbd>+<kbd>Enter</kbd> makes a new line.", "<kbd>Esc</kbd> stops reading aloud and closes the highlight menu."])


# =========================================================================== 20
def settings(d: Doc, cfg: dict) -> None:
    d.section("Settings you can change (config.json)", "settings")
    d.p("Close QuantaKai, edit config.json, start it again.")
    meaning = {
        "app_name": "Name shown in the app and used in the instructions",
        "user_name": "What it calls you (a nickname on the Personalise page overrides it)",
        "ui_port": "The page's port", "chat_port": "Chat engine port", "embed_port": "Search engine port",
        "threads": "Processor threads for the chat engine and voice; \"auto\" = physical cores",
        "embed_threads": "Threads for the search engine",
        "gpu_layers": "Model layers on the graphics chip: 0 = processor only, 99 = all (Vulkan build only)",
        "context_window": "Tokens the model sees at once. Larger uses more RAM and slows the start of each answer",
        "max_model_gb": "Biggest model file allowed", "default_model": "Loaded on first start (later, your last choice is used)",
        "embedding_model": "The search model. If you change it, delete data\\library and add your books again",
        "chunk_words": "Passage size in words (re-add books after changing)", "chunk_overlap_words": "Overlap between passages",
        "study_top_k": "Passages given to each Offline answer",
        "study_min_score": "Passages below this meaning score are ignored (unless a strong keyword match). Raise it if answers use unrelated pages",
        "memory_top_k": "Facts given to each Chat reply", "memory_min_score": "How close a fact must be to be used",
        "auto_learn": "Starting value of the auto-learn switch (Memory page)",
        "run_timeout_seconds": "Longest a Run may take",
        "voice_model": "Whisper model file name", "tts_engine": "auto, kokoro, piper or windows",
        "tts_kokoro_voice": "Kokoro speaker number (3 = Heart)", "tts_voice": "Piper voice name",
        "tts_speed": "Piper length scale: lower = faster speech", "tts_expression": "Piper noise scale (pitch liveliness)",
        "tts_rhythm": "Piper noise_w (timing variation)", "tts_pause": "Silence between sentences (seconds)",
        "max_answer_tokens": "Longest answer per kind: chat, quick, explain, code, teach, quiz, story, character, voice",
        "temperature": "chat, study (Offline and Online), create",
    }
    rows = []
    for k, v in cfg.items():
        val = v if not isinstance(v, dict) else ", ".join(f"{a} {b}" for a, b in v.items())
        rows.append([c(k), E(str(val)), E(meaning.get(k, ""))])
    d.table(["Setting", "Value", "What it does"], rows)
    d.p("Extra keys the code understands if you add them: <code>voice_language</code> (Whisper language, default en), "
        "<code>tts_kokoro_fast</code> (false turns the kept-in-memory Kokoro off), <code>tts_kokoro_length_scale</code>, "
        "<code>tts_kokoro_max_slowness</code> (default 2.5), <code>tts_kokoro_chinese</code>.")


# =========================================================================== 21
def security(d: Doc) -> None:
    d.section("Security and safety", "security")
    d.table(["Risk", "How QuantaKai handles it"], [
        ["Other devices on the Wi-Fi", "The server binds to 127.0.0.1 only"],
        ["DNS rebinding", "Requests whose Host header is not 127.0.0.1:8000 or localhost:8000 get 403"],
        ["Other websites sending requests (CSRF)", "POST, PUT and DELETE with a foreign Origin header get 403; this protects /api/run, which executes code"],
        ["Model output containing HTML or scripts", "The page escapes all model text before turning Markdown into HTML"],
        ["Running code", "Only when you press Run; fresh temporary folder, isolated Python (-I), no input, 20-second limit, output capped"],
        ["Uploaded files", "Size limits (documents 18 MB, wallpaper 15 MB, any request body 32 MB, recordings 30 MB), wallpaper type checked by its first bytes, names cleaned before use"],
        ["Path tricks in ids", "Chat and document ids are stripped to letters, digits, _ and - before becoming file names"],
        ["Killing the wrong process", "A saved process number is only killed if its name is still llama-server (or python for the app)"],
        ["Leftover engines eating RAM", "A Windows Job Object kills the engines when the app's window closes"],
        ["Broken or oversized models", "Files must start with GGUF and be at most 5 GB to load"],
    ])
    d.p("An abliterated model will not refuse requests; the person using QuantaKai is responsible for what they ask it to do.")


# =========================================================================== 22
def tuning(d: Doc) -> None:
    d.section("Speed and tuning", "speed")
    d.p("Each answer shows its speed (for example \"18 s - 11.8 tokens/s\"). Measured on the Ryzen 5 3500U with "
        "Qwen2.5-3B Q4_K_M: about 11.8 tokens/s writing, about 22 tokens/s reading the prompt. A full Offline prompt "
        "(4 passages, about 900 tokens) therefore takes about 40 s before the first word; Chat starts in a few seconds "
        "thanks to <code>cache_prompt</code>.")
    d.table(["Change", "Effect"], [
        ["threads: try 4, 6, 8", "More is not always faster; physical cores (4) is usually best"],
        ["study_top_k 4 → 3", "About 25% less reading before an Offline answer starts"],
        ["chunk_words 180 → 140", "Shorter passages, faster reading (re-add books)"],
        ["A 2B model (Qwen3.5-2B)", "Roughly 1.5× faster, a little less careful"],
        ["Vulkan build + gpu_layers 99", "May help prompt reading on the Vega 8; test it: same question before and after"],
        ["Voice mode", "Answers capped at 220 tokens, spoken from the first sentence"],
        ["Piper instead of Kokoro", "Piper speaks almost instantly; Kokoro sounds better but uses more processor"],
    ])
    d.sub("Trying the graphics chip (Vulkan)")
    d.ul(["Download the <code>-bin-win-vulkan-x64.zip</code> from the same llama.cpp release.",
          "Rename <code>engine</code> to <code>engine-cpu</code>, make a new empty <code>engine</code> and unzip the Vulkan build into it.",
          "Set <code>\"gpu_layers\": 99</code>, restart, ask the same question; check logs\\chat-engine.log mentions Vulkan.",
          "Keep whichever is faster. To go back: delete the new engine folder, rename engine-cpu to engine, gpu_layers 0."], ordered=True)


# =========================================================================== 23
def models(d: Doc) -> None:
    d.section("Adding and switching models", "models")
    d.ul([
        "Any GGUF chat model of 5 GB or less works: put the .gguf in <code>models</code> (or <code>new stuff</code>) and it appears on the Models page and in the picker.",
        "Switching is manual: press Load or pick it at the top. Only one chat model is in memory at a time; the last one used loads at the next start.",
        "Good sizes for 16 GB RAM: 2B to 4B at Q4_K_M (1.3 to 2.5 GB). 7B/8B at Q4_K_M (4.4 to 4.9 GB) fits under the limit but is about half the speed.",
        "Abliterated versions (search Hugging Face for the model name + abliterated GGUF) are loaded the same way.",
        "Picture-capable models need their mmproj file in <code>models</code>, named so that it contains both <code>mmproj</code> and the model family, e.g. <code>Qwen3.5-2B-mmproj-F16.gguf</code> for <code>Qwen3.5-2B-Q4_K_M.gguf</code>. A mismatched mmproj crashes the engine.",
        "The search model (bge-small) and mmproj files never appear in the chat picker.",
    ])


# =========================================================================== 24
def troubleshooting(d: Doc) -> None:
    d.section("Troubleshooting", "trouble")
    d.table(["Problem", "Cause and fix"], [
        ["START.bat says \"not set up yet\"", "runtime\\python\\python.exe is missing: do Set up the portable Python, or run SETUP.bat"],
        ["\"Port 8000 is busy\"", "QuantaKai is already running, or another program uses 8000: run STOP.bat, or change ui_port"],
        ["ModuleNotFoundError: app", "python314._pth lacks the ..\\.. line, or START.bat is not in the QuantaKai folder"],
        ["ModuleNotFoundError: numpy / pymupdf", "The wheels were not unpacked into runtime\\python\\Lib\\site-packages (see Set up the portable Python)"],
        ["Model stuck on Loading / error", "Read logs\\chat-engine.log: missing DLL (re-extract the engine), not enough RAM (close programs or use a smaller model), bad file (re-download)"],
        ["\"Search model … is missing\"", "bge-small-en-v1.5-q8_0.gguf is not in models or has another name"],
        ["Book fails: no text found", "It is a scanned book (pictures of pages); OCR it first or attach pages as pictures"],
        ["Offline answers say \"couldn't find\" too often", "Lower study_min_score to 0.35, pick the subject by hand, or ask with the book's own words"],
        ["Online mode: could not reach the internet", "Check the connection; DuckDuckGo may also briefly block repeated searches"],
        ["Voice typing: not set up", "Run VOICE_SETUP.bat; check voice contains whisper-cli.exe and ggml-base.en.bin"],
        ["Kokoro missing from the voice menu", "voice must contain sherpa-onnx-offline-tts.exe and a folder with voices.bin + tokens.txt + model(.int8).onnx"],
        ["Kokoro very slow", "sherpa-onnx-c-api.dll is missing (not the shared build) or not v1.13.5; Piper is faster on 4 cores anyway"],
        ["Run: Java isn't installed", "Install a JDK 17+ and make sure java is on PATH"],
        ["Page looks old after an update", "Press Ctrl+F5 to reload without the cache"],
        ["Engines still running after closing", "Double-click STOP.bat"],
        ["verify_files.py says DIFFERENT", "Copy that file again with Save file (copy-paste can change quotes or spaces)"],
    ])


# =========================================================================== 25
def privacy(d: Doc) -> None:
    d.section("Privacy, backups and moving", "privacy")
    d.ul([
        "Everything you type, every book, memory and chat stays in the QuantaKai folder. Only Online mode sends your question (to DuckDuckGo) and fetches web pages.",
        "Memories can be read, edited and deleted on the Memory page; auto-learn can be switched off there.",
        "Back up the <code>data</code> folder. To move QuantaKai, close it and move the whole folder.",
        "Do not put books, data, models or voice files on GitHub (copyright, privacy and size). The repository's .gitignore keeps them out.",
    ])


# =========================================================================== 26
def links(d: Doc) -> None:
    d.section("Every link in this guide", "links")
    urls = [
        ("llama.cpp releases", "https://github.com/ggml-org/llama.cpp/releases"),
        ("Python for Windows", "https://www.python.org/downloads/windows/"),
        ("numpy files", "https://pypi.org/project/numpy/#files"),
        ("PyMuPDF files", "https://pypi.org/project/PyMuPDF/#files"),
        ("Qwen2.5-3B-Instruct GGUF", "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF"),
        ("bge-small-en-v1.5 GGUF", "https://huggingface.co/ggml-org/bge-small-en-v1.5-Q8_0-GGUF"),
        ("Qwen2.5-Coder-3B-Instruct GGUF", "https://huggingface.co/bartowski/Qwen2.5-Coder-3B-Instruct-GGUF"),
        ("Qwen3.5-2B GGUF (with mmproj)", "https://huggingface.co/unsloth/Qwen3.5-2B-GGUF"),
        ("whisper.cpp releases", "https://github.com/ggml-org/whisper.cpp/releases"),
        ("Whisper GGML models", "https://huggingface.co/ggerganov/whisper.cpp"),
        ("Piper 2023.11.14-2", "https://github.com/rhasspy/piper/releases/tag/2023.11.14-2"),
        ("Piper voices", "https://huggingface.co/rhasspy/piper-voices"),
        ("sherpa-onnx v1.13.5", "https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.5"),
        ("sherpa-onnx TTS models (Kokoro)", "https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models"),
        ("sherpa-onnx documentation", "https://k2-fsa.github.io/sherpa/onnx/"),
        ("Visual Studio Code", "https://code.visualstudio.com/"),
        ("Temurin JDK", "https://adoptium.net/"),
        ("Free Download Manager", "https://www.freedownloadmanager.org/"),
        ("DuckDuckGo HTML search (used by Online mode)", "https://html.duckduckgo.com/html/"),
        ("This project on GitHub", "https://github.com/Vamp1-hunid/My-Personal-Learning-Chatbot"),
    ]
    d.table(["What", "Link"], [[E(a), link(u)] for a, u in urls])
