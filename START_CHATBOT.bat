@echo off
REM ============================================================
REM  START_CHATBOT.bat - double-click to start the book chatbot.
REM  Works offline. Never edit this file unless you know why.
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
    echo Could not find Python 3.11 on this computer.
    echo Install Python 3.11 64-bit from python.org, then run SETUP_ONCE.bat once.
    echo See docs\MANUAL_STEPS.md for exact steps.
    echo.
    pause
    exit /b 1
)

%PY% launcher\launch_chatbot.py
echo.
pause
endlocal
