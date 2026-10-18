"""launcher/launch_chatbot.py — double-click entry point for the whole app.

Pure Python stdlib + subprocess. Designed to be run by a NON-TECHNICAL user
via START_CHATBOT.bat (or directly: python launcher\\launch_chatbot.py).

What it does, in order:
  1. Resolve a usable interpreter (.venv -> py -3.11 -> absolute 3.11 path).
     If none found: plain-English fix, exit 1. No traceback ever.
  2. Build the offline-first child environment (see runtime_probe.build_child_env).
  3. Pre-flight checks, one plain line each:
       artifacts present? build manifest hashes match? llama-server + GGUF
       present? ports 8081/8501 free?
  4. If the generation model is present: start llama-server DETACHED, log to
     logs\\llama_server.log, poll http://127.0.0.1:8081/health up to 60 s.
     Timeout => do NOT crash: continue in DEMO (extractive) mode.
  5. Start Streamlit DETACHED on 127.0.0.1:8501, poll the port, open a browser.
  6. Write logs\\chatbot.pid with both child PIDs.
  7. Friendly status block; block on input(); then kill both child trees
     (taskkill /T /F on Windows, SIGTERM group elsewhere). Never orphan children.

It NEVER imports faiss/torch/streamlit itself — heavy code lives only in the
children — so it runs on any Python and starts instantly even from the HDD.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import runtime_probe as rp  # noqa: E402  (stdlib-only helper module)

LOGS_DIR = ROOT / "logs"
LLAMA_LOG = LOGS_DIR / "llama_server.log"
PID_FILE = LOGS_DIR / "chatbot.pid"
LLAMA_PORT = 8081
STREAMLIT_PORT = 8501
HEALTH_URL = f"http://127.0.0.1:{LLAMA_PORT}/health"
APP_URL = f"http://127.0.0.1:{STREAMLIT_PORT}"


def say(line: str = "") -> None:
    print(line, flush=True)


# ---------------------------------------------------------------- startup ---
def find_interpreter() -> list[str]:
    cmd, desc = rp.resolve_interpreter(ROOT)
    if cmd is None:
        say(desc)          # plain-English fix instructions, no traceback
        sys.exit(1)
    say(f"[ok] Python interpreter: {desc}")
    return cmd


# ------------------------------------------------------------ pre-flight ---
def preflight(interpreter: list[str]) -> dict:
    """One plain-English line per check; returns state for the launch phase."""
    state = {"artifacts_ok": False, "fallback_corpus": False,
             "llama_exe": None, "gguf": None}

    ok, missing = rp.check_artifacts(ROOT)
    if ok:
        say("[ok] Index artifacts found (index.faiss, embeddings.npy, passages.jsonl).")
        status, msg = rp.verify_build_manifest(ROOT / "artifacts")
        if status == "mismatch":
            say(f"[!] {msg}")
            say("    The chatbot will REFUSE to answer until you rebuild, because a stale")
            say("    index produces plausible-but-wrong citations.")
        elif status == "absent":
            say(f"[~] {msg}")
        state["artifacts_ok"] = True
    else:
        say(f"[!] Index not built yet (missing: {', '.join(missing)}).")
        example = ROOT / "data" / "examples" / "passages.example.jsonl"
        if example.is_file():
            say("    You can continue in FALLBACK mode against the small bundled example")
            say("    corpus (demo quality only). For the real books run SETUP_ONCE.bat once.")
            try:
                ans = input("    Continue with the example corpus now? [y/N] ").strip().lower()
            except EOFError:
                ans = "n"
            state["fallback_corpus"] = (ans == "y")
        if not state["fallback_corpus"]:
            say("    Run SETUP_ONCE.bat first (needs internet once), then retry this launcher.")
            sys.exit(1)

    exe = rp.find_llama_server(ROOT)
    gguf = rp.find_gguf(ROOT)
    state["llama_exe"], state["gguf"] = exe, gguf
    if exe and gguf:
        say(f"[ok] Generation model found: {exe.name} + {gguf.name}")
    elif exe or gguf:
        have = exe or gguf
        say(f"[!] Generation model incomplete (found {have.name}, the other part is missing).")
        say("    See docs/MANUAL_STEPS.md for the exact download links.")
    else:
        say("[!] Generation model not installed yet - see docs/MANUAL_STEPS.md.")

    if rp.port_in_use(LLAMA_PORT):
        say(f"[!] Port {LLAMA_PORT} is already in use - assuming a llama-server is")
        say("    already running and reusing it.")
    if rp.port_in_use(STREAMLIT_PORT):
        say(f"[!] Port {STREAMLIT_PORT} is already in use - a chatbot window may")
        say("    already be open. Close it (or run STOP_CHATBOT.bat) and retry.")
        sys.exit(1)
    return state


# ----------------------------------------------------------- llama-server ---
def spawn_detached(cmd: list[str], env: dict, stdout_path: Path) -> subprocess.Popen:
    """Start a child that SURVIVES this launcher's console (detached on Windows)."""
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    logf = stdout_path.open("ab", buffering=0)
    kwargs = dict(cwd=str(ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT)
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    logf.close()   # child holds its own handle now
    return proc


def wait_for_health(timeout_s: int = 60, interval: float = 1.0, opener=None) -> bool:
    """Poll the llama-server /health endpoint. Injectable `opener` for tests."""
    if opener is None:
        import urllib.request

        def opener(url, timeout):
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return getattr(r, "status", r.getcode())

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if int(opener(HEALTH_URL, 2)) == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def wait_for_port(port: int, timeout_s: int = 90, interval: float = 1.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if rp.port_in_use(port):
            return True
        time.sleep(interval)
    return False


def start_generation(interpreter: list[str], env: dict, state: dict) -> tuple[subprocess.Popen | None, str]:
    """Returns (proc_or_None, mode). Never raises; degrades to extractive."""
    if not (state["llama_exe"] and state["gguf"]):
        say("Generation model did not start - running in DEMO (extractive) mode.")
        return None, "extractive"
    if rp.port_in_use(LLAMA_PORT):
        if wait_for_health(timeout_s=5):
            say("[ok] Reusing the llama-server already listening on 8081.")
            return None, "generative"
    cmd = [str(state["llama_exe"]),
           "-m", str(state["gguf"]),
           "-c", "1024", "-t", "2",
           "--host", "127.0.0.1", "--port", str(LLAMA_PORT)]
    say("[..] Starting llama-server (first load from the HDD can take minutes)...")
    try:
        proc = spawn_detached(cmd, env, LLAMA_LOG)
    except OSError as exc:
        say(f"[!] Could not start llama-server ({exc.__class__.__name__}).")
        say("Generation model did not start - running in DEMO (extractive) mode.")
        return None, "extractive"
    if wait_for_health(timeout_s=60):
        say(f"[ok] Generation model live on port {LLAMA_PORT} (pid {proc.pid}).")
        return proc, "generative"
    say("Generation model did not start - running in DEMO (extractive) mode.")
    say(f"       (details in {LLAMA_LOG.name}; e.g. an 'AVX2' build crashes on this CPU -")
    say("        download the plain 'avx' build, see docs/LAUNCHER.md troubleshooting)")
    kill_tree(proc)
    return None, "extractive"


# -------------------------------------------------------------- streamlit ---
def start_app(interpreter: list[str], env: dict) -> subprocess.Popen:
    cmd = interpreter + ["-m", "streamlit", "run", "src/app.py",
                         "--server.address", "127.0.0.1",
                         "--server.port", str(STREAMLIT_PORT),
                         "--server.headless", "true"]
    say("[..] Starting the chatbot window (this reads a lot from disk, be patient)...")
    return spawn_detached(cmd, env, LOGS_DIR / "streamlit.log")


# ------------------------------------------------------------------ pids ---
def write_pid_file(llama_pid: int | None, app_pid: int) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [str(app_pid)] + ([str(llama_pid)] if llama_pid else [])
    PID_FILE.write_text("\n".join(lines) + "\n", encoding="ascii")


def kill_tree(proc) -> None:
    """Kill a child and everything it spawned. Never leaves orphans."""
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30)
        else:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except Exception:
            pass
    except Exception:
        # Last resort so we never hang the shutdown path.
        try:
            proc.kill()
        except Exception:
            pass


def cleanup(llama_proc, app_proc) -> None:
    kill_tree(app_proc)
    kill_tree(llama_proc)
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ main ---
def main() -> int:
    say("=" * 62)
    say("  BOOK GROUNDED CHATBOT - starting up")
    say("=" * 62)
    interpreter = find_interpreter()
    state = preflight(interpreter)

    env = rp.build_child_env(ROOT)          # offline flags baked in
    llama_proc, mode = start_generation(interpreter, env, state)
    env["CHATBOT_MODE"] = mode

    app_proc = start_app(interpreter, env)
    write_pid_file(llama_proc.pid if llama_proc else None, app_proc.pid)

    app_up = wait_for_port(STREAMLIT_PORT, timeout_s=120)
    url = APP_URL
    if app_up:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    else:
        say("[!] The chatbot window is slow to come up (HDD). Open manually:")
        say(f"    {url}   - still loading, give it a minute.")

    say("")
    say("-" * 62)
    say(f"  MODE       : {'GENERATIVE (model-written answers)' if mode == 'generative' else 'DEMO (extractive passage answers)'}")
    say(f"  RETRIEVAL  : {'real book index' if state['artifacts_ok'] else 'bundled example corpus (demo only)'}")
    say(f"  ADDRESS    : {url}")
    say("  To shut down: close this window or run STOP_CHATBOT.bat")
    say("-" * 62)
    say("")

    try:
        input("Press Enter to stop...")
    except (EOFError, KeyboardInterrupt):
        pass
    say("Stopping children...")
    cleanup(llama_proc, app_proc)
    say("Stopped. Goodbye.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception as exc:  # absolutely never show a raw traceback to the user
        say(f"[!] Something went wrong: {exc}")
        say("    Run src/doctor.py for details, or see docs/LAUNCHER.md.")
        raise SystemExit(1)
