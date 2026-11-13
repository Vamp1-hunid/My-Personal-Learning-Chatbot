"""chat.py - puts each reply together.

For every message it:
  1. loads the conversation so far (data\\chats\\<id>.json)
  2. CHAT mode : finds relevant memories and adds them to the instructions
     STUDY mode: searches your books and hands the best passages to the model
  3. trims old messages so everything fits in the model's 4096-token window
  4. streams the reply back piece by piece, then saves the conversation
  5. (chat mode, auto-learn on) asks the model which new facts to remember
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Iterator

from . import docs, engine, library, llm, memory, ocr, web
from .prompts import (CHAT_SYSTEM, MEMORY_BLOCK, NO_PASSAGES, SIMPLER_REQUEST,
                      STUDY_CODE, STUDY_EXPLAIN, STUDY_QUICK, STUDY_QUIZ, STUDY_TEACH, NO_WEB, TYPO_NOTE, WEB_CODE, WEB_EXPLAIN,
                      WEB_QUICK, WEB_QUIZ, WEB_TEACH, VOICE_NOTE, STORY_RULES, CHARACTER_RULES)
from .settings import CHATS_DIR, CONFIG, load_state, user_name, write_json_atomic

GENERATE_LOCK = threading.Lock()   # one reply at a time; others wait their turn
CHARS_PER_TOKEN = 3.5              # rough rule of thumb for English text


# --------------------------------------------------------------------------- storage
def _path(conv_id: str):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", conv_id)
    return CHATS_DIR / f"{safe}.json"


def load_conversation(conv_id: str | None) -> dict:
    if conv_id:
        try:
            conv = json.loads(_path(conv_id).read_text(encoding="utf-8"))
            # every question and its answer share a 'turn' tag, so Retry and Edit know what to replace.
            # Older chats get a tag from their position (the same every time they are loaded).
            turn = None
            for i, m in enumerate(conv.get("messages", [])):
                if m.get("role") == "user":
                    turn = m.setdefault("turn", f"t{i}")
                elif turn and "turn" not in m:
                    m["turn"] = turn
            return conv
        except (OSError, ValueError):
            pass
    now = time.strftime("%Y-%m-%d %H:%M")
    return {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            "title": "New chat", "created": now, "updated": now, "messages": []}


def save_conversation(conv: dict) -> None:
    conv["updated"] = time.strftime("%Y-%m-%d %H:%M")
    write_json_atomic(_path(conv["id"]), conv)


def list_conversations() -> list[dict]:
    out = []
    for p in CHATS_DIR.glob("*.json"):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": c["id"], "title": c["title"], "updated": c["updated"]})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda c: c["updated"], reverse=True)


def delete_conversation(conv_id: str) -> bool:
    p = _path(conv_id)
    docs.delete_all(conv_id)          # its attached documents go too
    if p.exists():
        p.unlink()
        return True
    return False


# --------------------------------------------------------------------------- prompt building
def _tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 4


def _fit_history(history: list[dict], budget: int, max_turns: int) -> list[dict]:
    """Keep the newest messages that fit in the token budget."""
    kept: list[dict] = []
    for m in reversed(history[-max_turns * 2:]):
        cost = _tokens(m["content"])
        if cost > budget:
            break
        kept.insert(0, {"role": m["role"], "content": m["content"]})
        budget -= cost
    return kept


def _format_passages(hits: list[dict]) -> str:
    if not hits:
        return NO_PASSAGES
    parts = []
    for n, h in enumerate(hits, start=1):
        pages = f"p. {h['page']}" if h["page"] == h["page_end"] else f"pp. {h['page']}-{h['page_end']}"
        parts.append(f"[{n}] ({h['title']}, {pages})\n{h['text']}")
    return "\n\n".join(parts)


def _search_query(message: str, history: list[dict]) -> str:
    """Short follow-ups ("why?", "give an example") are searched together with the last question."""
    if len(message.split()) < 6:
        previous = [m["content"] for m in history if m["role"] == "user"]
        if previous:
            return previous[-1] + " " + message
    return message


def _public_source(n: int, h: dict) -> dict:
    return {"n": n, "title": h["title"], "page": h["page"], "page_end": h["page_end"],
            "score": h["score"], "text": h["text"], "category": h.get("category", "")}


# --------------------------------------------------------------------------- one turn
def reply(conv_id: str | None, mode: str, style: str, message: str,
          simpler: bool = False, book_category: str = "auto",
          images: list[str] | None = None, turn: str | None = None,
          rewind: str | None = None, voice: bool = False) -> Iterator[dict]:
    """Yield events for the web page: meta, sources, token..., done (or error).
    rewind = the tag of an earlier question: it and everything after it are removed first
    (used by Retry, Resend and Edit, so the old answer doesn't stay in the conversation)."""
    conv = load_conversation(conv_id)
    history = conv["messages"]
    if rewind:
        cut = next((i for i, m in enumerate(history) if m.get("turn") == rewind), None)
        if cut is not None:
            del history[cut:]
            save_conversation(conv)
    turn = re.sub(r"[^\w-]", "", turn or "")[:40] or uuid.uuid4().hex[:10]
    names = {"name": CONFIG["app_name"], "user": user_name()}   # your nickname, if you set one
    mode = mode if mode in ("study", "online", "create") else "chat"   # study = Offline (books)
    if mode == "create":
        style = "character" if style == "character" else "story"
    else:
        style = style if style in ("quick", "code", "teach", "quiz") else "explain"   # detailed by default
    if simpler:
        message = SIMPLER_REQUEST
    message = message.strip()
    images = [i for i in (images or []) if i.startswith("data:image/")]
    typed = message
    picture_note = ""
    if images:
        texts = []
        for n, img in enumerate(images, start=1):
            yield {"type": "status", "text": f"Reading picture {n} of {len(images)}..."}
            try:
                found = ocr.read_text(img)
            except (RuntimeError, ValueError) as e:
                found = ""
                yield {"type": "notice", "text": str(e)}
            label = f"Picture {n}" if len(images) > 1 else "The picture"
            texts.append(f"[{label} - text read from it]\n{found}" if found else f"[{label} - no readable text found]")
        picture_note = "\n\n".join(texts)
        yield {"type": "ocr", "text": picture_note}
        if not message:
            message = "Answer the question in the picture. Show your working step by step."
        message = message + "\n\n" + picture_note
    if not message:
        yield {"type": "error", "message": "Type a message first."}
        return
    if conv["title"] == "New chat":
        conv["title"] = (message[:48] + "...") if len(message) > 48 else message

    yield {"type": "meta", "conv_id": conv["id"], "title": conv["title"]}

    remembered = None
    if mode == "chat":
        explicit = memory.explicit_request(message)
        if explicit:
            remembered = memory.add(explicit, source="manual")
            yield {"type": "memory", "saved": [explicit] if remembered else [],
                   "note": "Saved to memory." if remembered else "I already knew that."}

    window = int(CONFIG["context_window"])
    caps = CONFIG["max_answer_tokens"]
    max_tokens = int(caps.get("chat" if mode == "chat" else style, caps.get("explain", 800)))
    # Voice mode: a reply that will be read aloud is kept short, so you hear it in seconds, not minutes
    spoken = voice and (mode == "chat" or style in ("explain", "quick"))
    if spoken:
        max_tokens = min(max_tokens, int(caps.get("voice", 220)))
    sources: list[dict] = []

    try:
        if mode == "chat":
            facts = memory.relevant(message)
            block = MEMORY_BLOCK.format(user=names["user"], facts="\n".join(f"- {f}" for f in facts)) if facts else ""
            system = CHAT_SYSTEM.format(memory_block=block, **names)
            budget = window - max_tokens - _tokens(system) - _tokens(message) - 64
            messages = [{"role": "system", "content": system + TYPO_NOTE.format(**names)}]
            messages += _fit_history(history, budget, max_turns=12)
            messages.append({"role": "user", "content": message})
            temperature = float(CONFIG["temperature"]["chat"])
        elif mode == "create":
            # story writing and character creation: no books, no web, more imagination
            system = (CHARACTER_RULES if style == "character" else STORY_RULES).format(**names)
            budget = window - max_tokens - _tokens(system) - _tokens(message) - 64
            messages = [{"role": "system", "content": system + TYPO_NOTE.format(**names)}]
            messages += _fit_history(history, max(0, budget), max_turns=10)
            messages.append({"role": "user", "content": message})
            temperature = float(CONFIG["temperature"].get("create", 0.9))
        elif mode == "online":
            last = next((m for m in reversed(history) if m["role"] == "assistant" and m.get("sources")), None)
            if simpler and last:
                found = last["sources"]
            else:
                yield {"type": "status", "text": "Searching the web..."}
                try:
                    found = web.gather(_search_query(message, history))
                except web.WebError as e:
                    yield {"type": "error", "message": str(e)}
                    return
                found = [{"n": n, "title": f["title"], "url": f["url"], "text": f["text"]}
                         for n, f in enumerate(found, start=1)]
            sources = found
            yield {"type": "sources", "sources": sources}
            extracts = "\n\n".join(f"[{s['n']}] ({s['title']})\n{s['text']}" for s in sources) or NO_WEB
            system = {"explain": WEB_EXPLAIN, "code": WEB_CODE, "teach": WEB_TEACH, "quiz": WEB_QUIZ}.get(style, WEB_QUICK).format(**names)
            content = f"Web extracts:\n{extracts}\n\nQuestion: {message}"
            budget = window - max_tokens - _tokens(system) - _tokens(content) - 64
            messages = [{"role": "system", "content": system + TYPO_NOTE.format(**names)}]
            messages += _fit_history(history, max(0, budget), max_turns=4 if style == "teach" else 2)
            messages.append({"role": "user", "content": content})
            temperature = float(CONFIG["temperature"]["study"])
        else:
            if simpler:
                last = next((m for m in reversed(history) if m["role"] == "assistant" and m.get("sources")), None)
                hits = [dict(s, book_id="") for s in (last or {}).get("sources", [])]
            else:
                hits = library.INDEX.search(_search_query(message, history), int(CONFIG["study_top_k"]),
                                            category=book_category)
                hits = [h for h in hits if h["score"] >= float(CONFIG["study_min_score"])
                        or h.get("keyword", 0) >= 0.6]   # strong exact-term match counts too
            sources = [_public_source(n, h) for n, h in enumerate(hits, start=1)]
            fixes = {} if simpler else dict(library.INDEX.last_corrections)
            yield {"type": "sources", "sources": sources,
                   "categories": [] if simpler else list(library.INDEX.last_categories),
                   "corrections": fixes}
            system = {"explain": STUDY_EXPLAIN, "code": STUDY_CODE, "teach": STUDY_TEACH, "quiz": STUDY_QUIZ}.get(style, STUDY_QUICK).format(**names)
            content = f"Book passages:\n{_format_passages(hits)}\n\nQuestion: {message}"
            if fixes:
                content += "\n(Probable spelling fixes: " + ", ".join(f"{k} -> {v}" for k, v in fixes.items()) + ")"
            budget = window - max_tokens - _tokens(system) - _tokens(content) - 64
            messages = [{"role": "system", "content": system + TYPO_NOTE.format(**names)}]
            messages += _fit_history(history, max(0, budget), max_turns=4 if style == "teach" else 2)
            messages.append({"role": "user", "content": content})
            temperature = float(CONFIG["temperature"]["study"])
    except llm.EngineNotReady as e:
        yield {"type": "error", "message": str(e)}
        return

    if spoken:
        messages[0] = {"role": "system", "content": messages[0]["content"] + VOICE_NOTE.format(**names)}

    # documents attached to this chat: add their most relevant parts, then trim older history to fit
    if conv.get("docs"):
        fixed = _tokens(messages[0]["content"]) + _tokens(messages[-1]["content"])
        room = window - max_tokens - fixed - 64
        block, used = docs.context_block(conv, _search_query(typed or message, history), max(0, min(1500, int(room * 0.75))))
        if block:
            middle = messages[1:-1]
            messages = ([{"role": "system", "content": messages[0]["content"] + "\n\n" + block}]
                        + _fit_history(middle, max(0, room - _tokens(block)), max_turns=len(middle) or 1)
                        + [messages[-1]])
            yield {"type": "context", "names": used}

    pieces: list[str] = []
    stats: dict = {}
    started = time.time()
    stopped_early = False
    with GENERATE_LOCK:
        if images and getattr(engine.CHAT, 'vision', False) and messages and messages[-1]['role'] == 'user':
            # this model can see pictures: send the picture itself along with the text read from it
            messages[-1] = {'role': 'user', 'content': [{'type': 'text', 'text': messages[-1]['content']}] +
                            [{'type': 'image_url', 'image_url': {'url': i}} for i in images]}
        stream = llm.chat_stream(messages, max_tokens, temperature)
        try:
            for event in stream:
                if "text" in event:
                    pieces.append(event["text"])
                    yield {"type": "token", "text": event["text"]}
                else:
                    stats = event["stats"]
        except llm.EngineNotReady as e:
            yield {"type": "error", "message": str(e)}
            return
        except GeneratorExit:      # you pressed Stop: keep what was written so far
            stopped_early = True
        except Exception as e:
            yield {"type": "error", "message": f"The engine stopped answering: {e}"}
            return
        finally:
            stream.close()   # closing the connection makes the engine stop writing
            text = "".join(pieces).strip()
            if text:
                history.append({"role": "user", "content": message, "mode": mode, "style": style, "turn": turn,
                                "display": "Explain that more simply" if simpler
                                else (typed or "Answer the question in the picture") + (" (with picture)" if images else "")})
                history.append({"role": "assistant", "content": text, "mode": mode, "style": style, "turn": turn,
                                "sources": sources,
                                "stats": {"tokens_per_second": round(stats.get("predicted_per_second", 0), 1),
                                          "seconds": round(time.time() - started, 1)}})
                save_conversation(conv)
    if stopped_early:
        return

    yield {"type": "done", "stats": history[-1]["stats"] if pieces else {}}

    auto = load_state().get("auto_learn", CONFIG["auto_learn"])
    if mode == "chat" and auto and not remembered and pieces:
        threading.Thread(target=_learn_later, args=(message, "".join(pieces)), daemon=True).start()


def _learn_later(message: str, text: str) -> None:
    with GENERATE_LOCK:   # wait until no reply is being written
        memory.learn_from_turn(message, text)
