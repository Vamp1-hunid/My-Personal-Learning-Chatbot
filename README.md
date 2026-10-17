# Book-Grounded RAG Chatbot — Group G014

A Retrieval-Augmented Generation (RAG) chatbot grounded in **15+ assigned books**:
retrieves passages (FAISS, CPU), generates short answers with a tiny local Q4-quantized
model (Qwen2.5-0.5B) served over a separate llama.cpp `llama-server` HTTP process),
cites page-accurate
sources, and **refuses** (abstains) when the corpus cannot support an answer.

Everything runs **CPU-only** on the target laptop: HP Pavilion, AMD A8-7410,
12 GB RAM (10.9 usable), 1.82 TB HDD, Windows 10/11 64-bit, no admin rights.
Full implementation guide: `docs/final_plan.html` (open in any browser — 49 sections).

## One-time install (PowerShell, from this folder)

```powershell
py -0p                                   # confirm Python 3.11 exists; installed for user only
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1             # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python src\doctor.py                     # hardware + package compatibility check
```

Session env (every new window, weak-CPU friendly):
```powershell
$env:OMP_NUM_THREADS="2"; $env:MKL_NUM_THREADS="2"
```

## Downloads (nothing on the critical path needs admin)

| Artifact | Where | Then |
|---|---|---|
| llama.cpp Windows zip tagged **avx** (NOT avx2/avx512) | github.com/ggml-org/llama.cpp/releases | unzip into `tools\llama.cpp\` |
| Qwen2.5-0.5B-Instruct Q4_K_M GGUF | official Qwen repo on Hugging Face | save into `models\`, record SHA-256 in `config\models.yaml` |
| Embedding model `all-MiniLM-L6-v2` + **coordinator-pinned revision** | auto-downloaded on first embed run, cached in `%USERPROFILE%\.cache\huggingface` | pin revision in `config\models.yaml` (doctor warns while a placeholder) |
| (only if a book is scanned) Tesseract UB-Mannheim + `pip install ocrmypdf` | per-user install | OCR one book at a time to `data\cache\ocr\` |

**Page convention:** every citation page number is the **PDF page index (1-based)**,
not the printed book page. Stated here AND in every report.

## Build the index (once per corpus change)

```powershell
python src\ingest.py     # PDFs -> page cache, flags scanned books for OCR
python src\chunk.py      # 160 words / 30 overlap, per page -> data\passages\passages.jsonl
python src\embed.py      # MiniLM, batch 4 -> artifacts\embeddings.npy   (10-40 min; offline)
python src\index.py      # FAISS IndexFlatIP -> artifacts\index.faiss + index_config.json
```

## Ask questions

CLI (primary):
```powershell
python -m src.cli "State Ohm's law exactly as the books define it."
python -m src.cli --json --show-sources "Compare the two books' definitions of EMF."
```

Streamlit demo (memory-safe: bounded 8-turn log, live RAM stats, abstention banners):
```powershell
python -m streamlit run src/app.py
```
The demo shows **retrieved passages** (with cosine score bars), **validated citations**
(expandable to the exact supporting text), **abstention with reasons**, latency,
answer mode, and free-RAM / process-RSS against the 6 GB warn / 7 GB hard caps.
Optional separate generation process (unloads with `Stop-Process -Name llama-server`):
```powershell
Start-Process tools\llama.cpp\llama-server.exe -ArgumentList "-m models\qwen2.5-0.5b-instruct-q4_k_m.gguf -c 1024 -t 2 --port 8081 --host 127.0.0.1"
```

## Tests & evaluation

```powershell
python -m pytest tests/ -v                                       # all tests green before demoing
python evaluation\run_eval.py validation                          # tune only here (min_score, top_k, chunk size)
python evaluation\run_eval.py test                                # ONCE at the end; report honest numbers
```
Question set: `evaluation\questions.json` — 40 balanced questions
(10 direct / 6 reasoning / 6 numerical / 6 cross-book / 8 unanswerable / 4 citation-check),
≈40% validation / 60% test, **split before tuning**. Human-review columns are filled
row by row in `report_validation.json` / `report_test.json`.

## The three integration contracts (130-group platform)

1. **Passage schema** — see `data/schema/passage.json`; `chunk_id` = `G###_BOOK_###_P#_C##`,
   row *i* of `embeddings.npy` ↔ line *i* of `data/passages/passages.jsonl`, never reorder one alone.
2. **Retrieval interface** — `retrieve(question: str, top_k: int = 5) -> list[dict]` in `src\retrieve.py`
   returning `{text, score, book_id, title, page, chunk_id, edition}`.
3. **Answer JSON** — exactly `{"answer": str, "sources": [{book_id, page, chunk_id}], "insufficient_evidence": bool}`
   built via `answer_schema.to_contract_payload()`; extension keys (`mode`, `conflicts`) are local-only.

## Repo layout

```
src\          doctor ingest chunk embed index retrieve generate citations answer_schema cli app memwatch
config\       models.yaml chunking.yaml retrieval.yaml hardware.yaml memory.yaml
data\         books\ (PRIVATE) cache\ passages\ book_manifest.json schema\
artifacts\    embeddings.npy index.faiss index_config.json passages.example.jsonl
tests\        test_ingest retrieve citations answer_format abstention chunk
evaluation\   questions.json run_eval.py template_report.md
docs\         final_plan.html (full build guide)   SUMMARY.md
tools\        llama.cpp\ (git-ignored)     models\ (git-ignored)
```

## Safety rules (non-negotiable)

- **Never commit**: PDFs, extracted/passages text, `artifacts\`, `models\`, `tools\`, `.env`.
  (`.gitignore` enforces; still run the secrets audit before each push.)
- Contract keys stay exactly three for the router; open-source/tunable internals differ per group.
- Memory-attendance is a request, not a right: < 6 GB free ⇒ tier-0 (top_k 3, ctx 1024);
  > 6 GB process RSS ⇒ warn; ≥ 7 GB ⇒ stop and drop a tier.
- Never tune on the test split; never show an unvalidated citation; never average out conflicts.
- Hosted generation (Tier 2) runs **only** with written approval; keys live in `.env`, never committed.

## Team roles

- **Intake/Ops** — books, manifest, permissions, OCR (§16–17 of the guide).
- **Indexing** — ingest → chunk → embed → index correctness and rebuild scripts.
- **Generation** — llama-server ops, prompt template, fallback chain.
- **Evaluation** — questions.json review, human scoring, report numbers.
- **Integration/QA** — schema/interface checks, secrets audit, submission checklist.

## Current status

See `HANDOFF.md` for the exact next steps and the one-pass verification status of this copy.
