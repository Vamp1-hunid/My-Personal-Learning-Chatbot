QUANTAKAI  (personal offline chatbot)
=====================================

First time:   double-click SETUP.bat   (needs internet once, about 2.1 GB)
Every time:   double-click START.bat   (the chat page opens in your browser)
To quit:      close the black START window, or double-click STOP.bat
Voice typing: double-click VOICE_SETUP.bat once (needs internet, about 230 MB)

The folder is self-contained: it carries its own Python, engine and models.
You can move or copy the whole QuantaKai folder anywhere (another drive,
a USB disk, another Windows PC) and START.bat still works. Close it first.

Folders
  app\        the Python program (server, engines, library, memory, chat)
  ui\         index.html - the chat page you see in the browser
  books\      put PDF, EPUB, Word (.docx), PowerPoint (.pptx), .txt or .md files
              here, then press "Add new books" in Library
  models\     .gguf model files. Any file of 5 GB or less appears in the picker
  engine\     llama.cpp (llama-server.exe) - runs the models
  runtime\    portable Python (python\) and its two packages (wheels\)
  data\       your book index, memories and saved chats (never leaves the PC)
  logs\       setup report and engine logs, for troubleshooting
  scripts\    setup.ps1, used by SETUP.bat
  tests\      smoke_test.py checks the app without real models
  voice\      whisper.cpp + speech model for offline voice typing (VOICE_SETUP.bat)

The full step-by-step build guide is BUILD_GUIDE.html.
Back up the data\ folder to keep your memories, chats and book index.
