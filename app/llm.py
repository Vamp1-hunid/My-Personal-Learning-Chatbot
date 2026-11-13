"""llm.py - talks to the two llama-server engines over HTTP.

llama-server speaks the same "OpenAI-compatible" API that many AI apps use:
  POST /v1/chat/completions  -> the model writes a reply
  POST /v1/embeddings        -> text is turned into a list of numbers (a vector)
Only Python's built-in urllib is used, so there is nothing extra to install.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterator

import numpy as np

from .engine import CHAT, EMBED


class EngineNotReady(RuntimeError):
    pass


def _post(url: str, payload: dict, timeout: float):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def chat_stream(messages: list[dict], max_tokens: int, temperature: float) -> Iterator[dict]:
    """Yield the reply piece by piece as it is written.

    Yields {"text": "..."} for each new piece, and finally {"stats": {...}}
    with the engine's own speed measurements.
    """
    if CHAT.state != "ready":
        raise EngineNotReady(CHAT.error or "No chat model is loaded yet.")
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.9,
        "stream": True,
        "stream_options": {"include_usage": True},
        "cache_prompt": True,
    }
    stats: dict = {}
    with _post(CHAT.base_url + "/v1/chat/completions", payload, timeout=600) as resp:
        for raw in resp:  # the server sends one "data: {...}" line per piece
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except ValueError:
                continue
            if event.get("timings"):
                stats = event["timings"]
            for choice in event.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    yield {"text": piece}
    yield {"stats": stats}


def chat_once(messages: list[dict], max_tokens: int = 200, temperature: float = 0.1) -> str:
    """Get a whole reply in one go (used for background jobs like memory saving)."""
    if CHAT.state != "ready":
        raise EngineNotReady(CHAT.error or "No chat model is loaded yet.")
    payload = {"messages": messages, "max_tokens": max_tokens,
               "temperature": temperature, "stream": False}
    with _post(CHAT.base_url + "/v1/chat/completions", payload, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"] or ""


# bge models search better when a QUESTION gets this prefix (passages do not).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _embed_raw(texts: list[str]) -> list[list[float]]:
    with _post(EMBED.base_url + "/v1/embeddings", {"input": texts}, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return [r["embedding"] for r in sorted(body["data"], key=lambda d: d["index"])]


def _embed_one_safely(text: str) -> list[float]:
    """One passage that the engine refused (usually too many word pieces: code, formulas,
    tables). Keep shortening it until it fits, so one awkward page can't fail a whole book."""
    for _ in range(8):
        try:
            return _embed_raw([text])[0]
        except urllib.error.HTTPError as e:
            if e.code not in (400, 413, 500) or len(text) <= 120:
                raise
            text = text[: int(len(text) * 0.7)]
    raise RuntimeError("A passage could not be indexed even after shortening it.")


def embed(texts: list[str], is_query: bool = False) -> np.ndarray:
    """Turn texts into unit-length vectors (rows). Similar meaning -> similar vectors."""
    if EMBED.state != "ready":
        raise EngineNotReady(EMBED.error or "The search engine is not running.")
    if is_query:
        texts = [QUERY_PREFIX + t for t in texts]
    texts = [t[:1500] for t in texts]  # usually inside the 512-token limit
    try:
        rows = _embed_raw(texts)
    except urllib.error.HTTPError as e:
        if e.code not in (400, 413, 500):
            raise
        rows = [_embed_one_safely(t) for t in texts]   # find and shrink the oversized one(s)
    vectors = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
