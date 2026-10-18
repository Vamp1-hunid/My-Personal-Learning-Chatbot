@echo off
REM ============================================================
REM  SETUP_ONCE.bat - run this ONCE, while you have internet.
REM  After it finishes, the chatbot works with NO network at all.
REM  Everything is resumable: if a step fails, fix it and re-run.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo [1/6] Finding Python 3.11...
set "PY311="
py -3.11 -c "pass" >nul 2>&1
if not errorlevel 1 set "PY311=py -3.11"
if not defined PY311 (
    if exist "C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe" set "PY311=C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe"
)
if not defined PY311 (
    echo Could not find Python 3.11. Install "Python 3.11.x Windows installer 64-bit"
    echo from python.org first, then re-run this file. Do NOT use the default
    echo python on this machine - it is a 3.15 beta that cannot run this project.
    pause
    exit /b 1
)
echo       OK: %PY311%

echo.
echo [2/6] Creating the virtual environment .venv (skip if it exists)...
if not exist ".venv\Scripts\python.exe" (
    %PY311% -m venv .venv
    if errorlevel 1 (
        echo Failed to create .venv. See docs\MANUAL_STEPS.md.
        pause
        exit /b 1
    )
)
set "VPY=.venv\Scripts\python.exe"

echo.
echo [3/6] Installing pinned packages...
echo       (torch is installed from the CPU-only index: the +cpu wheel is ~200 MB,
echo        the default PyPI wheel bundles CUDA and is ~2.4 GB - that is what
echo        timed out before.)
"%VPY%" -m pip install --upgrade pip --default-timeout=120 --retries 10
"%VPY%" -m pip install torch==2.4.1+cpu --index-url https://download.pytorch.org/whl/cpu --default-timeout=120 --retries 10
if errorlevel 1 (
    echo torch CPU wheel failed to download. Re-run SETUP_ONCE.bat when the
    echo network is better - pip resumes from cache. Continuing with the rest.
)
for %%F in (requirements.txt) do (
    "%VPY%" -m pip install -r "%%F" --default-timeout=120 --retries 10
    if errorlevel 1 echo Some packages failed to install. Re-run SETUP_ONCE.bat.
)

echo.
echo [4/6] Pre-downloading the embedding model into models\hf_cache (offline later)...
set "HF_HOME=%cd%\models\hf_cache"
"%VPY%" -c "import os; os.makedirs(os.path.join('models','hf_cache'),exist_ok=True); from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41', cache_folder=os.path.join('models','hf_cache')); print('embedding model cached for offline use')"
if errorlevel 1 echo Embedding model download FAILED - retrieval will not work offline until you retry this step online.

echo.
echo [5/6] Checking the generation model (llama-server + Qwen GGUF)...
set "GENOK=0"
if exist "tools\llama.cpp\llama-server.exe" if exist "models\qwen2.5-0.5b-instruct-q4_k_m.gguf" set "GENOK=1"
if "%GENOK%"=="1" (
    echo       OK: llama-server.exe and the GGUF are in place.
) else (
    echo GENERATION MODEL MISSING - the chatbot still works in DEMO extractive mode.
    echo To get full model-written answers, download BOTH of these ^(see docs\MANUAL_STEPS.md^):
    echo   1. llama.cpp Windows zip, the plain "avx" build - NOT avx2, NOT avx512
    echo      ^(^this CPU has no AVX2 - an avx2 build crashes with "illegal instruction"^)
    echo      from: https://github.com/ggml-org/llama.cpp/releases
    echo      unzip so that this exact file exists:  tools\llama.cpp\llama-server.exe
    echo   2. qwen2.5-0.5b-instruct-q4_k_m.gguf  ^(about 350 MB^)
    echo      from the official Qwen repo on Hugging Face
    echo      ^(Qwen/Qwen2.5-0.5B-Instruct-GGUF, Q4_K_M variant^)
    echo      save it as exactly:                 models\qwen2.5-0.5b-instruct-q4_k_m.gguf
    echo The app runs fine without them - just labelled DEMO mode.
)

echo.
echo [6/6] Build the search index now?
echo       WARNING: on this laptop ^(4-core APU + spinning HDD^) indexing the 15 books
echo       is a MULTI-HOUR job. It is safe to leave the laptop plugged in and walk away.
echo       It is resumable: re-running SETUP_ONCE.bat later can continue where it stopped.
echo       You can also skip and build later with: python -m src.ingest / chunk / embed / index
choice /C YN /M "Build the index now"
if errorlevel 2 (
    echo Skipped. When ready, run: launcher\build_index.bat  ^(or see docs\MANUAL_STEPS.md^)
) else (
    echo Building ingest -^> chunk -^> embed -^> index. This can take hours. Do not close this window.
    "%VPY%" src\ingest.py
    "%VPY%" src\chunk.py
    "%VPY%" src\embed.py
    "%VPY%" src\index.py
    echo Index build finished. If any line above showed an error, fix it and re-run SETUP_ONCE.bat.
)

echo.
echo Final health check:
"%VPY%" src\doctor.py
echo.
echo Setup complete. From now on just double-click START_CHATBOT.bat - it works offline.
pause
endlocal
