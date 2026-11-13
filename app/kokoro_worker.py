"""
QuantaKai - Kokoro voice worker.

Runs as its own small program next to QuantaKai. It loads the Kokoro voice model ONCE,
then keeps it in memory and turns each line of text it is sent into speech. Before this,
the whole 114 MB model was reloaded for every single sentence, which is why Kokoro was so slow.

It runs in a separate process on purpose: if the voice library ever crashes, only this
helper stops, and QuantaKai simply starts it again (or falls back to the old way).

Talking to it (one JSON object per line):
    in : {"text": "...", "sid": 3, "speed": 1.0, "out": "C:/.../tts-1234.wav"}
    out: @@{"ok": true, "seconds": 0.8, "audio_seconds": 2.6}
Lines that do not start with @@ are just messages from the library and are ignored.

Usage: python -I kokoro_worker.py <folder with sherpa-onnx-c-api.dll> <kokoro folder> <lexicon file or -> <threads>
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import time
from ctypes import POINTER, Structure, c_char_p, c_float, c_int32, c_void_p
from pathlib import Path


def say(obj: dict) -> None:
    sys.stdout.write("@@" + json.dumps(obj) + "\n")
    sys.stdout.flush()


# ---- The exact layouts from sherpa-onnx v1.13.5 include/sherpa-onnx/c-api/c-api.h ----
class Vits(Structure):
    _fields_ = [("model", c_char_p), ("lexicon", c_char_p), ("tokens", c_char_p), ("data_dir", c_char_p),
                ("noise_scale", c_float), ("noise_scale_w", c_float), ("length_scale", c_float),
                ("dict_dir", c_char_p)]


class Matcha(Structure):
    _fields_ = [("acoustic_model", c_char_p), ("vocoder", c_char_p), ("lexicon", c_char_p), ("tokens", c_char_p),
                ("data_dir", c_char_p), ("noise_scale", c_float), ("length_scale", c_float), ("dict_dir", c_char_p)]


class Kokoro(Structure):
    _fields_ = [("model", c_char_p), ("voices", c_char_p), ("tokens", c_char_p), ("data_dir", c_char_p),
                ("length_scale", c_float), ("dict_dir", c_char_p), ("lexicon", c_char_p), ("lang", c_char_p)]


class Kitten(Structure):
    _fields_ = [("model", c_char_p), ("voices", c_char_p), ("tokens", c_char_p), ("data_dir", c_char_p),
                ("length_scale", c_float)]


class Zipvoice(Structure):
    _fields_ = [("tokens", c_char_p), ("encoder", c_char_p), ("decoder", c_char_p), ("vocoder", c_char_p),
                ("data_dir", c_char_p), ("lexicon", c_char_p), ("feat_scale", c_float), ("t_shift", c_float),
                ("target_rms", c_float), ("guidance_scale", c_float)]


class Pocket(Structure):
    _fields_ = [("lm_flow", c_char_p), ("lm_main", c_char_p), ("encoder", c_char_p), ("decoder", c_char_p),
                ("text_conditioner", c_char_p), ("vocab_json", c_char_p), ("token_scores_json", c_char_p),
                ("voice_embedding_cache_capacity", c_int32)]


class Supertonic(Structure):
    _fields_ = [("duration_predictor", c_char_p), ("text_encoder", c_char_p), ("vector_estimator", c_char_p),
                ("vocoder", c_char_p), ("tts_json", c_char_p), ("unicode_indexer", c_char_p),
                ("voice_style", c_char_p)]


class ModelConfig(Structure):
    _fields_ = [("vits", Vits), ("num_threads", c_int32), ("debug", c_int32), ("provider", c_char_p),
                ("matcha", Matcha), ("kokoro", Kokoro), ("kitten", Kitten), ("zipvoice", Zipvoice),
                ("pocket", Pocket), ("supertonic", Supertonic)]


class TtsConfig(Structure):
    _fields_ = [("model", ModelConfig), ("rule_fsts", c_char_p), ("max_num_sentences", c_int32),
                ("rule_fars", c_char_p), ("silence_scale", c_float)]


class GeneratedAudio(Structure):
    _fields_ = [("samples", POINTER(c_float)), ("n", c_int32), ("sample_rate", c_int32)]


def b(path) -> bytes | None:
    return str(path).encode("utf-8") if path else None


def write_wav(path: str, samples, n: int, rate: int) -> None:
    """Float samples in [-1, 1] -> 16-bit mono WAV."""
    try:
        import numpy as np
        pcm = (np.clip(np.ctypeslib.as_array(samples, shape=(n,)), -1.0, 1.0) * 32767).astype("<i2").tobytes()
    except Exception:
        from array import array
        pcm = array("h", (int(max(-1.0, min(1.0, samples[i])) * 32767) for i in range(n))).tobytes()
    header = (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
              struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)))
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(header + pcm)
    os.replace(tmp, path)


def main() -> None:
    lib_dir, kdir, lexicon, threads = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4])
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(lib_dir))
    lib = ctypes.CDLL(str(lib_dir / ("sherpa-onnx-c-api.dll" if os.name == "nt" else "libsherpa-onnx-c-api.so")))
    lib.SherpaOnnxCreateOfflineTts.argtypes = [POINTER(TtsConfig)]
    lib.SherpaOnnxCreateOfflineTts.restype = c_void_p
    lib.SherpaOnnxOfflineTtsSampleRate.argtypes = [c_void_p]
    lib.SherpaOnnxOfflineTtsSampleRate.restype = c_int32
    lib.SherpaOnnxOfflineTtsGenerate.argtypes = [c_void_p, c_char_p, c_int32, c_float]
    lib.SherpaOnnxOfflineTtsGenerate.restype = POINTER(GeneratedAudio)
    lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio.argtypes = [POINTER(GeneratedAudio)]
    lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio.restype = None

    model = kdir / "model.int8.onnx" if (kdir / "model.int8.onnx").exists() else kdir / "model.onnx"
    cfg = TtsConfig()                       # ctypes fills every field with zero / NULL, like memset
    k = cfg.model.kokoro
    keep = [b(model), b(kdir / "voices.bin"), b(kdir / "tokens.txt"), b(kdir / "espeak-ng-data"),
            b(lexicon) if lexicon and lexicon != "-" else None, b"cpu"]
    k.model, k.voices, k.tokens, k.data_dir, k.lexicon = keep[0], keep[1], keep[2], keep[3], keep[4]
    k.length_scale = 1.0
    cfg.model.num_threads = threads
    cfg.model.debug = 0
    cfg.model.provider = keep[5]
    cfg.max_num_sentences = 1
    cfg.silence_scale = 0.2

    started = time.time()
    tts = lib.SherpaOnnxCreateOfflineTts(ctypes.byref(cfg))
    if not tts:
        say({"ready": False, "error": "The Kokoro voice could not be loaded."})
        return
    rate = lib.SherpaOnnxOfflineTtsSampleRate(tts)
    say({"ready": True, "sample_rate": rate, "load_seconds": round(time.time() - started, 2)})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            t0 = time.time()
            audio = lib.SherpaOnnxOfflineTtsGenerate(tts, str(job["text"]).encode("utf-8"),
                                                     int(job.get("sid", 0)), float(job.get("speed", 1.0)))
            if not audio:
                say({"ok": False, "error": "Kokoro returned no audio."})
                continue
            a = audio.contents
            n, sr = a.n, a.sample_rate
            if n > 0:
                write_wav(job["out"], a.samples, n, sr)
            lib.SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio)
            if n <= 0:
                say({"ok": False, "error": "Kokoro made empty audio."})
                continue
            say({"ok": True, "seconds": round(time.time() - t0, 3), "audio_seconds": round(n / sr, 3)})
        except Exception as e:  # keep running for the next sentence
            say({"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        say({"ready": False, "error": f"{type(e).__name__}: {e}"})
