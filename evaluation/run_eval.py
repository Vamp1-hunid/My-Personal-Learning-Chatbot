"""evaluation/run_eval.py — automated evaluation.

Reads evaluation/questions.json (reviewed question set) and produces:
  evaluation/report.json   — machine-readable metrics
  evaluation/report.md     — human-readable summary

Run with --split validation during tuning. --split test is a final-once
activity. Tuning against the test split invalidates your evaluation.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import psutil

from src.generate import answer
from src.retrieve import retrieve

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "evaluation" / "questions.json"
PASSAGES = ROOT / "artifacts" / "passages.jsonl"


def load_passage_ids():
    ids = set()
    with PASSAGES.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)["chunk_id"])
    return ids


def run(split: str) -> dict:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    subset = [q for q in questions
              if q.get("split") == split and q.get("review_status") == "reviewed"]
    if not subset:
        raise SystemExit(f"No reviewed questions with split == '{split}'.")

    store = load_passage_ids()
    res = {
        "split": split,
        "num_questions": len(subset),
        "recall_at_5": 0,
        "citation_validity": 0,
        "abstention_accuracy": 0,
        "answerable": 0,
        "unanswerable": 0,
        "latency_mean_s": 0.0,
        "peak_ram_gb": round(psutil.Process().memory_info().rss / (1 << 30), 3),
    }

    n_recall = n_cit = n_abs = n_ans = n_unans = 0
    latencies = []
    per_q = []

    for q in subset:
        t0 = time.perf_counter()
        payload = answer(q["question"])
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        answerable = q.get("answerable", True)
        cited_ids = {s["chunk_id"] for s in payload.get("sources", [])}
        valid_citation = all(cid in store for cid in cited_ids)

        row = {
            "id": q["question_id"],
            "question": q["question"],
            "insufficient_evidence": payload["insufficient_evidence"],
            "cited_ids": sorted(cited_ids),
            "expected_ids": q.get("expected_chunk_ids", []),
            "latency_s": round(elapsed, 3),
            "citation_valid": valid_citation,
        }
        # Recall@5 (a: expected chunk-id returned inside top-5 retrieval result)
        if answerable:
            n_ans += 1
            hits = retrieve(q["question"], top_k=5)
            hit_ids = {h["chunk_id"] for h in hits}
            row["recall_hit"] = bool(set(q.get("expected_chunk_ids", [])) & hit_ids)
            if row["recall_hit"]:
                n_recall += 1
        else:
            n_unans += 1
            row["abstention_correct"] = payload["insufficient_evidence"] in (True,)
            if row["abstention_correct"]:
                n_abs += 1

        if valid_citation:
            n_cit += 1
        per_q.append(row)

    res.update({
        "answerable": n_ans,
        "unanswerable": n_unans,
        "recall_at_5": round((n_recall / n_ans) * 100, 2) if n_ans else None,
        "citation_validity": round((n_cit / len(subset)) * 100, 2) if subset else 0,
        "abstention_accuracy": round((n_abs / n_unans) * 100, 2) if n_unans else None,
        "latency_mean_s": round(sum(latencies) / len(latencies), 2),
    })
    res["per_question"] = per_q

    out_json = ROOT / "evaluation" / "report.json"
    out_md = ROOT / "evaluation" / "report.md"
    out_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(
        f"# Evaluation Report — split `{split}`\n\n"
        f"- Questions reviewed: {res['num_questions']}\n"
        f"- Answerable questions: {res['answerable']}\n"
        f"- Unanswerable questions: {res['unanswerable']}\n"
        f"- **Recall@5**: {res['recall_at_5']}%\n"
        f"- **Citation validity**: {res['citation_validity']}%\n"
        f"- **Abstention accuracy**: {res['abstention_accuracy']}%\n"
        f"- Mean latency: {res['latency_mean_s']} s\n"
        f"- Peak RAM of eval process: {res['peak_ram_gb']} GB\n"
        f"\n_Generated automatically; human-reviewed test set results are added manually._\n",
        encoding="utf-8")
    print(f"wrote {out_json}\nwrote {out_md}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["validation", "test"], default="validation")
    args = ap.parse_args()
    run(args.split)
