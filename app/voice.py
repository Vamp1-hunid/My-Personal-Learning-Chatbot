"""voice.py - offline VOICE TYPING: turns your recorded speech into text.

It uses whisper.cpp (whisper-cli.exe) and a small Whisper speech model, both kept
in the QuantaKai\\voice folder. Nothing is sent to the internet.
Run VOICE_SETUP.bat once to download them (about 150 MB).

Reading answers ALOUD uses the best offline voice engine it finds:
  1. Kokoro (through sherpa-onnx) - very natural, bright young American female voices
  2. Piper - fast, decent quality
  3. the voices built into Windows (handled by the chat page) as a last resort
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .settings import CONFIG, DATA_DIR, ROOT, load_state, save_state, user_name

VOICE_DIR = ROOT / "voice"
TMP_DIR = DATA_DIR / "tmp"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # don't flash a black window
_lock = threading.Lock()                           # one transcription at a time


def unpack_downloads() -> list[str]:
    """If you drop piper_windows_amd64.zip or whisper-bin-x64.zip into the voice folder,
    unpack them into the right place automatically (no manual unzipping needed)."""
    import zipfile
    done = []
    if not VOICE_DIR.exists():
        return done
    import tarfile
    for t in VOICE_DIR.glob("*.tar.bz2"):
        name = t.name.lower()
        if not (name.startswith("sherpa-onnx") or name.startswith("kokoro")):
            continue
        folder = VOICE_DIR / t.name[:-len(".tar.bz2")]
        if folder.exists():
            continue
        try:
            print(f"  voice: unpacking {t.name} (this can take a minute)...")
            with tarfile.open(t, "r:bz2") as f:
                f.extractall(VOICE_DIR, filter="data")
            done.append(t.name)
        except (tarfile.TarError, OSError, EOFError) as e:
            print(f"  voice: could not unpack {t.name} (incomplete download?): {e}")
            import shutil
            shutil.rmtree(folder, ignore_errors=True)   # don't leave a half-unpacked folder behind
            try:
                t.replace(t.with_name(t.name + ".broken"))   # so a good copy can be dropped in later
            except OSError:
                pass
    for z in VOICE_DIR.glob("*.zip"):
        name = z.name.lower()
        try:
            if name.startswith("piper"):
                if _find_piper():
                    continue
                with zipfile.ZipFile(z) as f:
                    f.extractall(VOICE_DIR / "piper")
                done.append("Piper voice engine")
            elif name.startswith("whisper-bin"):
                if _find_cli():
                    continue
                tmp = VOICE_DIR / "_unpack"
                with zipfile.ZipFile(z) as f:
                    f.extractall(tmp)
                cli = next(tmp.rglob("whisper-cli.exe"), None)
                if cli:
                    for item in cli.parent.iterdir():
                        target = VOICE_DIR / item.name
                        if item.is_file() and not target.exists():
                            item.replace(target)
                    done.append("whisper.cpp voice typing engine")
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
        except (zipfile.BadZipFile, OSError) as e:
            print(f"  voice: could not unpack {z.name}: {e}")
    for d in done:
        print(f"  voice: unpacked the {d}")
    return done


def _find_cli() -> Path | None:
    if not VOICE_DIR.exists():
        return None
    for name in ("whisper-cli.exe", "whisper-cli", "main.exe"):
        hit = next(VOICE_DIR.rglob(name), None)
        if hit:
            return hit
    return None


def _find_model() -> Path | None:
    if not VOICE_DIR.exists():
        return None
    wanted = CONFIG.get("voice_model", "ggml-base.en.bin")
    exact = VOICE_DIR / wanted
    if exact.is_file() and exact.stat().st_size > 10_000_000:
        return exact
    models = [p for p in VOICE_DIR.rglob("ggml-*.bin") if p.stat().st_size > 10_000_000]
    return min(models, key=lambda p: p.stat().st_size) if models else None


_unpacking = threading.Event()


def start_unpacking() -> None:
    """Unpack any dropped-in voice downloads in the background (big ones take a minute)."""
    def work():
        try:
            unpack_downloads()
        finally:
            _unpacking.set()
        if tts_engine():
            prewarm_preview()          # loads the reading voice now (Piper or Kokoro), so the first answer speaks quickly
    threading.Thread(target=work, daemon=True).start()


KOKORO_STATS = {"calls": 0, "slow_calls": 0, "last_rtf": None, "disabled": False}


def _busy() -> bool:
    """True while books are being indexed: the processor is shared, so use the faster voice."""
    try:
        from . import library
        return bool(library.PROGRESS.get("running"))
    except Exception:
        return False


# Kokoro v1.0 speaker numbers 0-27 are the English voices (the rest are other languages)
KOKORO_VOICES = [
    (3, "Heart", "US female - most natural, warm and bright"),
    (2, "Bella", "US female - bright and expressive"),
    (7, "Nova", "US female - crisp and clear"),
    (10, "Sky", "US female - young and light"),
    (6, "Nicole", "US female - soft, close-mic"),
    (9, "Sarah", "US female - calm and friendly"),
    (4, "Jessica", "US female - relaxed"),
    (0, "Alloy", "US female - neutral"),
    (1, "Aoede", "US female - smooth"),
    (5, "Kore", "US female - steady"),
    (8, "River", "US female - easy-going"),
    (16, "Michael", "US male - warm"),
    (13, "Eric", "US male - clear"),
    (11, "Adam", "US male - deep"),
    (15, "Liam", "US male - young"),
    (17, "Onyx", "US male - low"),
    (18, "Puck", "US male - lively"),
    (12, "Echo", "US male - neutral"),
    (14, "Fenrir", "US male - strong"),
    (19, "Santa", "US male - jolly"),
    (21, "Emma", "UK female - warm"),
    (22, "Isabella", "UK female - bright"),
    (20, "Alice", "UK female - clear"),
    (23, "Lily", "UK female - soft"),
    (26, "George", "UK male - classic"),
    (24, "Daniel", "UK male - calm"),
    (27, "Lewis", "UK male - deep"),
    (25, "Fable", "UK male - storyteller"),
]


def voice_choice() -> dict:
    """Your pick from the voice menu (saved in data/state.json), or the config defaults."""
    v = load_state().get("voice") or {}
    return {"engine": v.get("engine", str(CONFIG.get("tts_engine", "auto")).lower()),
            "kokoro_sid": int(v.get("kokoro_sid", CONFIG.get("tts_kokoro_voice", 3))),
            "piper_voice": v.get("piper_voice", CONFIG.get("tts_voice", "en_US-hfc_female-medium"))}


def set_voice(engine: str, voice_id=None) -> dict:
    engine = engine.lower()
    if engine not in ("auto", "kokoro", "piper", "windows"):
        raise ValueError("Unknown voice engine")
    v = voice_choice()
    v["engine"] = engine
    if engine == "kokoro" and voice_id is not None:
        v["kokoro_sid"] = int(voice_id)
        KOKORO_STATS.update(disabled=False, slow_calls=0)   # you chose it, so try it again
    if engine == "piper" and voice_id:
        v["piper_voice"] = str(voice_id)
    save_state(voice=v)
    return v


def _kokoro_group() -> str:
    if _find_c_api():
        return "Kokoro - most natural (loads in a few seconds the first time)"
    return "Kokoro - natural, but slow on this laptop"


def voice_list() -> dict:
    options = []
    if _find_sherpa() and _find_kokoro():
        options += [{"engine": "kokoro", "id": sid, "name": f"{name} - {desc}", "group": _kokoro_group()}
                    for sid, name, desc in KOKORO_VOICES]
    if _find_piper():
        for onnx in sorted(VOICE_DIR.glob("*.onnx")):
            if onnx.with_suffix(".onnx.json").exists():
                label = onnx.stem.replace("en_US-", "").replace("en_GB-", "UK ").replace("-medium", "").replace("_", " ")
                options.append({"engine": "piper", "id": onnx.stem, "name": label.title(), "group": "Piper - fastest"})
    options.append({"engine": "windows", "id": "windows", "name": "Windows built-in voice", "group": "Other"})
    return {"options": options, "choice": voice_choice(), "active": tts_engine(), "kokoro": dict(KOKORO_STATS)}


def tts_engine() -> str | None:
    pref = voice_choice()["engine"]
    if pref == "windows":
        return None
    kokoro_ok = _find_sherpa() and _find_kokoro()
    if pref == "kokoro" and kokoro_ok:
        return "kokoro"
    # Automatic = the FAST voice (Piper) when it is installed; Kokoro sounds more natural but is
    # several times slower on a 4-core laptop, so it is used only when you pick a Kokoro voice
    if pref == "auto" and not (_find_piper() and _find_voice()) and kokoro_ok \
            and not KOKORO_STATS["disabled"] and not _busy():
        return "kokoro"
    if pref in ("auto", "piper", "kokoro") and _find_piper() and _find_voice():
        return "piper"
    return None


def status() -> dict:
    cli, model = _find_cli(), _find_model()
    engine = tts_engine()
    tts = engine is not None
    if cli and model:
        return {"available": True, "model": model.name, "tts": tts, "tts_engine": engine,
                "kokoro": dict(KOKORO_STATS, fast=bool(_find_c_api()), loaded=_KOKORO.proc is not None)}
    missing = "the speech engine" if not cli else "the speech model"
    return {"available": False, "tts": tts, "tts_engine": engine,
            "reason": f"Voice typing is not set up yet ({missing} is missing). "
                      "Double-click VOICE_SETUP.bat once (needs internet, about 230 MB)."}


# =========================================================================== speaking (Piper)
PIPER_DIR = VOICE_DIR / "piper"
_tts_lock = threading.Lock()
_tts_proc: subprocess.Popen | None = None


def _find_piper() -> Path | None:
    return next(PIPER_DIR.rglob("piper.exe"), None) if PIPER_DIR.exists() else None


def _make_compatible(cfg: Path) -> None:
    """Newer Piper voices group some vowel pairs (like "aɪ") under one id. The Piper
    engine for Windows (2023.11) only accepts single sounds and refuses to start, so
    drop those grouped entries; the engine then sends the two sounds separately."""
    import json
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        ids = data.get("phoneme_id_map", {})
        multi = [k for k in ids if len(k) != 1]
        if not multi:
            return
        backup = cfg.with_name(cfg.name + ".original")
        if not backup.exists():
            backup.write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")
        for k in multi:
            del ids[k]
        data.pop("vowel_clusters", None)
        cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  voice: made {cfg.name} work with this Piper engine")
    except (OSError, ValueError) as e:
        print(f"  voice: could not check {cfg.name}: {e}")


def _find_voice() -> Path | None:
    if not VOICE_DIR.exists():
        return None
    wanted = VOICE_DIR / (voice_choice()["piper_voice"] + ".onnx")
    if wanted.is_file() and wanted.with_suffix(".onnx.json").is_file():
        _make_compatible(wanted.with_suffix(".onnx.json"))
        return wanted
    return next((p for p in VOICE_DIR.glob("*.onnx") if p.with_suffix(".onnx.json").is_file()), None)


def _piper_args() -> list[str]:
    # length_scale < 1 = faster speech (0.88 is about 165 words a minute for this voice);
    # noise settings add natural, lively pitch movement; short pauses keep it snappy.
    return ["--length_scale", str(CONFIG.get("tts_speed", 0.88)),
            "--noise_scale", str(CONFIG.get("tts_expression", 0.72)),
            "--noise_w", str(CONFIG.get("tts_rhythm", 0.85)),
            "--sentence_silence", str(CONFIG.get("tts_pause", 0.12))]


def _start_piper() -> subprocess.Popen:
    """Keep one Piper running with the voice loaded, so each sentence starts fast."""
    out_dir = TMP_DIR / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    piper, voice = _find_piper(), _find_voice()
    return subprocess.Popen([str(piper), "--model", str(voice), "--output_dir", str(out_dir)] + _piper_args(),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            cwd=str(piper.parent), creationflags=NO_WINDOW)


def _speak_oneshot(text: str) -> bytes:
    piper, voice = _find_piper(), _find_voice()
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out = TMP_DIR / f"tts-{uuid.uuid4().hex[:8]}.wav"
    try:
        subprocess.run([str(piper), "--model", str(voice), "--output_file", str(out)] + _piper_args(),
                       input=text.encode("utf-8"), capture_output=True, timeout=60,
                       cwd=str(piper.parent), creationflags=NO_WINDOW)
        return out.read_bytes()
    finally:
        try:
            out.unlink()
        except OSError:
            pass


# =========================================================================== speaking (Kokoro)
def _find_sherpa() -> Path | None:
    return next(VOICE_DIR.rglob("sherpa-onnx-offline-tts.exe"), None) if VOICE_DIR.exists() else None


def _find_kokoro() -> Path | None:
    """The unpacked Kokoro folder (it holds model.onnx or model.int8.onnx, voices.bin, tokens.txt)."""
    if not VOICE_DIR.exists():
        return None
    for voices in VOICE_DIR.rglob("voices.bin"):
        d = voices.parent
        if (d / "tokens.txt").exists() and ((d / "model.int8.onnx").exists() or (d / "model.onnx").exists()):
            return d
    return None


def _find_c_api() -> Path | None:
    """sherpa-onnx-c-api.dll from the sherpa-onnx download (lets Kokoro stay loaded in memory)."""
    if not VOICE_DIR.exists() or os.name != "nt":
        return None
    return next(VOICE_DIR.rglob("sherpa-onnx-c-api.dll"), None)


class _KokoroWorker:
    """A helper program that keeps the Kokoro model loaded, so each sentence takes a fraction
    of a second instead of reloading 114 MB every time. If it fails, the old way is used."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lexicon = None
        self.failures = 0
        self.load_seconds = None

    def _read(self, timeout: float) -> dict:
        proc = self.proc
        timer = threading.Timer(timeout, lambda: proc.kill() if proc.poll() is None else None)
        timer.start()
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("the Kokoro helper stopped")
                line = line.decode("utf-8", "replace").strip()
                if line.startswith("@@"):
                    import json
                    return json.loads(line[2:])
        finally:
            timer.cancel()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None

    def _start(self, lexicon: str) -> None:
        import sys
        self.stop()
        dll, d = _find_c_api(), _find_kokoro()
        cmd = [sys.executable, "-I", str(Path(__file__).with_name("kokoro_worker.py")), str(dll.parent), str(d),
               lexicon or "-", str(CONFIG.get("threads", 4))]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=str(dll.parent), creationflags=NO_WINDOW)
        self.lexicon = lexicon
        reply = self._read(120)
        if not reply.get("ready"):
            self.stop()
            raise RuntimeError(reply.get("error") or "the Kokoro helper did not start")
        self.load_seconds = reply.get("load_seconds")
        print(f"  voice: Kokoro loaded and kept in memory ({self.load_seconds} s)")

    def speak(self, text: str, sid: int, lexicon: str, speed: float) -> tuple[bytes, float]:
        """Returns (wav bytes, seconds spent making it)."""
        import json
        if self.proc is None or self.proc.poll() is not None or lexicon != self.lexicon:
            self._start(lexicon)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        out = TMP_DIR / f"tts-{uuid.uuid4().hex[:8]}.wav"
        try:
            self.proc.stdin.write((json.dumps({"text": text, "sid": sid, "speed": speed, "out": str(out)}) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            reply = self._read(max(30.0, len(text) * 0.25))
            if not reply.get("ok") or not out.exists():
                raise RuntimeError(reply.get("error") or "no audio")
            return out.read_bytes(), float(reply.get("seconds", 0))
        except (OSError, ValueError) as e:
            self.stop()
            raise RuntimeError(f"the Kokoro helper failed ({e})")
        finally:
            try:
                out.unlink()
            except OSError:
                pass


_KOKORO = _KokoroWorker()


def _kokoro_lexicon() -> str:
    d = _find_kokoro()
    british = 20 <= voice_choice()["kokoro_sid"] <= 27
    p = d / ("lexicon-gb-en.txt" if british else "lexicon-us-en.txt")
    return str(p) if p.exists() else ""


def _speak_kokoro_fast(text: str) -> tuple[bytes, float] | None:
    """Try the kept-in-memory Kokoro. None means 'use the old way'."""
    if not _find_c_api() or _KOKORO.failures >= 3 or CONFIG.get("tts_kokoro_fast", True) is False:
        return None
    scale = float(CONFIG.get("tts_kokoro_length_scale") or 1.0)
    try:
        result = _KOKORO.speak(text, voice_choice()["kokoro_sid"], _kokoro_lexicon(), 1.0 / max(0.3, scale))
        _KOKORO.failures = 0
        return result
    except Exception as e:
        _KOKORO.failures += 1
        print(f"  voice: fast Kokoro failed ({e}); using the slower way for now")
        return None


def _speak_kokoro(text: str) -> bytes:
    exe, d = _find_sherpa(), _find_kokoro()
    model = d / "model.int8.onnx" if (d / "model.int8.onnx").exists() else d / "model.onnx"
    # English only: the Chinese word lists in the multi-language pack are huge and were being
    # loaded for every sentence, which made speech many times slower than it needs to be
    british = 20 <= voice_choice()["kokoro_sid"] <= 27
    lexicons = ",".join(str(p) for p in (d / ("lexicon-gb-en.txt" if british else "lexicon-us-en.txt"),) if p.exists())
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out = TMP_DIR / f"tts-{uuid.uuid4().hex[:8]}.wav"
    cmd = [str(exe), f"--kokoro-model={model}", f"--kokoro-voices={d / 'voices.bin'}",
           f"--kokoro-tokens={d / 'tokens.txt'}", f"--kokoro-data-dir={d / 'espeak-ng-data'}",
           f"--num-threads={CONFIG.get('threads', 4)}",
           f"--sid={voice_choice()['kokoro_sid']}", f"--output-filename={out}"]
    if lexicons:
        cmd.append(f"--kokoro-lexicon={lexicons}")
    if CONFIG.get("tts_kokoro_chinese") and (d / "dict").is_dir():
        cmd.append(f"--kokoro-dict-dir={d / 'dict'}")
        zh = d / "lexicon-zh.txt"
        if zh.exists():
            cmd = [c + "," + str(zh) if c.startswith("--kokoro-lexicon=") else c for c in cmd]
    if CONFIG.get("tts_kokoro_length_scale"):
        cmd.append(f"--kokoro-length-scale={CONFIG['tts_kokoro_length_scale']}")
    cmd.append(text)
    try:
        run = subprocess.run(cmd, capture_output=True, timeout=120, cwd=str(exe.parent), creationflags=NO_WINDOW)
        if not out.exists():
            err = run.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
            raise RuntimeError("Kokoro voice failed: " + " | ".join(err))
        return out.read_bytes()
    finally:
        try:
            out.unlink()
        except OSError:
            pass


_CACHE: "dict[tuple, bytes]" = {}
_CACHE_ORDER: list[tuple] = []


def _voice_key(engine: str) -> str:
    c = voice_choice()
    return str(c["kokoro_sid"]) if engine == "kokoro" else c["piper_voice"]


def preview_text() -> str:
    c, engine = voice_choice(), tts_engine()
    if engine == "kokoro":
        name = next((n for sid, n, _ in KOKORO_VOICES if sid == c["kokoro_sid"]), "Kokoro")
    else:
        name = "your fast voice"
    return f"Hi {user_name()}! This is {name}. Here's how I'll read your answers."


def speak(text: str) -> bytes:
    """Turn a piece of text into WAV audio. Anything already spoken (previews, re-reads)
    comes from a small memory cache instantly."""
    engine = tts_engine()
    if engine:
        key = (engine, _voice_key(engine), re.sub(r"\s+", " ", text).strip())
        if key in _CACHE:
            return _CACHE[key]
        audio = _speak_now(text)
        _CACHE[key] = audio
        _CACHE_ORDER.append(key)
        while len(_CACHE_ORDER) > 120:
            _CACHE.pop(_CACHE_ORDER.pop(0), None)
        return audio
    return _speak_now(text)


def prewarm_preview() -> None:
    """Make the preview for the voice you just picked in the background, so Preview is instant."""
    def work():
        try:
            speak(preview_text())
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()


def _speak_now(text: str) -> bytes:
    global _tts_proc
    engine = tts_engine()
    if not engine:
        raise RuntimeError("The offline voice is not installed. Run VOICE_SETUP.bat once.")
    text = re.sub(r"\s+", " ", text).strip()[:1500]
    if not text:
        raise RuntimeError("Nothing to say.")
    if engine == "kokoro":
        with _tts_lock:
            started = time.time()
            fast = _speak_kokoro_fast(text)
            if fast:
                audio, took = fast            # time spent speaking only, not the one-off loading
            else:
                audio = _speak_kokoro(text)
                took = time.time() - started
        seconds = max(0.1, (len(audio) - 44) / 48000)          # 24 kHz, 16-bit mono
        rtf = took / seconds                                     # 1.0 = as fast as it talks
        KOKORO_STATS["calls"] += 1
        KOKORO_STATS["last_rtf"] = round(rtf, 2)
        if rtf > float(CONFIG.get("tts_kokoro_max_slowness", 2.5)):
            KOKORO_STATS["slow_calls"] += 1
            if KOKORO_STATS["slow_calls"] >= 2 and voice_choice()["engine"] == "auto":
                KOKORO_STATS["disabled"] = True                  # too slow on this laptop: use Piper
                print(f"  voice: Kokoro is too slow here ({rtf:.1f}x slower than speech) - using Piper")
        print(f"  voice: Kokoro made {seconds:.1f} s of speech in {took:.1f} s")
        return audio
    with _tts_lock:
        for _ in range(2):   # if the running Piper has stopped, start it again once
            try:
                if _tts_proc is None or _tts_proc.poll() is not None:
                    _tts_proc = _start_piper()
                _tts_proc.stdin.write((text + "\n").encode("utf-8"))
                _tts_proc.stdin.flush()
                wav_path = Path(_tts_proc.stdout.readline().decode("utf-8", "replace").strip())
                if wav_path.is_file():
                    data = wav_path.read_bytes()
                    try:
                        wav_path.unlink()
                    except OSError:
                        pass
                    if data[:4] == b"RIFF":
                        return data
            except (OSError, ValueError):
                pass
            if _tts_proc and _tts_proc.poll() is None:
                _tts_proc.kill()
            _tts_proc = None
        return _speak_oneshot(text)   # last resort: one Piper run just for this text


def _clean(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|\([^)]*(music|noise|silence|blank)[^)]*\)", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def transcribe(wav: bytes) -> str:
    """wav = 16 kHz mono 16-bit WAV recorded by the chat page. Returns the words spoken."""
    cli, model = _find_cli(), _find_model()
    if not (cli and model):
        raise RuntimeError(status()["reason"])
    if len(wav) < 1000 or wav[:4] != b"RIFF":
        raise RuntimeError("The recording was empty. Hold the microphone button a little longer.")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"voice-{uuid.uuid4().hex[:8]}.wav"
    path.write_bytes(wav)
    cmd = [str(cli), "-m", str(model), "-f", str(path), "-nt", "-np",
           "-t", str(CONFIG.get("threads", 4)),
           "-l", CONFIG.get("voice_language", "en")]
    try:
        with _lock:
            started = time.time()
            run = subprocess.run(cmd, capture_output=True, timeout=180, cwd=str(cli.parent),
                                 creationflags=NO_WINDOW)
        if run.returncode != 0:
            err = run.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["unknown error"]
            raise RuntimeError(f"Voice typing failed: {err[0]}")
        text = _clean(run.stdout.decode("utf-8", "replace"))
        print(f"  voice: {len(wav) // 32000} s of audio -> text in {time.time() - started:.1f} s")
        return text
    except subprocess.TimeoutExpired:
        raise RuntimeError("Voice typing took too long. Try a shorter recording.")
    finally:
        try:
            path.unlink()
        except OSError:
            pass
