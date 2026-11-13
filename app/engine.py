"""engine.py - starts and stops the llama.cpp AI engine (llama-server).

Two engines run side by side, each in its own background process:
  * the CHAT engine  - the language model you talk to (port 8090 by default)
  * the SEARCH engine - a tiny embedding model that turns text into numbers so
                        book passages and memories can be searched (port 8091)

Only one chat model is loaded at a time. Switching model = stop the old
process, start a new one with the other .gguf file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import re
from pathlib import Path

from .settings import CONFIG, ENGINE_DIR, LOGS_DIR, MODELS_DIR, PIDS_FILE, ROOT, load_state, save_state

IS_WINDOWS = os.name == "nt"
# On Windows, start engines without opening extra black console windows.
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
GB = 1024 ** 3


# --------------------------------------------------------------------------- helpers
def find_server_exe() -> list[str]:
    """Return the command that starts llama-server.

    Looks anywhere inside the engine folder, so it works whether you unzipped
    llama.cpp straight into engine\\ or into a sub-folder.
    The QUANTAKAI_FAKE_ENGINE variable is only used by the automatic
    tests (tests\\fake_llama_server.py) - you never need it.
    """
    if os.environ.get("QUANTAKAI_FAKE_ENGINE"):
        return [sys.executable, str(ROOT / "tests" / "fake_llama_server.py")]
    name = "llama-server.exe" if IS_WINDOWS else "llama-server"
    found = sorted(ENGINE_DIR.rglob(name))
    if not found:
        raise FileNotFoundError(
            f"{name} was not found inside {ENGINE_DIR}. "
            "Run SETUP.bat, or download llama.cpp by hand (BUILD_GUIDE.html, \"Download the engine\") and unzip it into the engine folder."
        )
    return [str(found[0])]


def is_gguf(path: Path) -> bool:
    """Every real model file starts with the 4 letters GGUF. Broken downloads do not."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except OSError:
        return False


def http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def list_models() -> list[dict]:
    """Every .gguf file in the models folder that can be used for chatting."""
    limit = float(CONFIG["max_model_gb"])
    embed_name = CONFIG["embedding_model"].lower()
    models = []
    for p in sorted(MODELS_DIR.glob("*.gguf"), key=lambda x: x.name.lower()):
        if p.name.lower() == embed_name or "mmproj" in p.name.lower():
            continue  # the search model and vision files are not chat models
        size_gb = p.stat().st_size / GB
        valid = is_gguf(p)
        reason = ""
        if not valid:
            reason = "Not a valid model file (download incomplete?)"
        elif size_gb > limit:
            reason = f"Bigger than the {limit:g} GB limit"
        models.append({
            "name": p.name,
            "size_gb": round(size_gb, 2),
            "allowed": valid and size_gb <= limit,
            "reason": reason,
        })
    return models


# --------------------------------------------------------------------------- Windows job
def _make_kill_on_close_job():
    """Windows only: put engines in a "job" so they die when this app dies.

    Without it, closing the black START window would leave llama-server
    running in the background, still holding gigabytes of memory.
    Returns a function that adds a process to the job (does nothing elsewhere).
    """
    if not IS_WINDOWS:
        return lambda proc: None
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("Basic", Basic), ("Io", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        info = Extended()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))

        def add(proc):
            try:
                k32.AssignProcessToJobObject(job, int(proc._handle))
            except Exception:
                pass
        add.job = job  # keep the job open for as long as the app runs
        return add
    except Exception:
        return lambda proc: None


_add_to_job = _make_kill_on_close_job()


# --------------------------------------------------------------------------- PID file
def _read_pids() -> dict:
    try:
        return json.loads(PIDS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_pid(role: str, pid: int | None) -> None:
    pids = _read_pids()
    if pid is None:
        pids.pop(role, None)
    else:
        pids[role] = pid
    PIDS_FILE.write_text(json.dumps(pids), encoding="utf-8")


def _process_name(pid: int) -> str:
    """Name of a running program, e.g. 'llama-server.exe' ('' if it is not running)."""
    try:
        if IS_WINDOWS:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, creationflags=NO_WINDOW).stdout
            return out.split('","')[0].strip('"').lower() if out.startswith('"') else ""
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").lower()
    except Exception:
        return ""


def kill_leftover_engines(roles: tuple = ("chat", "embed")) -> None:
    """Stop programs this app started last time and left running.

    Windows re-uses process numbers, so the name is checked first: only
    llama-server (or python, for the app itself) is ever stopped.
    """
    pids = _read_pids()
    for role in roles:
        pid = pids.pop(role, None)
        if not pid:
            continue
        name = _process_name(int(pid))
        expected = "python" if role == "ui" or os.environ.get("QUANTAKAI_FAKE_ENGINE") else "llama-server"
        if expected not in name:
            continue
        try:
            if IS_WINDOWS:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, creationflags=NO_WINDOW)
            else:
                os.kill(int(pid), 9)
        except Exception:
            pass
    PIDS_FILE.write_text(json.dumps(pids), encoding="utf-8")


