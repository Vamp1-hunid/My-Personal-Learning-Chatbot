"""src/app.py — Memory-safe Streamlit DEMO page.

Run from the project root:
    python -m streamlit run src/app.py
(stop with Ctrl+C in the terminal; the llama-server process is NOT managed
here — start/stop it yourself per config/models.yaml, or the page runs in
labelled extractive mode.)

Memory-safety rules implemented in this page:
1. BOUNDED history: only the last MAX_TURNS questions are kept in
   session_state, and every stored text (question, answer, passage snippet)
   is truncated, so a long demo can never grow RAM without limit.
2. LAZY loading: the FAISS index / embedding model / passage store are loaded
   only when the first question is asked (or via the explicit sidebar button).
   Hit preload before the demo to avoid the first-question stall on an HDD.
3. PASSAGE SNIPPETS are truncated to retrieval.yaml snippet_chars when stored
   or displayed; full passages stay in the store on disk, not in RAM.
4. MEMORY CHECKS: the sidebar shows available RAM and this process RSS against
   the warn (6 GB) / hard (7 GB) thresholds from config/memory.yaml. Below the
   min-free threshold the demo auto-suggests tier-0 settings (top_k=3).
5. NO chat-session caching of embeddings or answer objects beyond the bounded
   log; re-asking a question re-retrieves (cheap: one MiniLM encode).

What the page shows per question:
- Retrieved passages: every top-k hit with its cosine score bar, book title,
  PDF page, chunk_id and (truncated) passage text.
- Citations: only sources that survived citation validation (citations.py),
  each expandable to the exact stored passage it points at.
- Abstention: a red banner plus the reason (top score below threshold, no
  candidates, no valid citation survived), with the score/threshold numbers.
- Answer mode and latency: local-llm / extractive / hosted-approved, seconds.
"""
from __future__ import annotations

import time

import streamlit as st

from src import memwatch
from src.generate import answer
from src.retrieve import retrieve

st.set_page_config(page_title="Book-Grounded Chatbot — Demo", layout="wide")

MAX_TURNS = 8            # bounded session history (memory cap on the demo)
Q_CHARS = 500            # max question chars stored
A_CHARS = 4000           # max answer text chars stored

st.title("Book-Grounded Chatbot — Demo")
st.caption(
    "Answers come ONLY from the ingested books. Every citation is validated "
    "against the stored passages before display; questions the corpus cannot "
    "support are refused (abstained)."
)


@st.cache_data(ttl=3600)
def _retrieval_config() -> dict:
    """Small config read, cached once, kept out of the hot path."""
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    return yaml.safe_load((root / "config" / "retrieval.yaml").read_text(encoding="utf-8"))["retrieval"]


RETR = _retrieval_config()
THRESHOLD = float(RETR.get("threshold_score", 0.35))
SNIPPET_CHARS = int(RETR.get("snippet_chars", 480))


