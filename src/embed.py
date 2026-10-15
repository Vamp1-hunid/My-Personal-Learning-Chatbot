"""src/embed.py — Embedding stage.

Encodes every passage's text into a normalized float32 vector using the pinned
Sentence-Transformers model/revision from config/models.yaml, on CPU only, with
small batches controlled by config/hardware.yaml. Saves artifacts/embeddings.npy
and records embedding provenance in artifacts/embedding_meta.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
HARDWARE = yaml.safe_load((ROOT / "config" / "hardware.yaml").read_text(encoding="utf-8"))
PASSAGES = ROOT / "artifacts" / "passages.jsonl"
EMB = ROOT / "artifacts" / "embeddings.npy"
META = ROOT / "artifacts" / "embedding_meta.json"


def main() -> None:
    from sentence_transformers import SentenceTransformer  # cpu-only

    rows = [json.loads(line) for line in
            PASSAGES.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("passages.jsonl is empty. Run ingest.py + chunk.py first.")

    emb_cfg = MODELS["embedding"]
    model = SentenceTransformer(
        emb_cfg["model_name"],
        revision=emb_cfg["revision"],
        device="cpu",
    )
    texts = [r["text"] for r in rows]

    batch = HARDWARE["batch_size"]
    vecs = model.encode(
        texts,
        batch_size=batch,
        convert_to_numpy=True,
        show_progress_bar=True,
        normalize_embeddings=emb_cfg["normalize"],  # unit norm; IP == cosine
    ).astype("float32")

    np.save(EMB, vecs)
    meta = {
        "model_name": emb_cfg["model_name"],
        "revision": emb_cfg["revision"],
        "dim": int(vecs.shape[1]),
        "num_passages": int(vecs.shape[0]),
        "normalized": emb_cfg["normalize"],
        "device": "cpu",
        "batch_size": batch,
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"embedded {vecs.shape[0]} passages dim={vecs.shape[1]} -> {EMB}")


if __name__ == "__main__":
    main()