def remember_pid(role: str, pid: int) -> None:
    _write_pid(role, pid)


# --------------------------------------------------------------------------- engine
class Engine:
    """One llama-server background process."""

    def __init__(self, role: str, port: int):
        self.role = role            # "chat" or "embed"
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.model: str | None = None
        self.state = "stopped"      # stopped | loading | ready | error
        self.vision = False         # True when the loaded model can look at pictures
        self.error = ""
        self.lock = threading.Lock()
        self.log = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.log:
            self.log.close()
            self.log = None
        self.state = "stopped"
        _write_pid(self.role, None)

    def start(self, model_file: Path, extra_args: list[str], timeout: float = 240,
              threads: int | None = None) -> bool:
        """Start llama-server with one model and wait until it answers /health."""
        with self.lock:
            self.stop()
            self.state, self.error, self.model = "loading", "", model_file.name
            log_path = LOGS_DIR / f"{self.role}-engine.log"
            cmd = find_server_exe() + [
                "-m", str(model_file),
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "-t", str(threads if threads is not None else CONFIG["threads"]),
            ] + extra_args
            self.log = open(log_path, "w", encoding="utf-8", errors="replace")
            self.log.write("COMMAND: " + " ".join(cmd) + "\n\n")
            self.log.flush()
            self.proc = subprocess.Popen(
                cmd, stdout=self.log, stderr=subprocess.STDOUT,
                cwd=str(ROOT), creationflags=NO_WINDOW,
            )
            _add_to_job(self.proc)
            _write_pid(self.role, self.proc.pid)
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    self.state = "error"
                    self.error = f"The engine stopped while loading. Read logs\\{log_path.name}"
                    return False
                if http_ok(self.base_url + "/health"):
                    self.state = "ready"
                    return True
                time.sleep(0.5)
            self.state = "error"
            self.error = f"The engine took longer than {timeout:.0f} s to load. Read logs\\{log_path.name}"
            return False


CHAT = Engine("chat", int(CONFIG["chat_port"]))
EMBED = Engine("embed", int(CONFIG["embed_port"]))


def find_vision_file(model_name: str) -> Path | None:
    """A model's vision file ("mmproj") lets it look at pictures. It must be named after the
    model, e.g. Qwen3.5-2B-mmproj.gguf for Qwen3.5-2B-Q4_K_M.gguf (a wrong one crashes the engine)."""
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9.]+", "-", s.lower())
    stem = norm(Path(model_name).stem)
    family = re.sub(r"-(q\d.*|iq\d.*|f16|bf16|f32)$", "", stem)        # drop the quantisation part
    family = re.sub(r"-(instruct|chat|it)$", "", family)
    for p in MODELS_DIR.glob("*.gguf"):
        n = norm(p.stem)
        if "mmproj" in n and family and family in n:
            return p
    return None


def load_chat_model(name: str) -> bool:
    """Load a chat model by file name. Refuses files over the size limit."""
    match = next((m for m in list_models() if m["name"] == name), None)
    if match is None:
        CHAT.state, CHAT.error = "error", f"{name} is not in the models folder."
        return False
    if not match["allowed"]:
        CHAT.state, CHAT.error = "error", f"{name}: {match['reason']}."
        return False
    vision = find_vision_file(name)
    args = ["-c", str(CONFIG["context_window"]), "-ngl", str(CONFIG["gpu_layers"]), "--parallel", "1"]
    if vision:
        args += ["--mmproj", str(vision)]
    ok = CHAT.start(MODELS_DIR / name, args)
    CHAT.vision = bool(ok and vision)
    if ok:
        save_state(last_model=name)
    return ok


def start_embed_engine() -> bool:
    path = MODELS_DIR / CONFIG["embedding_model"]
    if not is_gguf(path):
        EMBED.state = "error"
        EMBED.error = f"Search model {CONFIG['embedding_model']} is missing from the models folder."
        return False
    # bge-small reads at most 512 tokens per passage and uses "CLS" pooling.
    return EMBED.start(path, ["--embeddings", "--pooling", "cls",
                              "-c", "2048", "-b", "2048", "-ub", "512", "--parallel", "4"],
                       timeout=90, threads=int(CONFIG.get("embed_threads", 2)))


def pick_startup_model() -> str | None:
    """Last model you used, else the default, else the first allowed model."""
    allowed = [m["name"] for m in list_models() if m["allowed"]]
    for candidate in (load_state().get("last_model"), CONFIG["default_model"]):
        if candidate in allowed:
            return candidate
    return allowed[0] if allowed else None


def stop_all() -> None:
    CHAT.stop()
    EMBED.stop()
