"""fake_llama_server.py - a stand-in for llama-server, used only by the automatic tests.

It answers the same web addresses as the real engine (/health,
/v1/chat/completions, /v1/embeddings) with simple made-up results, so the
whole app can be tested without downloading any models. You never run this
yourself; tests\\smoke_test.py starts it for you.
"""
import hashlib
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

args = sys.argv[1:]
PORT = int(args[args.index("--port") + 1])
EMBEDDINGS = "--embeddings" in args
DIM = 384


def vector(text: str) -> list[float]:
    text = text.replace("Represent this sentence for searching relevant passages: ", "")
    v = [0.0] * DIM
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


def answer_for(messages: list[dict]) -> str:
    last = messages[-1]["content"]
    if "Facts:" in last:
        return "- The user is studying data science at university." if "I am" in last or "I'm" in last else "- NONE"
    if "What do you do?" in str(messages[0].get("content", "")):      # Create > Adventure
        return ("*Chapter 1 - The night market - a stolen map*\n\nRain drums on the tin roofs.\n\n"
                "### What do you do?\n1. **Follow the courier** - Risk being seen in the crowd.\n"
                "2. **Bribe the guard** - Spend your last coins for a name.\n3. **Read the map** - Trust a stranger's code.")
    if "Book passages:" in last:
        return "Overfitting means a model memorises the training data instead of learning the pattern [1]. It then does badly on new data [1]."
    return "Hello! I am a test reply from the fake engine. Everything is connected."


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "nope"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path == "/v1/embeddings" and EMBEDDINGS:
            inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
            self._send({"data": [{"index": i, "embedding": vector(t)} for i, t in enumerate(inputs)]})
            return
        if self.path == "/v1/chat/completions" and not EMBEDDINGS:
            import os
            dump = os.environ.get("QUANTAKAI_FAKE_DUMP")
            if dump:                      # lets tests check what the app sent to the model
                with open(dump, "w", encoding="utf-8") as f:
                    json.dump(body, f)
            text = answer_for(body["messages"])
            if not body.get("stream"):
                self._send({"choices": [{"message": {"content": text}}]})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for word in re.findall(r"\S+\s*", text):
                chunk = {"choices": [{"delta": {"content": word}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.02)
            final = {"choices": [], "timings": {"predicted_per_second": 9.5, "prompt_per_second": 60.0}}
            self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self._send({"error": "wrong endpoint"}, 404)


if __name__ == "__main__":
    time.sleep(0.5)  # pretend to load a model
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
