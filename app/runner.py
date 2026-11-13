"""runner.py - runs code that QuantaKai wrote, on this laptop, and returns the output.

Python uses QuantaKai's own portable Python (numpy is available).
Java needs a JDK installed on the laptop (java 11 or newer can run one .java file directly).
Each run happens in a fresh temporary folder, with no keyboard input, and is stopped
after a time limit so a never-ending loop can't freeze anything.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .settings import CONFIG, DATA_DIR

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
MAX_OUTPUT = 20_000


def _python() -> str:
    return sys.executable   # the portable Python QuantaKai itself runs on


def _java() -> str | None:
    found = shutil.which("java")
    if found:
        return found
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / "java.exe").exists():
        return str(Path(home) / "bin" / "java.exe")
    return None


def languages() -> dict:
    return {"python": True, "java": _java() is not None}


def run(code: str, language: str) -> dict:
    language = (language or "").lower()
    if language in ("py", "python", "python3"):
        language = "python"
    if language not in ("python", "java"):
        return {"ok": False, "output": "", "error": f"Running {language or 'this'} code isn't supported. Python and Java are."}
    if len(code) > 100_000:
        return {"ok": False, "output": "", "error": "That code is too long to run."}
    timeout = int(CONFIG.get("run_timeout_seconds", 20))
    work = Path(tempfile.mkdtemp(prefix="run-", dir=DATA_DIR))
    try:
        if language == "python":
            src = work / "main.py"
            src.write_text(code, encoding="utf-8")
            cmd = [_python(), "-I", str(src)]
        else:
            java = _java()
            if not java:
                return {"ok": False, "output": "", "error": "Java isn't installed (or isn't on PATH). Install a JDK 17+ to run Java code."}
            m = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", code)
            src = work / f"{m.group(1) if m else 'Main'}.java"
            src.write_text(code, encoding="utf-8")
            cmd = [java, str(src)]           # single-file launch, no separate compile step
        started = time.time()
        try:
            p = subprocess.run(cmd, cwd=str(work), capture_output=True, stdin=subprocess.DEVNULL,
                               timeout=timeout, creationflags=NO_WINDOW,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace")[:MAX_OUTPUT]
            return {"ok": False, "output": out, "error": f"Stopped after {timeout} seconds (an endless loop, or waiting for input?).",
                    "seconds": timeout}
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace").replace(str(work) + os.sep, "")
        return {"ok": p.returncode == 0, "output": out[:MAX_OUTPUT], "error": err[-MAX_OUTPUT:],
                "exit_code": p.returncode, "seconds": round(time.time() - started, 2)}
    finally:
        shutil.rmtree(work, ignore_errors=True)
