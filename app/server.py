"""server.py - the local web server you chat through.

Start it with:   runtime\\python\\python.exe -m app.server   (START.bat does this)
It serves the chat page (ui\\index.html) at http://127.0.0.1:8000 and a small
JSON API the page uses. Only this computer can reach it (it listens on
127.0.0.1, not on your Wi-Fi network).

On start-up it also launches the search engine and your last-used chat model.
"""
from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import chat, docs, engine, library, memory, organize, runner, voice
from .settings import BOOKS_DIR, CONFIG, DATA_DIR, MODELS_DIR, UI_DIR, load_state, save_state, user_name

PORT = int(CONFIG["ui_port"])
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}

# ------------------------------------------------------------------ wallpaper
WALL_TYPES = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"),
              b"GIF8": ("gif", "image/gif"), b"RIFF": ("webp", "image/webp")}
MAX_WALL_BYTES = 15_000_000


def _wall_file():
    return next((p for p in DATA_DIR.glob("wallpaper.*") if p.suffix in (".png", ".jpg", ".gif", ".webp")), None)


def _save_wall(data_url: str) -> str:
    raw = base64.b64decode(data_url.split(",", 1)[-1], validate=False)
    if len(raw) > MAX_WALL_BYTES:
        raise ValueError("That picture is too big (15 MB at most).")
    kind = next((v for k, v in WALL_TYPES.items() if raw.startswith(k)), None)
    if not kind or (kind[0] == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("Use a PNG, JPG, GIF or WebP picture.")
    old = _wall_file()
    if old:
        old.unlink()
    (DATA_DIR / f"wallpaper.{kind[0]}").write_bytes(raw)
    return kind[0]


def _open_folder(path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # opens File Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def status() -> dict:
    books = library.load_manifest()
    return {
        "app_name": CONFIG["app_name"],
        "user_name": user_name(),                     # your nickname, if you set one
        "nickname": str(load_state().get("nickname") or ""),
        "config_name": CONFIG["user_name"],
        "wallpaper": int(_wall_file().stat().st_mtime) if _wall_file() else 0,
        "wall_dim": load_state().get("wall_dim", 35),
        "wall_blur": load_state().get("wall_blur", 0),
        "chat": {"state": engine.CHAT.state, "model": engine.CHAT.model, "error": engine.CHAT.error},
        "search": {"state": engine.EMBED.state, "error": engine.EMBED.error},
        "books": len(books),
        "passages": sum(b.get("passages", 0) for b in books.values()),
        "memories": len(memory.list_all()),
        "auto_learn": load_state().get("auto_learn", CONFIG["auto_learn"]),
        "max_model_gb": CONFIG["max_model_gb"],
        "voice": voice.status(),
        "run": runner.languages(),
        "images": {"ocr": os.name == "nt", "vision": bool(getattr(engine.CHAT, "vision", False))},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "OfflineChatbot/1.0"

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _host_ok(self) -> bool:
        # Blocks "DNS rebinding": a web page on the internet pretending to be localhost.
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            self.send_error(HTTPStatus.FORBIDDEN, "Wrong host")
            return False
        return True

    def _origin_ok(self) -> bool:
        # Blocks "cross-site request forgery": any website you visit could otherwise send
        # requests to this app in the background (for example to /api/run, which runs code).
        # Browsers always say which site a request comes from in the Origin header.
        origin = self.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            self.send_error(HTTPStatus.FORBIDDEN, "Requests from other websites are not allowed")
            return False
        return True

    def _json(self, data, status_code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(min(length, 32_000_000)).decode("utf-8"))   # room for pictures
        except ValueError:
            return {}

    # ------------------------------------------------------------ GET
    def do_GET(self):
        if not self._host_ok():
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = (UI_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            self._json(status())
        elif path == "/api/wallpaper":
            f = _wall_file()
            if not f:
                self.send_error(404)
                return
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", next(v[1] for v in WALL_TYPES.values() if v[0] == f.suffix[1:]))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/models":
            self._json({"models": engine.list_models(), "active": engine.CHAT.model,
                        "state": engine.CHAT.state, "max_gb": CONFIG["max_model_gb"]})
        elif path == "/api/books":
            self._json({"books": library.list_books(), "progress": library.PROGRESS,
                        "categories": library.all_categories(),
                        "category_groups": library.category_groups(), "queue": list(library.QUEUE)})
        elif path == "/api/memory":
            self._json({"memories": list(reversed(memory.list_all()))})
        elif path == "/api/voices":
            self._json(voice.voice_list())
        elif path == "/api/chats":
            self._json({"chats": chat.list_conversations()})
        elif m := re.fullmatch(r"/api/chats/([\w-]+)", path):
            conv = chat.load_conversation(m.group(1))
            found = conv["messages"] or conv.get("docs")
            self._json(conv if found else {"error": "not found"}, 200 if found else 404)
        else:
            self.send_error(404)

    # ------------------------------------------------------------ POST
    def do_POST(self):
        if not (self._host_ok() and self._origin_ok()):
            return
        path = urlparse(self.path).path
        if path == "/api/voice/transcribe":      # raw WAV audio, not JSON
            self._transcribe()
            return
        data = self._body()
        if path == "/api/chat":
            self._stream_reply(data)
        elif path == "/api/docs":                     # attach a document to a chat
            conv = chat.load_conversation(str(data.get("conv_id") or "") or None)
            try:
                doc = docs.add(conv, str(data.get("name", "document.txt")), docs.decode_upload(str(data.get("data", ""))))
            except docs.DocError as e:
                self._json({"ok": False, "error": str(e)}, 200)
                return
            except Exception as e:                    # an unusual file the readers choked on
                self._json({"ok": False, "error": f"Could not read that file ({type(e).__name__})."}, 200)
                return
            chat.save_conversation(conv)
            self._json({"ok": True, "conv_id": conv["id"], "doc": doc, "docs": conv["docs"]})
        elif path == "/api/models/load":
            name = str(data.get("name", ""))
            threading.Thread(target=engine.load_chat_model, args=(name,), daemon=True).start()
            self._json({"ok": True})
        elif path == "/api/books/scan":
            if engine.EMBED.state != "ready":
                self._json({"ok": False, "error": engine.EMBED.error or "Search engine not ready."}, 409)
                return
            threading.Thread(target=library.scan_and_add, daemon=True).start()
            self._json({"ok": True})
        elif path == "/api/books/add":
            if engine.EMBED.state != "ready":
                self._json({"ok": False, "error": engine.EMBED.error or "Search engine not ready."}, 409)
                return
            files = data.get("files") or ([data["file"]] if data.get("file") else [])
            self._json({"ok": True, "queued": library.request_add([str(f) for f in files])})
        elif path == "/api/books/category":
            try:
                library.set_category(str(data.get("file", "")), str(data.get("category", "")))
                self._json({"ok": True})
            except ValueError as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif path == "/api/run":
            self._json(runner.run(str(data.get("code", "")), str(data.get("language", ""))))
        elif path == "/api/voices":
            try:
                voice.set_voice(str(data.get("engine", "auto")), data.get("id"))
                voice.prewarm_preview()            # so the Preview button plays straight away
                self._json({"ok": True, **voice.voice_list()})
            except ValueError as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif path == "/api/voice/speak":
            self._speak(voice.preview_text() if data.get("preview") else str(data.get("text", "")))
        elif path == "/api/memory":
            item = memory.add(str(data.get("text", "")), source="manual")
            self._json({"ok": bool(item), "item": item})
        elif path == "/api/settings":
            if "auto_learn" in data:
                save_state(auto_learn=bool(data["auto_learn"]))
            if "nickname" in data:
                save_state(nickname=" ".join(str(data["nickname"]).split())[:40])
            if "wall_dim" in data:
                save_state(wall_dim=max(0, min(90, int(data["wall_dim"]))))
            if "wall_blur" in data:
                save_state(wall_blur=max(0, min(30, int(data["wall_blur"]))))
            self._json(status())
        elif path == "/api/wallpaper":
            try:
                kind = _save_wall(str(data.get("data", "")))
                self._json({"ok": True, "type": kind, **status()})
            except (ValueError, OSError) as e:
                self._json({"ok": False, "error": str(e)}, 400)
        elif path == "/api/open-folder":
            folder = {"books": BOOKS_DIR, "models": MODELS_DIR}.get(data.get("which"))
            if folder:
                _open_folder(folder)
            self._json({"ok": bool(folder)})
        else:
            self.send_error(404)

    def do_PUT(self):
        if not (self._host_ok() and self._origin_ok()):
            return
        m = re.fullmatch(r"/api/memory/(\w+)", urlparse(self.path).path)
        if not m:
            return self.send_error(404)
        self._json({"ok": memory.update(m.group(1), str(self._body().get("text", "")))})

    def do_DELETE(self):
        if not (self._host_ok() and self._origin_ok()):
            return
        path = urlparse(self.path).path
        if path == "/api/wallpaper":
            f = _wall_file()
            if f:
                f.unlink()
            self._json({"ok": True})
        elif m := re.fullmatch(r"/api/memory/(\w+)", path):
            self._json({"ok": memory.delete(m.group(1))})
        elif m := re.fullmatch(r"/api/chats/([\w-]+)", path):
            self._json({"ok": chat.delete_conversation(m.group(1))})
        elif m := re.fullmatch(r"/api/docs/([\w-]+)/(\w+)", path):
            conv = chat.load_conversation(m.group(1))
            ok = docs.remove(conv, m.group(2))
            if ok:
                chat.save_conversation(conv)
            self._json({"ok": ok, "docs": conv.get("docs", [])})
        else:
            self.send_error(404)

    # ------------------------------------------------------------ voice typing
    def _transcribe(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 30_000_000:          # 30 MB is about 15 minutes of speech
            self._json({"ok": False, "error": "The recording was empty or too long."}, 400)
            return
        audio = self.rfile.read(length)
        try:
            self._json({"ok": True, "text": voice.transcribe(audio)})
        except RuntimeError as e:
            self._json({"ok": False, "error": str(e)}, 200)

    def _speak(self, text: str) -> None:
        try:
            audio = voice.speak(text)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self._json({"ok": False, "error": str(e)}, 503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(audio)

    # ------------------------------------------------------------ streaming
    def _stream_reply(self, data: dict) -> None:
        """Send the reply as Server-Sent Events: one 'data: {...}' line per piece."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        events = chat.reply(data.get("conv_id"), data.get("mode", "chat"), data.get("style", "quick"),
                            str(data.get("message", "")), bool(data.get("simpler")),
                            str(data.get("book_category", "auto")),
                            [str(x) for x in (data.get("images") or [])][:4],
                            turn=str(data.get("turn") or "") or None, rewind=str(data.get("rewind") or "") or None,
                            voice=bool(data.get("voice")))
        try:
            for event in events:
                self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # you pressed Stop or closed the tab
        finally:
            events.close()
        self.close_connection = True


def _start_engines(model: str | None) -> None:
    engine.start_embed_engine()
    library.INDEX.reload()
    if model:
        engine.load_chat_model(model)
    else:
        engine.CHAT.state = "error"
        engine.CHAT.error = (f"No usable model in the models folder (each must be a .gguf file "
                             f"of {CONFIG['max_model_gb']} GB or less).")


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantaKai")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    engine.kill_leftover_engines()
    atexit.register(engine.stop_all)
    engine.remember_pid("ui", os.getpid())   # lets STOP.bat find this window's program
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Port {PORT} is busy - the chatbot may already be running. Run STOP.bat, then try again.")
        sys.exit(1)
    httpd.daemon_threads = True

    organize.tidy_downloads()             # files dropped in "new stuff" go to the right folders
    voice.start_unpacking()               # unpack voice engines dropped into the voice folder
    model = engine.pick_startup_model()
    threading.Thread(target=_start_engines, args=(model,), daemon=True).start()

    url = f"http://127.0.0.1:{PORT}/"
    print("=" * 60)
    print(f"  {CONFIG['app_name']} is running at {url}")
    print(f"  Loading model: {model or 'none found'}")
    print("  Keep this window open. Close it (or run STOP.bat) to quit.")
    print("=" * 60)
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop_all()
        httpd.server_close()


if __name__ == "__main__":
    main()
