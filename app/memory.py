"""memory.py - the chatbot's long-term memory about you.

A language model cannot retrain itself while you talk to it. Instead, facts are
written to data\\memory.json (with a search vector each). Before every reply,
the memories that best match your message are found and handed to the model,
so it "remembers" them in later conversations.

Facts get in two ways:
  * you say "remember that ..."         -> saved straight away
  * auto-learn (can be switched off)    -> after each chat reply the model is
                                           asked to list new facts you stated
You can read, edit and delete everything on the Memory page.
"""
from __future__ import annotations

import re
import threading
import time
import uuid

import numpy as np

from . import llm
from .prompts import MEMORY_EXTRACT
from .settings import CONFIG, MEMORY_FILE, write_json_atomic

_lock = threading.Lock()
DUPLICATE_SCORE = 0.92   # a new fact this similar to an old one is not saved twice

REMEMBER_RE = re.compile(r"^\s*(?:please\s+)?remember(?:\s+that)?[\s,:]+(.{3,})$", re.I | re.S)


def _load() -> list[dict]:
    import json
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    write_json_atomic(MEMORY_FILE, items)


def list_all() -> list[dict]:
    return [{k: v for k, v in m.items() if k != "vec"} for m in _load()]


def _vector(text: str) -> list[float] | None:
    try:
        return [round(float(x), 5) for x in llm.embed([text])[0]]
    except Exception:
        return None  # search engine down: keep the fact, add its vector later


def add(text: str, source: str = "manual") -> dict | None:
    text = re.sub(r"\s+", " ", text).strip().rstrip(".") + "."
    if len(text) < 4:
        return None
    vec = _vector(text)
    with _lock:
        items = _load()
        if vec is not None:
            for m in items:
                if m.get("vec") and float(np.dot(m["vec"], vec)) >= DUPLICATE_SCORE:
                    return None  # already known
        item = {"id": uuid.uuid4().hex[:10], "text": text, "source": source,
                "created": time.strftime("%Y-%m-%d %H:%M"), "vec": vec}
        items.append(item)
        _save(items)
    return {k: v for k, v in item.items() if k != "vec"}


def update(mem_id: str, text: str) -> bool:
    with _lock:
        items = _load()
        for m in items:
            if m["id"] == mem_id:
                m["text"], m["vec"] = text.strip(), _vector(text)
                _save(items)
                return True
    return False


def delete(mem_id: str) -> bool:
    with _lock:
        items = _load()
        kept = [m for m in items if m["id"] != mem_id]
        _save(kept)
        return len(kept) != len(items)


def relevant(message: str) -> list[str]:
    """The stored facts that best match this message."""
    items = _load()
    if not items:
        return []
    # Fill in vectors that are missing (saved while the search engine was off).
    if any(m.get("vec") is None for m in items):
        with _lock:
            items = _load()
            for m in items:
                if m.get("vec") is None:
                    m["vec"] = _vector(m["text"])
            _save(items)
    usable = [m for m in items if m.get("vec")]
    if not usable:
        return []
    if len(usable) <= int(CONFIG["memory_top_k"]):
        return [m["text"] for m in usable]
    try:
        q = llm.embed([message], is_query=True)[0]
    except Exception:
        return [m["text"] for m in usable[-int(CONFIG["memory_top_k"]):]]
    scores = np.asarray([m["vec"] for m in usable], dtype=np.float32) @ q
    order = np.argsort(-scores)[: int(CONFIG["memory_top_k"])]
    return [usable[i]["text"] for i in order if scores[i] >= float(CONFIG["memory_min_score"])]


def explicit_request(message: str) -> str | None:
    """'remember that my exam is on 3 Dec' -> 'my exam is on 3 Dec'."""
    m = REMEMBER_RE.match(message)
    return m.group(1).strip() if m else None


def learn_from_turn(user_message: str, reply: str) -> list[str]:
    """Ask the model which new, lasting facts the user stated. Runs after the reply."""
    prompt = MEMORY_EXTRACT.format(user=user_message[:1500], reply=reply[:800])
    try:
        out = llm.chat_once([{"role": "user", "content": prompt}], max_tokens=120, temperature=0.0)
    except Exception:
        return []
    saved = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        fact = line.lstrip("- ").strip()
        if fact.upper().startswith("NONE") or len(fact) < 8:
            continue
        if add(fact, source="auto"):
            saved.append(fact)
    return saved
