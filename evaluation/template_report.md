# Evaluation report: Group G014, subject Data Science

Environment: HP Pavilion, AMD A8-7410, 12 GB RAM, HDD, Windows __, Python 3.11.__, tier __, threads __
Embedding: model ____ revision ____ | Index: IndexFlatIP, ____ chunks
Generation: ____ Q4_K_M, ctx ____, max_new_tokens ____ · page convention: PDF page (1-based)

## Document processing
Books processed ___/15 · failed pages ___ · OCR problems ___ · metadata complete ___%

## Machine metrics (from run_eval.py — no claims, just numbers)
| Metric | Validation | Test |
|---|---|---|
| Recall@5 | ____% | ____% |
| Citation validity | 100% (code-enforced) | 100% |
| Abstention accuracy | ____% | ____% |
| Mean latency | ____ s | ____ s |
| Peak RAM (incl. llama-server) | ____ GB | ____ GB |

## Human review (fill row by row from report_*.json)
Correct ____% · partial ____% · wrong ____% · citation-supports-claim ____% · groundedness ____%
False abstentions on answerable questions ____/____

## Freeze record
min_score chosen on validation: ____ · top_k: ____ · chunk words: 160 / overlap 30
Validation-tuning freeze date: ____ · Test split run ONCE on: ____

## Failure analysis + limitations
____

## Leakage controls
How the split was made (before any tuning): ____ · near-duplicate check: ____
