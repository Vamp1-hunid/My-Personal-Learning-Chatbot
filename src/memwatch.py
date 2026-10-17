"""src/memwatch.py — runtime memory monitor.

Used by the CLI/every run to warn at 6 GB and crypto distinct hard-warn above
7 GB, per config/memory.yaml. Encourages closing heavy apps before generation;
never deletes file choices silently.
"""
from __future__ import annotations

import pathlib
import threading
import time

import psutil
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

# memory.yaml holds one top-level "memory" section; unwrap it so the keys
# (warn_gb, hard_gb, ...) are addressable directly. Without this the .get()
# calls below silently return None and fall back to hard-coded defaults.
_CFG_RAW = yaml.safe_load((ROOT / "config" / "memory.yaml").read_text(encoding="utf-8"))
CFG = _CFG_RAW.get("memory", _CFG_RAW)

_warn = CFG.get("warn_gb", 6.0) * (1 << 30)
_hard = CFG.get("hard_gb", 7.0) * (1 << 30)
_stop = threading.Event()
_peak = 0.0


def available_gb() -> float:
    return psutil.virtual_memory().available / (1 << 30)


def peak_used_gb() -> float:
    proc = psutil.Process()
    return proc.memory_info().rss / (1 << 30)


def check_once(verbose: bool = True) -> None:
    avail = available_gb()
    used = peak_used_gb()
    global _peak
    _peak = max(_peak, used)
    if used > _hard:
        print(f"⚠ HARD WARN: process used {used:.2f} GB > 7 GB cap; reduce "
              "context/base/max_new_tokens and retry. Generate Tier 3 or 4.")
    elif used > _warn:
        print(f"⚠ WARN: process used {used:.2f} GB > 6 GB target.")
    if avail < CFG.get("min_free_gb", 6.0):
        print(f"⚠ Available RAM is {avail:.2f} GB < 6 GB: auto-downgrading "
              "settings (Tier 0). Close browsers and other apps.")


def start_monitor(interval_s: float | None = None) -> threading.Thread:
    interval = float(interval_s or CFG.get("monitoring_interval_s", 30))

    def _run():
        while not _stop.is_set():
            check_once(verbose=False)
            _stop.wait(interval)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def stop_monitor() -> None:
    _stop.set()


def report_peak() -> float:
    return _peak
