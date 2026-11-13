"""smoke_test.py - checks the whole app works, without real models.

Run it from the project folder:
    runtime\\python\\python.exe tests\\smoke_test.py

It copies the app into a temporary folder, uses the fake engine instead of
llama.cpp, makes a small test PDF, then tests: start-up, the 5 GB size limit,
adding a book, a study answer with sources, a chat answer, "remember that...",
auto-learn, the memory page and saved chats. Your real folders are not touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
failures = []


def check(name, condition, detail=""):
    print(("  PASS  " if condition else "  FAIL  ") + name + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def call(method, path, data=None, timeout=30):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def chat(message, mode="chat", style="quick", conv_id=None, simpler=False):
    req = urllib.request.Request(BASE + "/api/chat", method="POST",
                                 data=json.dumps({"message": message, "mode": mode, "style": style,
                                                  "conv_id": conv_id, "simpler": simpler}).encode(),
                                 headers={"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(req, timeout=60) as r:
        for raw in r:
            line = raw.decode().strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def wait_for(fn, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main():
    tmp = Path(tempfile.mkdtemp(prefix="quantakai-test-"))
    print(f"Testing in {tmp}")
    for item in ("app", "ui", "tests", "config.json"):
        src = SRC / item
        (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp / item)
    cfg = json.loads((tmp / "config.json").read_text())
    cfg.update(ui_port=PORT, chat_port=8766, embed_port=8767,
               study_min_score=0.05)  # the fake engine's vectors score lower than real ones
    (tmp / "config.json").write_text(json.dumps(cfg))
    models = tmp / "models"
    models.mkdir()
    (models / cfg["default_model"]).write_bytes(b"GGUF" + b"\0" * 1000)
    (models / cfg["embedding_model"]).write_bytes(b"GGUF" + b"\0" * 1000)
    (models / "broken-download.gguf").write_bytes(b"\0" * 1000)
    with open(models / "too-big-model.gguf", "wb") as f:   # 6 GB "sparse" file, uses no real disk space
        f.write(b"GGUF")
        f.truncate(6 * 1024 ** 3)

    import pymupdf
    books = tmp / "books"
    books.mkdir()
    doc = pymupdf.open()
    lines = ("Overfitting happens when a machine learning model learns the training data too closely, "
             "including its noise, so it performs badly on new unseen data. ") * 12
    for i in range(3):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), f"Chapter {i + 1}. " + lines, fontsize=10)
    doc.save(books / "Intro_to_ML.pdf")

    env = dict(os.environ, QUANTAKAI_FAKE_ENGINE="1", PYTHONUNBUFFERED="1",
               QUANTAKAI_FAKE_DUMP=str(Path(tmp) / "last_request.json"))
    # Start the COPY's app (the portable Python always looks in the real folder first, so point it at the copy).
    boot = (f"import sys, runpy; sys.path.insert(0, r'{tmp}'); sys.argv = ['app.server', '--no-browser']; "
            "runpy.run_module('app.server', run_name='__main__')")
    server = subprocess.Popen([sys.executable, "-c", boot], cwd=tmp, env=env)
    try:
        check("web page loads", wait_for(lambda: urllib.request.urlopen(BASE + "/", timeout=2).status == 200))
        check("chat model and search engine start",
              wait_for(lambda: call("GET", "/api/status")["chat"]["state"] == "ready"
                       and call("GET", "/api/status")["search"]["state"] == "ready"))
        listed = {m["name"]: m for m in call("GET", "/api/models")["models"]}
        check("5 GB limit blocks the 6 GB model", listed["too-big-model.gguf"]["allowed"] is False)
        check("broken download is blocked", listed["broken-download.gguf"]["allowed"] is False)
        check("search model hidden from chat picker", cfg["embedding_model"] not in listed)
        call("POST", "/api/models/load", {"name": "too-big-model.gguf"})
        check("loading the 6 GB model is refused",
              wait_for(lambda: "limit" in call("GET", "/api/status")["chat"]["error"], 10))
        call("POST", "/api/models/load", {"name": cfg["default_model"]})
        check("switching back to the 3B model works",
              wait_for(lambda: call("GET", "/api/status")["chat"]["state"] == "ready"))

        call("POST", "/api/books/scan")
        check("book gets added", wait_for(lambda: call("GET", "/api/status")["books"] == 1))
        wait_for(lambda: not call("GET", "/api/books")["progress"]["running"])
        book = call("GET", "/api/books")["books"][0]
        check("book has pages and passages", book.get("pages") == 3 and book.get("passages", 0) > 0, str(book))

        ev = chat("What is overfitting in machine learning?", mode="study", style="explain")
        types = [e["type"] for e in ev]
        sources = next((e["sources"] for e in ev if e["type"] == "sources"), [])
        text = "".join(e["text"] for e in ev if e["type"] == "token")
        check("study answer streams", types[0] == "meta" and "token" in types and types[-1] == "done", str(types))
        check("study answer has book sources with page numbers", sources and sources[0]["page"] >= 1, str(sources)[:200])
        check("study answer cites [1]", "[1]" in text, text)
        conv = next(e["conv_id"] for e in ev if e["type"] == "meta")
        ev2 = chat("", mode="study", style="quick", conv_id=conv, simpler=True)
        check("'simpler please' reuses the same sources",
              next((e["sources"] for e in ev2 if e["type"] == "sources"), None) == sources)

        ev = chat("Remember that my statistics exam is on 3 December")
        check("'remember that' saves a memory", any(e["type"] == "memory" and e["saved"] for e in ev))
        ev = chat("Hi! I am a second-year data science student.")
        check("chat answer streams", "".join(e.get("text", "") for e in ev).startswith("Hello"))
        check("auto-learn saves a fact",
              wait_for(lambda: any(m["source"] == "auto" for m in call("GET", "/api/memory")["memories"]), 15))
        mems = call("GET", "/api/memory")["memories"]
        target = mems[0]["id"]
        call("PUT", f"/api/memory/{target}", {"text": "The user likes short answers."})
        check("memory can be edited",
              any(m["text"] == "The user likes short answers." for m in call("GET", "/api/memory")["memories"]))
        call("DELETE", f"/api/memory/{target}")
        check("memory can be deleted", all(m["id"] != target for m in call("GET", "/api/memory")["memories"]))

        chats = call("GET", "/api/chats")["chats"]
        check("conversations are saved", len(chats) == 3, str(chats))
        saved = call("GET", f"/api/chats/{conv}")
        check("saved chat keeps sources", saved["messages"][1]["sources"] == sources)

        ev = chat("", mode="create", style="adventure")
        check("an empty adventure message is refused by the server", any(e["type"] == "error" for e in ev))
        ev = chat("A detective story in Lusaka", mode="create", style="adventure")
        story = "".join(e.get("text", "") for e in ev if e["type"] == "token")
        check("adventure scene ends with three choices", story.count("**") >= 6 and "What do you do?" in story, story[:120])
        adv = next(e["conv_id"] for e in ev if e["type"] == "meta")
        ev = chat("I choose 2: Bribe the guard", mode="create", style="adventure", conv_id=adv)
        saved = call("GET", f"/api/chats/{adv}")["messages"]
        check("adventure continues in the same chat", len(saved) == 4 and saved[-1]["style"] == "adventure", str(len(saved)))

        import base64
        ref = "The Copper Road. Nalu walked the copper road toward Kitwe with the stolen key."
        up = call("POST", "/api/docs", {"conv_id": adv, "name": "my_story.txt",
                                        "data": base64.b64encode(ref.encode()).decode()})
        check("a reference document can be attached to a story", up.get("ok") is True, str(up))
        chat("Continue my story", mode="create", style="story", conv_id=adv)
        sent = json.loads((Path(tmp) / "last_request.json").read_text(encoding="utf-8"))
        system = sent["messages"][0]["content"]
        check("the story uses the attached document as its source", "Reference material" in system and "Nalu" in system)

        r = call("POST", "/api/books/subjects", {"action": "add", "name": "Lecture slides", "group": "Study"})
        check("a subject of your own can be added", r.get("ok") and "Lecture slides" in r["categories"], str(r)[:150])
        r = call("POST", "/api/books/subjects", {"action": "rename", "name": "Mathematics", "new_name": "Maths"})
        check("a built-in subject can be renamed", r.get("ok") and "Maths" in r["categories"] and "Mathematics" not in r["categories"])
        r = call("POST", "/api/books/subjects", {"action": "delete", "name": "Lecture slides"})
        check("your own subject can be deleted", r.get("ok") and "Lecture slides" not in r["categories"])

        bad = urllib.request.Request(BASE + "/api/status", headers={"Host": "evil.example:8765"})
        try:
            urllib.request.urlopen(bad, timeout=5)
            check("requests from other web sites are blocked", False)
        except urllib.error.HTTPError as e:
            check("requests from other web sites are blocked", e.code == 403)
    finally:
        server.terminate()
        server.wait(timeout=10)
        time.sleep(0.5)
        subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0, r'%s'); from app import engine; engine.kill_leftover_engines()" % tmp],
                       cwd=tmp, env=env)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("ALL TESTS PASSED" if not failures else f"{len(failures)} TEST(S) FAILED: {', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
