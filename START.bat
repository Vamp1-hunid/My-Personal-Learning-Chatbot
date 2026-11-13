@echo off
title QuantaKai
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
    echo QuantaKai is not set up yet. Double-click SETUP.bat first.
    pause
    exit /b 1
)
"runtime\python\python.exe" -m app.server
if errorlevel 1 pause
