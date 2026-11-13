"""settings.py - loads config.json and knows where every folder lives.

Every other file imports CONFIG and the folder paths from here, so paths are
written in exactly one place.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# The project folder is the parent of this "app" folder.
ROOT = Path(__file__).resolve().parent.parent

BOOKS_DIR = ROOT / "books"      # your PDF books go here
MODELS_DIR = ROOT / "models"    # .gguf model files go here
ENGINE_DIR = ROOT / "engine"    # llama.cpp (llama-server.exe) goes here
DATA_DIR = ROOT / "data"        # everything the app saves (index, memory, chats)
LOGS_DIR = ROOT / "logs"        # log files for troubleshooting
UI_DIR = ROOT / "ui"            # the web page you chat in

LIBRARY_DIR = DATA_DIR / "library"   # one .jsonl (text) + one .npy (vectors) per book
CHATS_DIR = DATA_DIR / "chats"       # one .json file per conversation
MEMORY_FILE = DATA_DIR / "memory.json"
STATE_FILE = DATA_DIR / "state.json"  # remembers the last model you loaded
PIDS_FILE = DATA_DIR / "engine_pids.json"

for _folder in (BOOKS_DIR, MODELS_DIR, ENGINE_DIR, DATA_DIR, LOGS_DIR, LIBRARY_DIR, CHATS_DIR):
    _folder.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    with open(ROOT / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG: dict = _load_config()


def _auto_threads() -> int:
    """Real (physical) cores. Most AMD Ryzen and Intel chips show 2 'logical
    processors' per core; using more threads than real cores makes llama.cpp slower."""
    logical = os.cpu_count() or 4
    return max(2, min(8, logical // 2 if logical >= 8 else logical))


if str(CONFIG.get("threads", "auto")).lower() == "auto":
    CONFIG["threads"] = _auto_threads()


def load_state() -> dict:
    """Small settings the app changes itself (last model, auto-learn switch)."""
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(**changes) -> dict:
    state = load_state()
    state.update(changes)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)
    return state


def user_name() -> str:
    """What QuantaKai calls you: the nickname set on the Personalise page, else user_name in config.json."""
    nick = str(load_state().get("nickname") or "").strip()
    return nick or str(CONFIG.get("user_name", "there"))


def write_json_atomic(path: Path, data) -> None:
    """Write to a temporary file first, then swap it in, so a crash never leaves half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
