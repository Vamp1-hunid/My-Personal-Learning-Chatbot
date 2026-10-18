"""src/index.py — Indexing stage.

Builds a FAISS CPU index (IndexFlatIP over normalized float32 vectors) from
artifacts/embeddings.npy in the SAME row order as artifacts/passages.jsonl.
Writes artifacts/index.faiss plus artifacts/index_config.json recording
embedding model, revision, dimension, index type, chunk count.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import faiss
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.runtime_probe import write_build_manifest  # stdlib-only helper
HARDWARE = yaml.safe_load((ROOT / "config" / "hardware.yaml").read_text(encoding="utf-8"))
MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
EMB = ROOT / "artifacts" / "embeddings.npy"
PASSAGES = ROOT / "artifacts" / "passages.jsonl"
IDX = ROOT / "artifacts" / "index.faiss"
META = ROOT / "artifacts" / "index_config.json"

faiss.omp_set_num_threads(HARDWARE["threads_faiss"])


def main() -> None:
    if not EMB.is_file():
        raise SystemExit("embeddings.npy missing. Run embed.py first.")
    vecs = np.load(EMB)
    n_rows = len(np.load(EMB, mmap_mode="r"))
    if not PASSAGES.is_file() or \
       sum(1 for _ in PASSAGES.open(encoding="utf-8")) != n_rows:
        raise SystemExit(
            "passages.jsonl missing or row count != embeddings. Re-run embed.py."
        )

    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)  # exact inner product == cosine after normalisation
    index.add(vecs)
    faiss.write_index(index, str(IDX))

    meta = {
        "embedding_model": MODELS["embedding"]["model_name"],
        "embedding_revision": MODELS["embedding"]["revision"],
        "dim": dim,
        "index_type": "IndexFlatIP",
        "normalized": True,
        "num_chunks": int(vecs.shape[0]),
        "group_id": "G014",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "metric_note": "vectors are unit-normalized on CPU; IP value in [-1, 1]",
        "stored_passages": "artifacts/passages.jsonl  (row i == vector i; NEVER reorder one without the other)",
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # TASK 3 staleness guard: sha256 manifest of the three build products.
    # src/retrieve.py verifies it on every load — a silently stale index would
    # produce plausible-but-wrong citations, the worst failure for this project.
    mf = write_build_manifest(IDX.parent, MODELS["embedding"],
                              num_chunks=int(vecs.shape[0]), group_id="G014")
    print(f"build manifest written -> {mf}")
    print(f"faiss index built: {IDX}  rows={int(vecs.shape[0])} dim={dim}")



if __name__ == "__main__":
    main()
