@echo off
title Stop QuantaKai
cd /d "%~dp0"
if exist "runtime\python\python.exe" (
    "runtime\python\python.exe" -m app.stop
) else (
    taskkill /F /IM llama-server.exe >nul 2>&1
    echo Engines stopped.
)
timeout /t 3 >nul
