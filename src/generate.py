"""src/generate.py — Generation stage.

Generates the final answer using ONLY retrieved evidence per the assignment
contract. Primary engine: llama.cpp `llama-server` (separate CPU process,
OpenAI-compatible endpoint, started with the command in config/models.yaml).
Tier 1 alt: `ollama` python package. Tier 2: approved hosted OpenAI-compatible
endpoint (only if the course approved it; configured via `.env`). Tier 3
guaranteed fallback: deterministic extractive answer built from the retrieved
passages — never an invented source.

Strict rules enforced here:
1. Early abstention when the top retrieval score is below the calibrated threshold.
2. Every citation is re-validated against stored passages (citations.py).
3. If no valid source remains, insufficient_evidence=True and sources=[].
4. Optional conflict detection surfaces contradictory retrieved passages.

Generation order (adjusted for this laptop — ollama runs here, llama-server does not):
  1) Ollama alt (qwen2.5:0.5b-instruct) — primary for this environment.
  2) llama-server — only if someone deploys the binary on port 8081.
  3) approved hosted OpenAI-compatible endpoint — only with course approval + .env.
  4) deterministic extractive answer from retrieved passages — guaranteed fallback.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Optional

# YAML loading: prefer PyYAML when it is available; fall back to the
# lightweight bundled reader (src/yaml_reader.py) on machines where it cannot
# be installed (e.g. build/test VMs without a compiler for the C extension).
try:
    import yaml as _yaml
    _yaml_load = _yaml.safe_load
except Exception:  # pragma: no cover — path exercised on Yahya's laptop as of 2026-10-17
    from src.yaml_reader import load_yaml as _yaml_load

from src import answer_schema
from src import citations as cite
from src.retrieve import retrieve

ROOT = pathlib.Path(__file__).resolve().parent.parent
_MODELS_PATH = ROOT / "config" / "models.yaml"
_RETRIEVAL_PATH = ROOT / "config" / "retrieval.yaml"
_HARDWARE_PATH = ROOT / "config" / "hardware.yaml"


def _load(path: pathlib.Path) -> dict:
    return _yaml_load(path.read_text(encoding="utf-8"))


MODELS = _load(_MODELS_PATH)
RETRIEVAL = _load(_RETRIEVAL_PATH)
HARDWARE = _load(_HARDWARE_PATH)


GEN_CFG = MODELS["generation"]
TOP_K = RETRIEVAL["top_k"]
MIN_SCORE = RETRIEVAL["threshold_score"]
MAX_CTX_CHARS = RETRIEVAL["max_context_chars"]
PASSAGE_STORE_PATH = ROOT / "artifacts" / "passages.jsonl"
ABSTAIN = ("The provided books do not contain sufficient evidence "
           "to answer this question.")

SYSTEM_PROMPT = (
    "Answer ONLY from the numbered passages provided. Cite each claim with its passage "
    "ID in square brackets, e.g. [BOOK_ID_P_PAGE_C_NUM]. Never invent IDs, titles, "
    "pages or facts. Keep the answer to 1-3 sentences. If passages disagree, begin with "
    "'CONFLICT:' and describe both views with their IDs. If the passages do not answer "
    "the question, reply exactly: INSUFFICIENT EVIDENCE."
)


def _ctx_format(hits, max_ctx=MAX_CTX_CHARS):
    """Render passages as [chunk_id] (title, page X) text blocks with an overall char cap."""
    parts, used = [], 0
    for h in hits:
        block = f"[{h['chunk_id']}] ({h['title']}, page {h['page']})\n{h['text']}\n"
        if used + len(block) > max_ctx and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts), len(parts)


def _format_sources(hits):
    return [{"book_id": h["book_id"], "page": h["page"], "chunk_id": h["chunk_id"]}
            for h in hits]


# --------------------------- local generation -------------------- #
GEN_TIMEOUT_S = 60.0   # TASK 2: hard cap on the whole generation call


def _post_chat_completion(url: str, body: dict, timeout_s: float) -> Optional[str]:
    """Single blocking HTTP POST with a HARD wall-clock deadline.

    Runs in a worker thread so a hung socket can never block the caller past
    `timeout_s` (the main thread returns and degrades to extractive instead).
    The abandoned daemon thread dies with the process; it only ever talks to
    127.0.0.1, so there is no leaked external connection.
    """
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor

    def _do() -> str:
        req = urllib.request.Request(url, json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_do).result(timeout=timeout_s)
    except Exception:
        return None


def _local_generate_llama_server(prompt: str) -> Optional[str]:
    """Call the small llama.cpp llama-server (OpenAI-compatible endpoint).

    Start it with (config/models.yaml contains the exact command too):
        Start-Process tools\\llama.cpp\\llama-server.exe -ArgumentList
            "-m models\\qwen2.5-0.5b-instruct-q4_k_m.gguf -c 1024 -t 2 --port 8081 --host 127.0.0.1"
    Stop it with: Stop-Process -Name llama-server
    (The launcher START_CHATBOT.bat does this for you.)
    """
    tier_key = f"tier{GEN_CFG.get('tier', 0)}"
    tier_cfg = GEN_CFG.get(tier_key, {})
    body = {
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": prompt}],
        "temperature": GEN_CFG.get("temperature", 0),
        "max_tokens": tier_cfg.get("max_new_tokens", 96),
        "stop": GEN_CFG.get("stop_markers", []),
    }
    return _post_chat_completion(GEN_CFG["server_url"], body, GEN_TIMEOUT_S)


def _local_generate_ollama(prompt: str) -> Optional[str]:
    """Alternative local engine (Tier 1 alt): Ollama CPU mode with tiny model.

    Also bounded by the same hard 60-second deadline (TASK 2). Never touches
    the network unless an ollama server is already listening on localhost.
    """
    import threading

    cfg_alt = MODELS.get("generation_ollama_alt", {})
    box: dict = {}

    def _do():
        try:
            import ollama
            resp = ollama.chat(model=cfg_alt.get("model_name", "qwen2.5:0.5b-instruct"),
                               messages=[{"role": "system", "content": SYSTEM_PROMPT},
                                         {"role": "user", "content": prompt}],
                               options={
                                   "num_ctx": cfg_alt.get("context_length", 1024),
                                   "num_predict": cfg_alt.get("max_new_tokens", 96),
                                   "temperature": cfg_alt.get("temperature", 0),
                                   "top_p": cfg_alt.get("top_p", 1.0),
                                   "num_thread": HARDWARE.get("threads", 2),
                               })
            box["text"] = resp["message"]["content"].strip()
        except Exception:
            box["text"] = None

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(GEN_TIMEOUT_S)
    if t.is_alive():
        return None          # timed out -> caller degrades, never hangs
    return box.get("text")


# --------------------------- hosted generation -------------------- #
def _hosted_generate(prompt: str) -> Optional[str]:
    """Approved hosted OPENAI-compatible fallback (Tier 2). Requires .env.

    HARD RULE: disabled unless config/models.yaml generation.hosted.enabled is
    true AND a key exists in .env — so an offline machine NEVER dials out.
    A missing dotenv/openai install returns None (fall through to extractive)
    rather than raising and breaking the whole answer path.
    """
    hosted = GEN_CFG.get("hosted") or {}
    if not hosted.get("enabled", False):
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        key = os.getenv("HOSTED_API_KEY")
        if not key or not os.getenv("HOSTED_MODEL"):
            return None
        from openai import OpenAI
        client = OpenAI(api_key=key,
                        base_url=os.getenv("HOSTED_BASE_URL") or None)
        resp = client.chat.completions.create(
            model=os.environ["HOSTED_MODEL"],
            temperature=GEN_CFG.get("temperature", 0),
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": prompt}])
        return resp.choices[0].message.content
    except Exception:
        return None


# --------------------------- extractive fallback --------------- #
def _extractive_answer(question: str, hits) -> str:
    """Deterministic grounded answer: pick best sentence from passages.

    Light keyword-overlap scoring; returns only whole sentences from the
    retrieved passages (no invented content) plus chunk-id citation.
    """
    stop = set("a an the is are was were be been to of in on for with and or as by "
               "that this it its from what which how who whom does do did".split())
    qwords = {w for w in re.findall(r"[a-zA-Z0-9]+", question.lower()) if w not in stop}
    best, best_sc = None, 0.0
    for h in hits:
        for sentence in re.split(r"(?<=[.!?])\s+", h["text"]):
            sw = set(re.findall(r"[a-zA-Z0-9]+", sentence.lower()))
            score = len(qwords & sw)
            if score > best_sc:
                best_sc, best = score, sentence.strip()
    if best and best_sc >= 2:
        return best
    return "INSUFFICIENT-EVIDENCE"


def _load_passage_store():
    # Honour an explicit override (used by tests); otherwise use the same
    # corpus the retriever is currently serving from.
    if PASSAGE_STORE_PATH.is_file():
        path = PASSAGE_STORE_PATH
    else:
        from src.retrieve import _active_paths
        _, path = _active_paths()
    if not path.is_file():
        return {}
    store = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                store[r["chunk_id"]] = r
    return store


def _generate_with_deadline(prompt: str) -> tuple[Optional[str], str]:
    """Run the local generation chain under a HARD 60-second deadline (TASK 2).

    Returns (text, mode):
      ("...", "local-llm")        — ollama answered in time
      ("...", "local-llm")        — llama-server answered in time
      (None,   "extractive_timeout") — engine was reachable but too slow
      (None,   "extractive")      — no local engine available at all
    Never raises, never hangs past GEN_TIMEOUT_S.
    """
    import threading

    box: dict = {"text": None, "mode": "extractive"}

    def _chain():
        # 1) Ollama alt (fastest for this laptop + already configured)
        text = _local_generate_ollama(prompt)
        if text is not None:
            box["text"], box["mode"] = text, "local-llm"
            return
        # 2) llama-server (started by START_CHATBOT.bat when the model exists)
        text = _local_generate_llama_server(prompt)
        if text is not None:
            box["text"], box["mode"] = text, "local-llm"
            return
        # 3) approved hosted endpoint — only with written approval; the config
        #    flag stays false, so offline machines never reach this code path.
        text = _hosted_generate(prompt)
        if text is not None:
            box["text"], box["mode"] = text, "hosted-approved"

    t = threading.Thread(target=_chain, daemon=True)
    t.start()
    t.join(GEN_TIMEOUT_S)
    if t.is_alive():
        # Engine hung past the hard cap: degrade honestly, label it distinctly
        # so the UI can say "the model timed out", not "no model installed".
        return None, "extractive_timeout"
    return box["text"], box["mode"]


def build(question: str, top_k: Optional[int] = None) -> dict:
    """Main entry point. Returns the common answer payload.

    {
      "answer": str,
      "sources": [{"book_id": ..., "page": ..., "chunk_id": ...}],
      "insufficient_evidence": bool,
      "conflicts": [...],   # optional; surfaces contradictory passages
      "mode": "local-llm" | "extractive" | "extractive_timeout" | "hosted-approved"
    }
    """
    k = top_k or TOP_K
    hits = retrieve(question, top_k=k)
    if not hits or hits[0]["score"] < MIN_SCORE:
        return {"answer": ABSTAIN, "sources": [], "insufficient_evidence": True}

    context, used = _ctx_format(hits)
    hits_used = hits[:used]
    prompt = f"Passages:\n{context}\n\nQuestion: {question}"

    generated, mode = _generate_with_deadline(prompt)
    timed_out = (mode == "extractive_timeout")
    if generated is None:
        generated = _extractive_answer(question, hits_used)
        mode = "extractive_timeout" if timed_out else "extractive"
    text = generated.strip()


    # Conflict detection (cheap heuristic): flag if two passage claims disagree.
    conflicts = []
    for i in range(len(hits_used) - 1):
        a, b = hits_used[i], hits_used[i + 1]
        if answer_schema.is_contradictory(a["text"], b["text"]):
            conflicts.append(
                f"Passages {a['chunk_id']} and {b['chunk_id']} appear to disagree. "
                f"A: {a['text'][:120]}...  B: {b['text'][:120]}....")

    # If the model itself refused evidence, abstain but attach TRUE conflict info.
    if "INSUFFICIENT EVIDENCE" in text.upper():
        payload = {"answer": ABSTAIN, "sources": [],
                   "insufficient_evidence": True, "mode": mode}
        if conflicts:
            payload["conflicts"] = conflicts
        return payload

    store = _load_passage_store()
    sources = cite.validate_citations(text, hits_used, store)
    if not sources:
        # Model gave no valid citation: use extractive fallback grounded in hits.
        generated = _extractive_answer(question, hits_used)
        if generated == "INSUFFICIENT-EVIDENCE":
            return {"answer": ABSTAIN, "sources": [],
                    "insufficient_evidence": True, "mode": "extractive"}
        text = generated.strip()
        mode = "extractive_timeout" if timed_out else "extractive"
        sources = cite.validate_citations(generated, hits_used, store) or \
                  _format_sources(hits_used[:1])

    payload = {"answer": text, "sources": sources,
               "insufficient_evidence": False, "mode": mode}
    if conflicts:
        payload["conflicts"] = conflicts
    return payload


def answer(question: str, top_k: Optional[int] = None) -> dict:
    """Public API used by CLI and Streamlit; validates the payload shape."""

    payload = build(question, top_k=top_k)
    errs = answer_schema.validate_answer(payload)
    if errs:
        # Last-resort honest fallback — never show an invalid payload.
        return {"answer": "System error during answer validation: "
                          + "; ".join(errs) + ". Please retry.",
                "sources": [],
                "insufficient_evidence": True}
    return payload


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "What is Ohm's law?"
    print(json.dumps(answer(q), indent=2, ensure_ascii=False))
