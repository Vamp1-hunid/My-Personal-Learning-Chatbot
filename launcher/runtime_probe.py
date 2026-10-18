"""launcher/runtime_probe.py — pure-stdlib helpers for the launcher suite.

Everything in this module must work with NOTHING installed beyond the Python
standard library, and must be importable on ANY Python (3.8+), including the
broken 3.15 beta on the target laptop. That is what makes it unit-testable
(see tests/test_launcher_runtime.py) without faiss/torch/streamlit.

The launchers use these helpers to:
  * resolve a usable interpreter (venv -> py -3.11 -> absolute 3.11 path),
  * build the child-process environment (offline flags, thread caps),
  * run pre-flight checks (artifacts, build manifest, model binaries, ports),
  * verify artifacts/BUILD_MANIFEST.json sha256 hashes (TASK 3 staleness guard).

Contract note: nothing here touches retrieve()/answer JSON/passage schema.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Interpreter resolution
# --------------------------------------------------------------------------

# The ONLY known-good absolute interpreter on the target laptop (Windows).
# Python 3.15.0b2 is the machine default and is unusable (no faiss cp315
# wheel, pyyaml won't build) — never fall back to it.
ABSOLUTE_PY311_WINDOWS = os.path.join(
    "C:", os.sep + os.sep, "Users", "Mulenga Mwamba", "AppData", "Local",
    "Programs", "Python", "Python311", "python.exe")

FIX_INSTRUCTIONS = (
    "Could not find a usable Python 3.11 on this computer.\n"
    "Fix: install 'Python 3.11.x (Windows installer 64-bit)' from python.org\n"
    "       (check 'Add to PATH' is NOT required; the launcher finds it via 'py').\n"
    f"       Or place it at: {ABSOLUTE_PY311_WINDOWS}\n"
    "Then double-click START_CHATBOT.bat again."
)


def _is_usable_exe(p: str) -> bool:
    """True if p looks like an executable python binary that exists."""
    try:
        path = Path(p)
    except Exception:
        return False
    if not path.is_file():
        return False
    name = path.name.lower()
    return name.startswith("python") and name.endswith((".exe", "3", "3.11")) \
        or name in ("python", "python.exe", "python3.11", "python3.11.exe")


def candidate_interpreters(repo_root: Path, platform_name: str | None = None,
                           home: Path | None = None) -> list[list[str]]:
    """Ordered command candidates, per the contract:
       .venv\\Scripts\\python.exe  ->  py -3.11  ->  absolute 3.11 path.
    Never includes bare `python` (that is the broken 3.15 beta on this box).
    """
    plat = platform_name or sys.platform
    home = Path(home) if home else Path.home()
    cands: list[list[str]] = []
    if plat.startswith("win"):
        venv_py = repo_root / ".venv" / "Scripts" / "python.exe"
        if venv_py.is_file():
            cands.append([str(venv_py)])
        cands.append(["py", "-3.11"])
        cands.append([ABSOLUTE_PY311_WINDOWS])
    else:
        # Dev/CI boxes (and the grader's VM) are not Windows: keep the same
        # priority order but map onto POSIX equivalents.
        venv_py = repo_root / ".venv" / "bin" / "python"
        if venv_py.is_file():
            cands.append([str(venv_py)])
        cands.append(["py", "-3.11"])          # harmless when absent
        for alt in ("python3.11", "python3", sys.executable):
            exe = alt if os.path.sep in alt else shutil.which(alt)
            if exe:
                cands.append([exe])
    # de-duplicate while preserving order
    seen, out = set(), []
    for c in cands:
        key = tuple(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def probe_command(cmd: list[str]) -> bool:
    """Return True if `cmd` runs and reports Python >= 3.9 < 3.14."""
    try:
        r = subprocess.run(
            cmd + ["-c", "import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] < (3,14) else 1)"],
            capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def resolve_interpreter(repo_root: Path, probe=None) -> tuple[list[str], str] | tuple[None, str]:
    """Returns (cmd_list, description) on success, (None, FIX_INSTRUCTIONS) on failure.

    `probe` is injectable for tests; defaults to probe_command.
    """
    probe = probe or probe_command
    for cmd in candidate_interpreters(repo_root):
        if probe(cmd):
            return cmd, " ".join(cmd)
    return None, FIX_INSTRUCTIONS


# --------------------------------------------------------------------------
# Environment construction for child processes
# --------------------------------------------------------------------------

def build_child_env(repo_root: Path, base_env: dict | None = None,
                    mode: str | None = None) -> dict:
    """Offline-first environment shared by llama-server and Streamlit children.

    - HF_HOME points INSIDE the repo so the first-time download cache survives
      and every later run works with no network at all.
    - HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE kill any runtime hub call.
    - OMP_NUM_THREADS=2 matches config/hardware.yaml (4-core APU, power-capped).
    - KMP_DUPLICATE_LIB_OK=TRUE prevents the torch+faiss-cpu OpenMP crash on
      Windows (both bundle libiomp14md.dll).
    - CHATBOT_MODE tells src/app.py whether the generative model is live.
    """
    env = dict(base_env if base_env is not None else os.environ)
    models_dir = repo_root / "models"
    env["HF_HOME"] = str(models_dir / "hf_cache")
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    if mode:
        env["CHATBOT_MODE"] = mode
    return env


# --------------------------------------------------------------------------
# Pre-flight checks
# --------------------------------------------------------------------------

ARTIFACT_FILES = ("index.faiss", "embeddings.npy", "passages.jsonl")
LLAMA_EXE_REL = Path("tools") / "llama.cpp" / "llama-server.exe"
GGUF_DIR_REL = Path("models")
GGUF_PATTERN = "qwen2.5-0.5b-instruct-q4_k_m*.gguf"


def check_artifacts(repo_root: Path) -> tuple[bool, list[str]]:
    art = repo_root / "artifacts"
    missing = [f for f in ARTIFACT_FILES if not (art / f).is_file()]
    return (not missing), missing


def find_llama_server(repo_root: Path) -> Path | None:
    p = repo_root / LLAMA_EXE_REL
    return p if p.is_file() else None


def find_gguf(repo_root: Path) -> Path | None:
    d = repo_root / GGUF_DIR_REL
    if not d.is_dir():
        return None
    hits = sorted(d.glob(GGUF_PATTERN))
    if hits:
        return hits[0]
    # accept any 0.5B Q4_K_M gguf the user placed there
    hits = [p for p in sorted(d.glob("*.gguf"))
            if "0.5b" in p.name.lower() and "q4_k_m" in p.name.lower()]
    return hits[0] if hits else None


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


# --------------------------------------------------------------------------
# BUILD_MANIFEST verification (shared logic with src/retrieve.py)
# --------------------------------------------------------------------------

MANIFEST_NAME = "BUILD_MANIFEST.json"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_build_manifest(artifacts_dir: Path, embedding_cfg: dict,
                         num_chunks: int, group_id: str = "G014") -> Path:
    """Called by src/index.py after a successful build (TASK 3)."""
    from datetime import datetime, timezone
    rows = {}
    for fname in ARTIFACT_FILES:
        p = artifacts_dir / fname
        if p.is_file():
            rows[fname] = sha256_file(p)
    manifest = {
        "schema_version": 1,
        "group_id": group_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "num_chunks": int(num_chunks),
        "embedding_model": embedding_cfg.get("model_name"),
        "embedding_revision": embedding_cfg.get("revision"),
        "files": rows,
    }
    out = artifacts_dir / MANIFEST_NAME
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out


def verify_build_manifest(artifacts_dir: Path) -> tuple[str, str]:
    """Returns (status, message) where status is 'ok' | 'absent' | 'mismatch'.

    NEVER raises — the caller decides how loud to be. Message is one plain
    English line, suitable for printing directly (no traceback).
    """
    mf = artifacts_dir / MANIFEST_NAME
    if not mf.is_file():
        return "absent", ("No BUILD_MANIFEST.json (older index build) - "
                          "continuing, but rebuild when convenient.")
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as exc:
        return "mismatch", (f"BUILD_MANIFEST.json is unreadable ({exc}) - "
                            "rebuild the index.")
    bad = []
    for fname, want in (data.get("files") or {}).items():
        p = artifacts_dir / fname
        if not p.is_file():
            bad.append(f"{fname} missing")
        elif sha256_file(p) != want:
            bad.append(f"{fname} content changed")
    if bad:
        return "mismatch", ("Your index is out of sync with your passages "
                            "(" + "; ".join(bad) + "). Rebuild with SETUP_ONCE.bat.")
    return "ok", "Build manifest verified: index matches passages."
