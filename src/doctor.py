"""src/doctor.py — Run BEFORE installing/running anything heavy.

Usage:
    python src/doctor.py           # full check
    python src/doctor.py --json    # machine-readable output for CI / reports
"""
from __future__ import annotations

import ctypes
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUPPORTED_PY = [(3, 10), (3, 11), (3, 12)]
RECOMMENDED_PY = (3, 11)
PACKAGES = ["fitz", "sentence_transformers", "faiss", "numpy", "yaml",
            "psutil", "pytest", "streamlit"]

LIMAVX_AVX2_HINT = ("The AMD A8-7410 uses Puma+ cores; they support AVX but usually "
                    "NOT AVX2. A llama.cpp build that requires AVX2 will die with "
                    "'illegal instruction' (Windows exit code 3221225501 = 0xC000001D).")


def _memory_via_psutil():
    import psutil
    vm = psutil.virtual_memory()
    return vm.total, vm.available


def _memory_via_winapi():
    """Fallback: GlobalMemoryStatusEx (Windows only, no admin rights needed)."""
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        def __init__(self):
            self.dwLength = ctypes.sizeof(self)
            super().__init__()
    stat = MEMORYSTATUSEX()
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullTotalPhys, stat.ullAvailPhys


def memory_profile():
    try:
        return _memory_via_psutil()
    except Exception:
        return _memory_via_winapi()


def detect_gpu_name() -> str:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController).Name"],
            capture_output=True, text=True, timeout=10,
        )
        return (out.stdout or "").strip() or "unknown"
    except Exception as exc:  # noqa: BLE001 — best-effort detection
        return f"unknown ({type(exc).__name__})"


def check_llama_binary(exe_path: Path) -> str:
    """Sparse smoke test for llama.cpp llama-server.exe.

    Windows-specific: a build that requires AVX2 on a Puma+ CPU crashes with
    the STATUS_ILLEGAL_INSTRUCTION exit code 3221225501 (0xC000001D).
    """
    if not exe_path.is_file():
        return f"skipped (no file at {exe_path})"
    try:
        r = subprocess.run([str(exe_path), "--version"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            return f"OK  exit={r.returncode}  build OK"
        if r.returncode == 3221225501:      # 0xC000001D
            return ("FAIL  illegal instruction (0xC000001D) — this build needs AVX2 "
                    "which your APU lacks. Download the plain 'avx' build instead "
                    "of the 'avx2' or 'avx512' variant.")
        return f"FAIL  exit={r.returncode} stderr={r.stderr[:200]}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT (probably hung, keep an eye on it)"
    except Exception as exc:  # noqa: BLE001 — catch-all for the smoke call
        return f"FAIL  {type(exc).__name__}: {exc}"


def recommended_threads() -> int:
    physical = os.cpu_count() or 2
    return 2 if physical >= 2 else 1


def suggested_tier(avail_gb: float) -> int:
    return 0 if avail_gb < 6.0 else 0


def check_packages() -> tuple[list[str], list[str]]:
    """Returns (found, missing)."""
    found, missing = [], []
    for pkg in PACKAGES:
        try:
            importlib.import_module(pkg)
            found.append(pkg)
        except Exception:
            missing.append(pkg)
    return found, missing


def main(json_out: bool = False):
    total, avail = memory_profile()
    total_gb, avail_gb = ((total or 0) / 2**30, (avail or 0) / 2**30)
    py = sys.version_info[:3]
    found, missing = check_packages()
    gpu = detect_gpu_name()
    llama_test = check_llama_binary(ROOT / "tools" / "llama.cpp" / "llama-server.exe")
    free_disk_gb = shutil.disk_usage(str(ROOT)).free / 2**30
    report = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": f"{py[0]}.{py[1]}.{py[2]}",
        "python_supported": py[:2] in SUPPORTED_PY,
        "logical_cores": os.cpu_count(),
        "suggested_threads": recommended_threads(),
        "ram_total_gb": round(total_gb, 2),
        "ram_available_gb": round(avail_gb, 2),
        "ram_zonets": "safe" if avail_gb >= 6.0 else "low",
        "gpu": gpu,
        "gpu_note": ("NVIDIA present, but the plan is CPU-first; "
                     "GPU path only as Tier 2/upgrade" if "NVIDIA" in gpu.upper()
                     else "no NVIDIA: CPU-only (integrated graphics is not AI VRAM)"),
        "free_disk_gb": round(free_disk_gb, 2),
        "packages_found": found,
        "packages_missing": missing,
        "llama.cpp_smoke_test": llama_test,
        "avx_note": LIMAVX_AVX2_HINT,
        "suggested_tier": suggested_tier(avail_gb),
        "suggested_memory_budget_gb": round(min(6.0, max(2.0, avail_gb - 3.0)), 1),
        "hard_cap_gb": 7.0,
        "problem_count": len(missing) + (0 if py[:2] in SUPPORTED_PY else 1),
    }
    if json_out:
        out = ROOT / "doctor_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"doctor_report.json written -> {out}")
    for k, v in report.items():
        print(f"{k}: {v}")
    return report


init = main  # alias for --json style entrypoint


if __name__ == "__main__":
    is_json = "--json" in sys.argv
    main(is_json)
    sys.exit(0)
