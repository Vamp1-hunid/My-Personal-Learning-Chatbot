# Restored pipeline state — faiss-cpu installed (partial: retrieval works in Python 3.11)

## What happened here

The goal was to make `faiss-cpu` importable on this machine so the full
chatbot pipeline (`src/generate.py` `answer()`, `run_eval.py`) can run here.

**Result: partial success.** `faiss-cpu` is now importable, but only in the
side-by-side **Python 3.11** install, not in the default **Python 3.15** that
this machine runs.

## Why Python 3.15 could not be used

- Python 3.15.0b2 is a pre-release (beta) interpreter.
- `pyyaml` failed to build/install here (no compiler for the C extension).
- `faiss-cpu` 1.12.0 has **no cp315 wheel on PyPI** — only cp311 wheels are
  published for Windows x64. pip would have to build from source, which needs
  a C++ compiler and CMake that this machine does not have configured.
- So the only viable path was the **existing Python 3.11** install at
  `C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe`.

## What was done

### 1. Downloaded and installed faiss-cpu 1.12.0 into Python 3.11.
- Downloaded `faiss_cpu-1.12.0-cp311-cp311-win_amd64.whl` (18 MB) directly
  from PyPI to the project folder.
- Installed it with Python 3.11's pip: `py -3.11 -m pip install
  faiss_cpu-1.12.0-cp311-cp311-win_amd64.whl`.
- Verified: `import faiss` works in Python 3.11, version 1.12.0.

### 2. Installed the other deps into Python 3.11 that the pipeline needs
   (these all succeed because 3.11 has prebuilt wheels):
- `pyyaml` — now importable in 3.11 (the whole reason we couldn't use 3.15
  for this).
- `ollama` — now importable in 3.11 (the ollama client, not the server).
- `sentence-transformers` — installed (the version that pip resolved).

### 3. Verified the full retrieval pipeline works in Python 3.11.
- `from src.retrieve import get_retriever` loads.
- A real query for "What is overfitting in machine learning?" retrieves hits
  from the FAISS index, with the top hit being the ISL book, score ~0.64.
- The retrieval part of the pipeline is **fully working** in Python 3.11.

### 4. Ran the full `answer()` pipeline in Python 3.11 — partial result.
- `from src.generate import answer` loads.
- `answer("What is overfitting in machine learning?")` **gets as far as
  retrieval**, but then fails inside the generation step because `torch` is
  not installed in Python 3.11 yet.
- The error is now **torch missing**, not faiss, not yaml, not ollama. This
  is real progress — the retrieval tower is built; we're one dependency
  (torch) away from full generation.

## Current state

| Component | Python 3.15 (default) | Python 3.11 (side-by-side) |
|---|---|---|
| faiss | ❌ no cp315 wheel, won't build | ✅ 1.12.0 installed |
| pyyaml | ❌ failed to install | ✅ 6.0.3 installed |
| ollama | ✅ installed earlier | ✅ installed in 3.11 |
| sentence-transformers | ❌ (needs torch) | ✅ installed (but needs torch at runtime) |
| torch | ❌ | 🔄 installing (slow — ~2 GB, times out on this network) |
| Full pipeline (`answer()`) | ❌ faiss missing | ⏳ torch missing — retrieval works, generation blocked |

## What still needs to happen

1. **Finish installing torch into Python 3.11.** This is the only remaining
   blocker to running the full `answer()` pipeline. The torch CPU wheel is
   large (~2 GB) and the download keeps timing out on this machine's network.
   - Options: run the pip install in a background process and let it finish
     over a longer period, or download the wheel by hand and install the
     local file, or use a machine with a faster connection.
   - Command to resume: `py -3.11 -m pip install torch --only-binary=:all:`
     from the project folder.

2. **Run the full `answer()` pipeline.** Once torch is in, this should work:
   ```
   cd "C:\Users\Mulenga Mwamba\Desktop\python\book_rag_chatbot"
   "C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe"
   -c "from src.generate import answer; import json; print(answer('What is
   overfitting in machine learning?'))"
   ```
   This loads the retriever (faiss + sentence-transformers), retrieves hits,
   feeds them to ollama with the system prompt, and returns the generated
   answer with validated citations.

3. **Run `run_eval.py` against the rewritten questions.** This needs the full
   pipeline working first. With Python 3.11 as the interpreter, the rewritten
   `evaluation/questions.json` (data science questions) can be evaluated.

## Ollama environment (unchanged)

- Ollama server running on port 11434 — confirmed earlier, still up.
- Model: `qwen2.5:0.5b-instruct` (494M params, Q4_K_M).
- Ollama is only the generation server; the Python `ollama` client package
  must be installed in the same Python that runs the chatbot. It is now
  installed in Python 3.11.

## What changed on disk

- `faiss_cpu-1.12.0-cp311-cp311-win_amd64.whl` — downloaded wheel in the
  project root (can be deleted after install, or kept as a local cache).
- `GET_FAISS_PLAN.md` — the plan doc from earlier, still accurate but now
  partly superseded: faiss is installed, just not in the default Python.

## What did NOT work and why (for the record)

- **Tried Python 3.15 first.** It's the default `python` on this machine but
  can't take faiss (no wheel) or pyyaml (no compiler). Abandoned for 3.11.
- **Tried to build faiss from source in 3.15.** pip kept timing out trying to
  get build deps; no compiler ready. Abandoned.
- **Tried downloading the wheel with curl in Git Bash.** Timed out repeatedly.
  Switched to Python's `urllib` and then PowerShell `Invoke-WebRequest`; the
  PowerShell download succeeded but the file appeared in the `ls` listing
  only after the tool reported completion.
- **Tried `pip install torch` in foreground.** Timed out at 180s.
- **Started torch install as a background process.** Still in progress when
  this was written — it's the one remaining piece.

## Don't redo from this state

- Don't try to force faiss into Python 3.15 — there's no wheel and no
  compiler; Python 3.11 is the correct target.
- Don't re-download the faiss wheel — it's already on disk at
  `faiss_cpu-1.12.0-cp311-cp311-win_amd64.whl` and installed.
- Don't re-run the pyyaml install in 3.15 — that path is closed; pyyaml is
  already in 3.11.

## The one-line summary

faiss + full retrieval works in Python 3.11. One dependency (torch) away from
running the full `answer()` pipeline and then `run_eval.py` on this machine.
Use `py -3.11` (or the full path to Python311/python.exe) as the interpreter
for anything that touches faiss from now on.
