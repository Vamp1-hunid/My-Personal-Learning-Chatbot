"""ocr.py - reads the text in a picture (a screenshot of a test question, a photo of notes).

It uses the text recognition built into Windows 10 and 11 (Windows.Media.Ocr), so it
works offline and needs no download. If the loaded chat model can see pictures (a
Qwen 3.5 model with its vision file), the picture is also sent to the model itself.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import uuid

from .settings import DATA_DIR

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TMP_DIR = DATA_DIR / "tmp"

# PowerShell 5 (built into Windows) can call the Windows text-recognition engine directly.
_SCRIPT = r'''
param([string]$path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'No text-recognition language is installed in Windows.' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) { $line.Text }
$stream.Dispose()
'''


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    m = re.match(r"data:image/(png|jpe?g|webp|bmp|gif);base64,(.+)", data_url or "", re.S)
    if not m:
        raise ValueError("Not a picture the app can read (use PNG or JPG).")
    ext = "jpg" if m.group(1) in ("jpg", "jpeg") else m.group(1)
    return base64.b64decode(m.group(2)), ext


def read_text(data_url: str) -> str:
    """Return the text found in the picture ('' if none). Raises RuntimeError on failure."""
    if os.name != "nt":
        raise RuntimeError("Reading text from pictures uses Windows' built-in text recognition.")
    raw, ext = decode_data_url(data_url)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    img = TMP_DIR / f"ocr-{uuid.uuid4().hex[:8]}.{ext}"
    script = TMP_DIR / "ocr.ps1"
    try:
        img.write_bytes(raw)
        if not script.exists() or script.read_text(encoding="utf-8") != _SCRIPT:
            script.write_text(_SCRIPT, encoding="utf-8")
        run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(img)],
                             capture_output=True, timeout=90, creationflags=NO_WINDOW)
        if run.returncode != 0:
            err = run.stderr.decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError("Could not read the picture: " + (err[-1] if err else "unknown error"))
        return run.stdout.decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("Reading the picture took too long.")
    finally:
        try:
            img.unlink()
        except OSError:
            pass
