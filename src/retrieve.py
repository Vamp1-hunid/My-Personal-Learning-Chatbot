"""src/retrieve.py — Retrieval stage (shared integration interface).

Required assignment contract:

    def retrieve(question: str, top_k: int = 5) -> list:
        \"\"\"
        Return passages with text, score, book_id, title, page, and chunk_id.
        \"\"\"

Loads FAISS index and the parallel passages.jsonl (same row order), encodes the
question with the SAME pinned embedding model used to build the index, then
returns the top-k passages with full metadata + cosine score.
"""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
EMB_CFG = MODELS["embedding"]
IDX = ROOT / "artifacts" / "index.faiss"
PASSAGES = ROOT / "artifacts" / "passages.jsonl"

# Example corpus used when the real book index has not been built yet (fresh
# clone, no PDFs). Keeps the chatbot runnable end-to-end out of the box.
EXAMPLE_PASSAGES = ROOT / "data" / "examples" / "passages.example.jsonl"


def _active_paths() -> tuple[Path, Path]:
    """Return (index, passages) paths to use: real artifacts if built,
    otherwise the bundled example corpus."""
    if IDX.is_file() and PASSAGES.is_file():
        return IDX, PASSAGES
    if EXAMPLE_PASSAGES.is_file():
        return None, EXAMPLE_PASSAGES  # index built on the fly at load time
    return IDX, PASSAGES


class Retriever:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        kwargs = {"device": "cpu"}
        rev = EMB_CFG.get("revision")
        # Only pin the revision when it is a real commit hash; placeholder or
        # absent values would make the download fail outright.
        if isinstance(rev, str) and len(rev) == 40 and \
                all(c in "0123456789abcdef" for c in rev.lower()):
            kwargs["revision"] = rev
        self.model = SentenceTransformer(EMB_CFG["model_name"], **kwargs)

        idx_path, passages_path = _active_paths()
        self.passages = [json.loads(line) for line in
                         passages_path.read_text(encoding="utf-8").splitlines()
                         if line.strip()]
        if not self.passages:
            raise SystemExit(f"no passages found in {passages_path}; "
                             "run ingest.py + chunk.py first.")
        if idx_path is None:
            # Example corpus (real book index not built yet): encode the
            # example passages and hold a small in-memory index.
            vecs = self.model.encode([p["text"] for p in self.passages],
                                     convert_to_numpy=True,
                                     normalize_embeddings=True).astype("float32")
            self.index = faiss.IndexFlatIP(vecs.shape[1])
            self.index.add(vecs)
        else:
            self.index = faiss.read_index(str(idx_path))
            assert len(self.passages) == self.index.ntotal, \
                "passages.jsonl and index.faiss row counts differ; rebuild embed+index."

    def retrieve(self, question: str, top_k: int = 5) -> list:
        """Return passages with text, score, book_id, title, page, and chunk_id."""
        if not question or not question.strip():
            return []
        q = self.model.encode([question.strip()],
                              convert_to_numpy=True,
                              normalize_embeddings=True).astype("float32")
        k = max(1, min(top_k, self.index.ntotal))
        scores, ids = self.index.search(q, k)
        out = []
        for score, i in zip(scores[0], ids[0]):
            if int(i) < 0:
                continue
            p = self.passages[int(i)]
            out.append({
                "text": p["text"],
                "score": float(score),
                "book_id": p["book_id"],
                "title": p["title"],
                "page": p["page"],
                "chunk_id": p["chunk_id"],
                "edition": p.get("edition", ""),
            })
        return out


_singleton = None
def get_retriever() -> Retriever:
    """Lazy singleton to keep memory low when embed/index not needed yet."""
    global _singleton
    if _singleton is None:
        _singleton = Retriever()
    return _singleton


# Assignment-grade convenience: this is the function other groups / the router call.
def retrieve(question: str, top_k: int = 5) -> list:
    return get_retriever().retrieve(question, top_k)