def _trim(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ----------------------------- sidebar -----------------------------
with st.sidebar:
    st.header("System status")

    avail = memwatch.available_gb()
    rss = memwatch.peak_used_gb()
    cfg = memwatch.CFG
    warn, hard, min_free = cfg["warn_gb"], cfg["hard_gb"], cfg["min_free_gb"]

    c1, c2 = st.columns(2)
    c1.metric("Free RAM", f"{avail:.1f} GB")
    c2.metric("Demo RSS", f"{rss:.2f} GB")
    st.caption(f"warn > {warn:.0f} GB · hard > {hard:.0f} GB (process)")

    if rss > hard:
        st.error("HARD memory cap exceeded. Stop the demo (`Ctrl+C`), stop "
                 "llama-server, and close other apps.")
    elif rss > warn:
        st.warning("Above warn threshold. Close apps; the runner may drop to "
                   "extractive mode.")
    if avail < min_free:
        st.warning(f"Only {avail:.1f} GB free (< {min_free:.0f} GB): using "
                   "tier-0 settings — top_k=3, small context.")

    low_ram = avail < min_free

    default_k = 3 if low_ram else int(RETR.get("top_k", 5))
    top_k = st.selectbox("Passages retrieved per question (top_k)",
                         options=[3, 5],
                         index=[3, 5].index(default_k if default_k in (3, 5) else 5),
                         help="top_k=3 is the tier-0 memory-safe setting "
                              "(config/retrieval.yaml: top_k_tier0).")

    if st.button("Preload retriever (index + embedder)", use_container_width=True):
        t0 = time.perf_counter()
        try:
            retrieve("preload", top_k=1)
            st.success(f"Loaded in {time.perf_counter() - t0:.0f} s. Ready.")
        except Exception as exc:
            st.error(f"Preload failed: {exc}")
    st.caption("Preload before a demo/question session so the first question "
               "does not stall on HDD reads.")

    if st.button("Clear demo log", use_container_width=True):
        st.session_state.log = []
        st.success("Log cleared.")
    st.caption(
        "History keeps only the last "
        f"{MAX_TURNS} questions with truncated texts, so demo memory stays flat.\n\n"
        "Generation runs in a SEPARATE llama-server process; if it is down, "
        "answers appear in labelled extractive mode."
    )


# ----------------------------- ask box -----------------------------
question = st.chat_input("Ask a question about the approved books…")

if question:
    entry = {"q": _trim(question, Q_CHARS)}
    t0 = time.perf_counter()
    try:
        payload = answer(question)
        entry["latency"] = time.perf_counter() - t0
        # Second retrieve call: one extra MiniLM encode (~ms on CPU), but it
        # gives the page every top-k hit — validated sources are a subset.
        entry["hits"] = [
            {k2: _trim(str(v), SNIPPET_CHARS) if k2 in ("text", "title")
             else v for k2, v in h.items()}
            for h in retrieve(question, top_k=top_k)
        ]
        entry["a"] = {k2: _trim(payload[k2], A_CHARS) if k2 == "answer" else payload[k2]
                      for k2 in payload}
    except FileNotFoundError as exc:
        entry["error"] = ("Index artifacts not found. Run ingest → chunk → "
                          "embed → index first, then reload this page. "
                          f"({exc})")
    except Exception as exc:
        entry["error"] = f"Unexpected failure: {exc}"
    st.session_state.log = (st.session_state.log + [entry])[-MAX_TURNS:]


# ----------------------------- rendering -----------------------------
def _render_source(h: dict) -> None:
    """One retrieved passage: score bar, metadata, truncated passage text."""
    score = float(h.get("score", 0.0))
    bar = min(1.0, max(0.0, score))
    meta = (f"[{h['chunk_id']}] {h.get('title', '?')} — PDF page {h.get('page', '?')} "
            f"({h.get('book_id', '?')})")
    with st.expander(meta, expanded=False):
        st.caption(f"cosine score: {score:.3f}  (threshold {THRESHOLD:.2f})")
        st.progress(bar if bar > 0 else 0.01)
        st.write(_trim(h.get("text", ""), SNIPPET_CHARS))


st.divider()
if not st.session_state.log:
    st.info("Ask something above. Good questions are ones the assigned books "
            "answer (e.g. definitions, laws, worked statements); try one that "
            "they cannot answer to see the abstention banner.")

for entry in st.session_state.log:
    st.chat_message("user").write(entry["q"])

    with st.chat_message("assistant"):
        if "error" in entry:
            st.error(entry["error"])
            continue

        p = entry["a"]
        hits = entry.get("hits", [])
        top_score = float(hits[0]["score"]) if hits else None

        m1, m2, m3 = st.columns(3)
        m1.metric("Latency", f"{entry.get('latency', 0.0):.2f} s")
        m2.metric("Top score",
                  f"{top_score:.3f}" if top_score is not None else "n/a",
                  None if top_score is None
                  else ("OK" if top_score >= THRESHOLD else "below threshold"))
        m2.caption(f"threshold {THRESHOLD:.2f}")
        m3.metric("Mode", str(p.get("mode", "—")))

        with st.expander("Retrieved passages (top-k, before validation)",
                         expanded=False):
            if hits:
                for h in hits:
                    _render_source(h)
            else:
                st.write("No candidates retrieved (empty corpus?).")

        if p.get("insufficient_evidence"):
            reason = ("no passages were retrieved"
                      if not hits
                      else (f"top score {top_score:.3f} is below the "
                            f"calibrated threshold {THRESHOLD:.2f}"
                            if top_score is not None and top_score < THRESHOLD
                            else "no citation survived validation"))
            st.error(
                f"**Refused (abstained) — {reason}.**\n\n{p['answer']}"
            )
            st.caption("Per the assignment contract an abstention carries no "
                       "sources: the payload is exactly "
                       "`{answer, sources: [], insufficient_evidence: true}`.")
        else:
            st.markdown(p["answer"])
            sources = p.get("sources") or []
            if sources:
                st.caption(f"Citations — all {len(sources)} validated against "
                           "the stored passage store:")
                for i, s in enumerate(sources, start=1):
                    label = (f"[{i}] {s['chunk_id']} — {s.get('title', '?')}, "
                             f"PDF page {s['page']} ({s['book_id']})")
                    with st.expander(label, expanded=False):
                        match = next(
                            (h for h in hits if h.get("chunk_id") == s["chunk_id"]),
                            None)
                        if match:
                            st.caption(f"retrieval score {match.get('score', 0):.3f}")
                            st.write(_trim(match.get("text", ""), SNIPPET_CHARS))
                        else:
                            st.write("Passage shown above under retrieved "
                                     "passages.")
            else:
                st.caption("No citations returned.")
            if p.get("conflicts"):
                for c in p["conflicts"]:
                    st.info(f"⚠ Conflict surfaced — {c}")
        if "mode" in p:
            st.caption(f"answer mode: {p['mode']}")
