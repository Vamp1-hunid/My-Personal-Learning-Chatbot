"""src/cli.py — CLI chatbot.

Usage:
  python -m src.cli "question text"
  python -m src.cli --json "question text"
  python -m src.cli --top-k 3 --show-sources "question"

Launch Ollama + indexes before running. Memory-safe: nothing heavy is loaded
until the first question is asked; generation happens through Ollama (a
separate process) so aborting with Ctrl+C does not thread-rippling.
"""
from __future__ import annotations

import json
import sys

from src.generate import answer


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) < 2:
        print("usage: python -m src.cli [--json] [--top-k 3] \"question\"")
        return 0

    args = sys.argv[1:]
    show_json = "--json" in args
    show_sources = "--show-sources" in args
    top_k = None
    if "--top-k" in args:
        i = args.index("--top-k")
        top_k = int(args[i + 1])
        del args[i:i + 2]
    question = " ".join(a for a in args if not a.startswith("--")).strip().strip('"').strip("'")
    if not question:
        print("empty question")
        return 1

    payload = answer(question, top_k=top_k)
    if show_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload["answer"])
        if payload["insufficient_evidence"]:
            print("[insufficient-evidence]")
        if show_sources:
            for s in payload["sources"]:
                print(f"  - {s['book_id']} p.{s['page']}  {s['chunk_id']}")
        if "conflicts" in payload:
            for c in payload["conflicts"]:
                print("  [conflict]", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
