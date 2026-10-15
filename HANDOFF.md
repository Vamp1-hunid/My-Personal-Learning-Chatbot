# HANDOFF — book_rag_chatbot (local repo, desktop copy)

Repo state: **36+ commits, single-file flow-control history, clean working tree.**
Identity: repo-local `Mulenga Mwamba <mulenga.mwamba.report@gmail.com>`
→ replace before any push: `git config user.email "your-real@email"`

## What is verified in this copy (pre-push validation, no hardware needed)
- All **23 Python files** AST-parse clean (src + tests + evaluation).
- `evaluation/questions.json`: 40 questions, 19 validation / 21 test, category mix
  10 direct / 6 reasoning / 6 numerical / 6 cross-book / 8 unanswerable / 4 citation-check.
- Configs match the A8-7410 rules: chunk 160/30, threads 2, tier0 ctx 1024,
  6 GB warn / 7 GB hard memory thresholds.
- `.gitignore` proven to block `artifacts/` (the example rows were re-homed to
  `data/examples/` when the ignore system refused them).
- `pytest` and `streamlit` were NOT executed here (not installed in the build
  sandbox) — see "run on your laptop" below.

## Run on your laptop, in this exact order (PowerShell, from repo root)
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest tests/ -v          # 1. expect: collect, unit tests green
python src\doctor.py                # 2. hardware + package report
python src\ingest.py                # 3. after dropping 15+ PDFs into data\books\
python src\chunk.py                 # 4.
python src\embed.py                 # 5. 10-40 min once
python src\index.py                 # 6.
python -m src.cli "What is Ohm's law?" --json   # decreta baseline in extractive mode
python -m streamlit run src/app.py  # 7. demo UI (memory-safe)
python evaluation\run_eval.py validation        # 8. tune here ONLY
python evaluation\run_eval.py test              # 9. once, at the end
```

## Fill before submission
1. `README.md`: group id (G001 → yours), assigned subject, team roles.
2. `evaluation/questions.json`: retarget `expected_chunk_ids`, write real
   `reference_answer`s, flip `review_status` to `reviewed` after a teammate
   reads the target page.
3. `data/book_manifest.json` (from the template): 15+ real entries.
4. `config/models.yaml`: pin the coordinator-approved embedding revision
   (doctor warns while a placeholder).
5. Drop the llama.cpp **avx** build (NOT avx2) into `tools\llama.cpp\` and a
   Qwen2.5-0.5B Q4_K_M GGUF into `models\` — both git-ignored.

## Do not
- Commit PDFs, extracted text, `artifacts\`, `models\`, `tools\`, `.env`.
- Tune on the test split; show unvalidated citations; run embed + generate at once.
