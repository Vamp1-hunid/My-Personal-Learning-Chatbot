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
import sys
import warnings
from pathlib import Path

import faiss
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODELS = yaml.safe_load((ROOT / "config" / "models.yaml").read_text(encoding="utf-8"))
EMB_CFG = MODELS["embedding"]
IDX = ROOT / "artifacts" / "index.faiss"
PASSAGES = ROOT / "artifacts" / "passages.jsonl"


class IndexOutOfSyncError(RuntimeError):
    """Raised when artifacts/BUILD_MANIFEST.json does not match the files on disk.

    A stale index silently returns WRONG passages for a question, which produces
    plausible-but-wrong citations — the worst possible failure for a graded,
    citation-grounded chatbot. We refuse to serve rather than guess.
    """


def _verify_build_manifest() -> None:
    """TASK 3 staleness guard, run once per process on real-artifact load.

    ok       -> continue silently
    absent   -> warn once (older build), continue
    mismatch -> raise IndexOutOfSyncError with a clear rebuild instruction
    """
    global _manifest_checked
    if _manifest_checked:
        return
    from launcher.runtime_probe import verify_build_manifest
    status, msg = verify_build_manifest(ROOT / "artifacts")
    _manifest_checked = True
    if status == "mismatch":
        raise IndexOutOfSyncError(msg)
    if status == "absent":
        warnings.warn(msg, RuntimeWarning)


_manifest_checked = False

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
        try:
            self.model = SentenceTransformer(EMB_CFG["model_name"], **kwargs)
        except Exception as exc:
            # Offline-first (TASK 2): one plain line, never a hang/traceback wall.
            raise SystemExit(
                "Embedding model not found in the local cache (models/hf_cache) "
                "and we are offline. Run SETUP_ONCE.bat once while online.") from exc

        idx_path, passages_path = _active_paths()
        if idx_path is not None:
            _verify_build_manifest()   # TASK 3: refuse to serve a stale index
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
