@echo off
title QuantaKai - voice setup
cd /d "%~dp0"
echo Setting up offline voice typing (needs internet once, about 230 MB)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\setup_voice.ps1"
echo.
pause
