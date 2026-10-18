@echo off
REM ============================================================
REM  STOP_CHATBOT.bat - shuts the chatbot down completely.
REM  Safe to run twice; safe to run when nothing is running.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "PIDFILE=logs\chatbot.pid"
if exist "%PIDFILE%" (
    for /f "usebackq tokens=*" %%P in ("%PIDFILE%") do (
        taskkill /T /F /PID %%P >nul 2>&1
    )
    del "%PIDFILE%" >nul 2>&1
    echo Stopped the chatbot processes recorded in %PIDFILE%.
) else (
    echo No %PIDFILE% found - trying the safety net anyway.
)

REM Safety nets: kill anything left behind by a crash.
taskkill /F /IM llama-server.exe /T >nul 2>&1

REM Free port 8501 (the streamlit child) even if the pid file was stale.
for /f "tokens=5" %%O in ('netstat -ano ^| findstr :8501 ^| findstr LISTENING') do (
    taskkill /T /F /PID %%O >nul 2>&1
)

echo Done. If a chatbot browser tab is still open it will no longer respond.
pause
endlocal
