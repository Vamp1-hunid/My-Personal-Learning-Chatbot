@echo off
REM ============================================================
REM  ASK_QUESTION.bat - type one question, get one answer.
REM  No flags, no terminal knowledge needed.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    py -3.11 -c "pass" >nul 2>&1
    if not errorlevel 1 set "PY=py -3.11"
)
if not defined PY (
    if exist "C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\Mulenga Mwamba\AppData\Local\Programs\Python\Python311\python.exe"
)
if not defined PY (
    echo Could not find Python 3.11. Run SETUP_ONCE.bat first - see docs\MANUAL_STEPS.md.
    pause
    exit /b 1
)

set "Q="
set /p "Q=Type your question about the books, then press Enter: "
if "%Q%"=="" (
    echo You typed nothing. Nothing to answer.
    pause
    exit /b 0
)

"%PY%" -m src.cli --show-sources "%Q%"
echo.
pause
endlocal
