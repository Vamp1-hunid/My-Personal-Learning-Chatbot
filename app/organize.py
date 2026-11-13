"""organize.py - tidies downloads into the right QuantaKai folders.

Drop downloaded files into a folder called "new stuff" (or "inbox") inside
QuantaKai, and the next time QuantaKai starts it moves each one where it belongs:
  - chat models (.gguf)                      -> models
  - Whisper speech model (ggml-*.bin)        -> voice
  - Piper voices (.onnx + .onnx.json)        -> voice
  - whisper-bin-x64.zip / piper_*.zip        -> voice (unpacked automatically)
  - sherpa-onnx-*.tar.bz2 / kokoro-*.tar.bz2  -> voice (Kokoro voice, unpacked automatically)
Files it doesn't recognise are left alone. Moving on the same drive is instant.
"""
from __future__ import annotations

import os
from pathlib import Path

from .settings import CONFIG, MODELS_DIR, ROOT

VOICE_DIR = ROOT / "voice"
INBOXES = ("new stuff", "inbox")


def _target(f: Path) -> Path | None:
    name = f.name.lower()
    if name.endswith(".gguf"):
        return MODELS_DIR          # chat models and their vision ("mmproj") files
    if name.startswith("ggml-") and name.endswith(".bin"):
        return VOICE_DIR
    if name.endswith(".onnx.json"):
        return VOICE_DIR
    if name.endswith(".onnx"):
        wanted = CONFIG.get("tts_voice", "en_US-hfc_female-medium").lower() + ".onnx"
        has_settings = (f.parent / (f.name + ".json")).exists() or (VOICE_DIR / (f.name + ".json")).exists()
        return VOICE_DIR if (name == wanted or has_settings) else None
    if name.endswith(".zip") and (name.startswith("whisper-bin") or name.startswith("piper")):
        return VOICE_DIR
    if name.endswith(".tar.bz2") and (name.startswith("sherpa-onnx") or name.startswith("kokoro")):
        return VOICE_DIR
    return None


def tidy_downloads() -> list[str]:
    moved = []
    for box in INBOXES:
        folder = ROOT / box
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            if not f.is_file() or f.name.endswith((".part", ".crdownload", ".tmp")):
                continue
            dest_dir = _target(f)
            if dest_dir is None:
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            if dest.exists():
                if dest.stat().st_size >= f.stat().st_size:
                    continue      # already have it; leave the spare copy for you to delete
                dest.unlink()     # the one already there is smaller: an incomplete download
            try:
                os.replace(f, dest)
                moved.append(f"{f.name} -> {dest_dir.name}")
            except OSError as e:
                print(f"  tidy: could not move {f.name}: {e}")
    for m in moved:
        print(f"  tidy: moved {m}")
    return moved
