@echo off
title QuantaKai - Setup
cd /d "%~dp0"
echo.
echo ================================================================
echo   QuantaKai - one-time setup
echo   Needs internet. Downloads about 2.1 GB. Safe to run again.
echo ================================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
echo.
echo A summary was saved to logs\setup_report.txt
pause
