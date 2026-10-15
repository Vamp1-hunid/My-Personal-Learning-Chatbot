# Final Consolidated Deliverable (combined model outputs + hardware-tailored plan)

The final deliverable is assembled as **`project/final_plan.html`** (single
self-contained HTML file, openable locally, no internet needed — TOC, search,
collapsible sections, dark-mode toggle, print styling). It merges the four
candidate outputs (2 PDFs + 2 HTMLs).

## Hardware-derived design constraints enforced in code and configs
- CPU-only (no CUDA, no DML, no Vulkan); pinned torch CPU wheel.
- Threads = 2 everywhere (OpenMP, MKL, FAISS, generation) via config/hardware.yaml.
- Memory budget: 6 GB warn / 7 GB hard; auto-downgrade ladder (Tier 0–4).
- HDD-friendly: passages fully in JSONL with sequential reads, no random index lookups.
- Generation: tiny quantized model only (Qwen2.5-0.5B-instruct Q4) via Ollama CPU mode;
  max_new_tokens 96; ctx 1024; temperature 0.

## Citation / abstention contract (implemented)
- `src/retrieve.py` — exact required `retrieve(question, top_k)`.
- `src/generate.py` — JSON with exactly `answer`/`sources`/`insufficient_evidence`
  (+ optional `conflicts`).
- `src/citations.py` — re-validates every cited chunk_id against stored passages;
  rejects invented sources and book/page drift.
- `src/answer_schema.py` — payload validation; last resort = honest abstention.
- Early abstention when top score < 0.35 (`config/retrieval.yaml`), tuned on validation
  split only.

## Primary stack choices
- Python 3.11.x (doctor rejects < 3.10 or > 3.12 with download note).
- PyMuPDF 1.24.14 for extraction; Tesseract OCR only when processing_status='needs_ocr'.
- FAISS CPU IndexFlatIP over normalized MiniLM-L6-v2 vectors;
  page-first chunking 220 words + 50 overlap.
- PDF page vs printed page preserved; edition metadata retained from manifest.

## Files on disk under `project/`
- config/{models,chunking,retrieval,hardware,memory}.yaml
- data/schema/passage.json, data/book_manifest.template.json
- src/{__init__,doctor,ingest,chunk,embed,index,retrieve,generate,citations,
  answer_schema,cli,app,memwatch}.py
- tests/{conftest,test_ingest,test_retrieve,test_citations,test_answer_format,
  test_abstention}.py
- evaluation/{run_eval.py,questions.template.json}
- artifacts/passages.example.jsonl
- README.md, requirements.txt, .gitignore, .env.example

## Verification performed in this sandbox
- AST parse of all src / tests / evaluation files: OK.
- Citation extraction / invented-source rejection / page-drift rejection: OK.
- answer_schema.validate_answer + is_contradictory: OK.
- Full faiss/torch build and index build are left to run on the target hardware
  (`doctor.py` first, then ingest → chunk → embed → index).
- `tests.test_retrieve` skips if faiss / sentence-transformers absent.
- `tests.test_ingest` enforces the real 15+ book manifest before final submission.
- pytest was NOT executed in this sandbox (pytest not installed); run
  `python -m pytest tests/ -v` on the target hardware as part of final acceptance.
- doctor.py was not executed here either (no psutil in sandbox; ctypes fallback unverified
  against this actual HP Pavilion). Run `python src/doctor.py` first, as documented.
