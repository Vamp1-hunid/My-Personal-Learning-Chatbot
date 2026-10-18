@echo off
REM ============================================================
REM  MAKE_DESKTOP_SHORTCUT.bat - puts a "Book Chatbot" icon on
REM  the Desktop that launches START_CHATBOT.bat.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateDesktopShortcut('Book Chatbot.lnk');" ^
  "$s.TargetPath='%~dp0START_CHATBOT.bat';" ^
  "$s.WorkingDirectory='%~dp0.';" ^
  "$s.IconLocation='%SystemRoot%\System32\shell32.dll,17';" ^
  "$s.Description='Start the Book Grounded Chatbot (offline).';" ^
  "$s.Save();" ^
  "Write-Host 'Created Desktop shortcut: Book Chatbot'"

echo If the shortcut does not appear, your OneDrive Desktop may be redirected -
echo look inside OneDrive\Desktop as well.
pause
endlocal
