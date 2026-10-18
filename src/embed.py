"""src/embed.py — Embedding stage.

Encodes every passage's text into a normalized float32 vector using the pinned
Sentence-Transformers model/revision from config/models.yaml, on CPU only, with
small batches controlled by config/hardware.yaml. Saves artifacts/embeddings.npy
and records embedding provenance in artifacts/embedding_meta.json.

Row order is a hard contract: row i of embeddings.npy must describe row i of
artifacts/passages.jsonl.

A full-corpus run takes hours on the target CPU-only laptop, so this stage:

* checkpoints after every block, and resumes from the checkpoint on re-run;
* can be split across processes (one per core pair) and merged, which roughly
  doubles throughput on the 4-core A8-7410. Row order is preserved because each
  shard owns a contiguous slice of passages.jsonl.

Usage:
    python src\\embed.py                          # single process (resumable)
    python src\\embed.py --shard 0 --shards 2     # first half
    python src\\embed.py --shard 1 --shards 2     # second half
    python src\\embed.py --merge                  # join shards -> embeddings.npy
"""
from __future__ import annotations

import os
import argparse
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

# Group id recorded in provenance. Must match the id in tests/ and data/schema.
GROUP_ID = "G014"

# Outer block size: how many passages are encoded between checkpoints. Chosen so
# a checkpoint costs a couple of minutes of work at ~2 chunks/s on the A8-7410.
CHECKPOINT_BLOCK = 512


def partial_path(shard: int | None) -> Path:
    name = "embeddings.partial.npy" if shard is None else f"embeddings.partial.{shard}.npy"
    return ROOT / "artifacts" / name


def load_rows() -> list[dict]:
    rows = [json.loads(line) for line in
            PASSAGES.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("passages.jsonl is empty. Run ingest.py + chunk.py first.")
    return rows


def shard_bounds(n: int, shard: int, shards: int) -> tuple[int, int]:
    """Contiguous, order-preserving split: shard k owns [lo, hi)."""
    lo = n * shard // shards
    hi = n * (shard + 1) // shards
    return lo, hi


def write_meta(vecs: np.ndarray, batch: int) -> None:
    emb_cfg = MODELS["embedding"]
    META.write_text(json.dumps({
        "model_name": emb_cfg["model_name"],
        "revision": emb_cfg["revision"],
        "dim": int(vecs.shape[1]),
        "num_passages": int(vecs.shape[0]),
        "normalized": emb_cfg["normalize"],
        "device": "cpu",
        "batch_size": batch,
        "group_id": GROUP_ID,
    }, indent=2), encoding="utf-8")


def run_shard(shard: int | None, shards: int) -> None:
    import torch
    from sentence_transformers import SentenceTransformer

    emb_cfg = MODELS["embedding"]
    batch = HARDWARE["batch_size"]
    # Allow an env override for benchmarking. HARDWARE['threads'] (2) is the
    # default for the A8-7410 low-power target. Higher values only help if the
    # encode loop actually saturates more than two threads.
    _env_thr = os.environ.get("OPT_TORCH_THREADS")
    threads = int(_env_thr) if _env_thr else HARDWARE["threads"]
    torch.set_num_threads(threads)  # keep each worker inside its share of cores

    rows = load_rows()
    lo, hi = (0, len(rows)) if shard is None else shard_bounds(len(rows), shard, shards)
    texts = [r["text"] for r in rows[lo:hi]]

    kwargs = {"device": "cpu"}
    rev = emb_cfg.get("revision")
    # Only pin a real 40-char commit hash; placeholder/absent revisions would
    # make the model download fail outright.
    if isinstance(rev, str) and len(rev) == 40 and \
            all(c in "0123456789abcdef" for c in rev.lower()):
        kwargs["revision"] = rev
    try:
        model = SentenceTransformer(emb_cfg["model_name"], **kwargs)
    except Exception as exc:
        # Offline-first (TASK 2): one plain line, never a hang/traceback wall.
        raise SystemExit("Embedding model not found in the local cache "
                         "(models/hf_cache) and we are offline. Run "
                         "SETUP_ONCE.bat once while online.") from exc
    dim = model.get_sentence_embedding_dimension()

    out_path = partial_path(shard)
    done = 0
    vecs = np.zeros((len(texts), dim), dtype="float32")
    if out_path.is_file():
        try:
            saved = np.load(out_path)
            if saved.ndim == 2 and saved.shape[1] == dim and saved.shape[0] <= len(texts):
                done = int(saved.shape[0])
                vecs[:done] = saved
                print(f"shard {shard}: resuming at {done}/{len(texts)}", flush=True)
            else:
                print(f"shard {shard}: checkpoint mismatch, restarting", flush=True)
        except Exception as exc:  # noqa: BLE001 — corrupt checkpoint must not be fatal
            print(f"shard {shard}: unreadable checkpoint ({type(exc).__name__}), restarting",
                  flush=True)

    label = f"shard {shard}/{shards}" if shard is not None else "single"
    for start in range(done, len(texts), CHECKPOINT_BLOCK):
        end = min(start + CHECKPOINT_BLOCK, len(texts))
        vecs[start:end] = model.encode(
            texts[start:end],
            batch_size=batch,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=emb_cfg["normalize"],  # unit norm; IP == cosine
        ).astype("float32")
        np.save(out_path, vecs[:end])
        print(f"  {label}: {end}/{len(texts)} embedded "
              f"(rows {lo}-{hi} of {len(rows)})", flush=True)

    if shard is None:
        np.save(EMB, vecs)
        out_path.unlink(missing_ok=True)
        write_meta(vecs, batch)
        print(f"embedded {vecs.shape[0]} passages dim={vecs.shape[1]} -> {EMB}")


def merge(shards: int) -> None:
    rows = load_rows()
    pieces = []
    for k in range(shards):
        path = partial_path(k)
        if not path.is_file():
            raise SystemExit(f"missing shard checkpoint: {path}")
        pieces.append(np.load(path))
    expected = [shard_bounds(len(rows), k, shards) for k in range(shards)]
    for k, (piece, (lo, hi)) in enumerate(zip(pieces, expected)):
        if piece.shape[0] != hi - lo:
            raise SystemExit(
                f"shard {k} incomplete: {piece.shape[0]} rows, expected {hi - lo}")
    vecs = np.concatenate(pieces, axis=0).astype("float32")
    if vecs.shape[0] != len(rows):
        raise SystemExit(f"merged {vecs.shape[0]} rows but passages.jsonl has {len(rows)}")
    np.save(EMB, vecs)
    for k in range(shards):
        partial_path(k).unlink(missing_ok=True)
    write_meta(vecs, HARDWARE["batch_size"])
    print(f"merged {shards} shards -> {EMB}  rows={vecs.shape[0]} dim={vecs.shape[1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shard", type=int, default=None)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    if args.merge:
        merge(args.shards)
        return
    if args.shard is not None and not (0 <= args.shard < args.shards):
        raise SystemExit(f"--shard must be in [0, {args.shards})")
    run_shard(args.shard, args.shards)


if __name__ == "__main__":
    main()
