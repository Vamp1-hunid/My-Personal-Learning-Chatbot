"""build_docs.py - builds QuantaKai's documentation from the real source files.

    python tools/build_docs.py

Writes:
    BUILD_GUIDE.html   the complete from-scratch build guide (every file, every step)
    docs/REPORT.html   the project report (design, decisions, testing, results)
    docs/manifest.json every source file with its size, line count and SHA-256

Because the guide reads each file from disk, the code it shows is always exactly the
code in this folder. Re-run this script after changing any file.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from docshell import Doc, E  # noqa: E402
from filespecs import FILES  # noqa: E402
import guide_text  # noqa: E402
import report_text  # noqa: E402

WIN_ROOT = r"C:\Users\Mulenga Mwamba\Desktop\QuantaKai"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig").replace("\r\n", "\n")   # no BOM, LF endings


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def winpath(rel: str) -> str:
    return rel.replace("/", "\\")


def python_outline(rel: str) -> list[list[str]]:
    """Functions and classes with their first docstring line (read with Python's own parser)."""
    tree = ast.parse(read(rel))
    rows = []

    def sig(fn) -> str:
        a = fn.args
        names = [x.arg for x in a.posonlyargs + a.args]
        if a.vararg:
            names.append("*" + a.vararg.arg)
        names += [x.arg for x in a.kwonlyargs]
        if a.kwarg:
            names.append("**" + a.kwarg.arg)
        return f"{fn.name}({', '.join(names)})"

    def first_line(node) -> str:
        doc = ast.get_docstring(node) or ""
        return doc.strip().split("\n")[0] if doc else ""

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("__"):
            rows.append([f"<code>{E(sig(node))}</code>", E(first_line(node))])
        elif isinstance(node, ast.ClassDef):
            rows.append([f"<code>class {E(node.name)}</code>", E(first_line(node))])
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and not sub.name.startswith("__"):
                    rows.append([f"<code>&nbsp;&nbsp;.{E(sig(sub))}</code>", E(first_line(sub))])
    return rows


def manifest() -> list[dict]:
    out = []
    for rel, purpose, _how, needs in FILES:
        text = read(rel)
        out.append({"path": rel, "lines": text.count("\n"), "bytes": len(text.encode("utf-8")),
                    "sha256": sha256_text(text), "purpose": re.sub("<[^>]+>", "", purpose), "needs": needs})
    return out


# =========================================================================== the guide
def build_guide() -> str:
    d = Doc("QuantaKai Build Guide", "Rebuild the whole project from an empty folder", "qk-guide-v2")
    files = manifest()
    total_lines = sum(f["lines"] for f in files)
    guide_text.intro(d, len(files), total_lines)
    guide_text.architecture(d)
    guide_text.glossary(d)
    guide_text.hardware(d)
    guide_text.downloads(d)
    guide_text.folders(d)
    guide_text.prepare(d)
    guide_text.engine_and_models(d)
    guide_text.portable_python(d)

    # ---------------------------------------------------------------- every file
    d.section("Create every file", "files")
    d.p(f"There are <b>{len(files)} files</b> ({total_lines:,} lines). Create them <b>in this order</b>: each file only "
        "uses files that come before it. For every file: create it at the exact path shown, paste the whole code "
        "box (or press <b>Save file</b> and move the download into place), save as UTF-8.")
    d.note("For AI assistants rebuilding this project",
           "<p>Copy each code box <b>character for character</b>. Do not shorten, summarise, re-indent, rename, "
           "\"improve\" or translate anything, and do not merge files. Keep every comment. If a file is long, write it "
           "in several appends but never skip a part. After each file, compare its line count with the number in its "
           "header. When all files exist, run the checker in the section <a href='#verify'>Check every file</a>; it "
           "lists any file whose content differs.</p>", "ai")
    d.table(["#", "File", "Lines", "Needs first", "What it is"],
            [[str(i + 1), f"<a href='#f-{i + 1}'><code>{E(winpath(f['path']))}</code></a>", f"{f['lines']:,}",
              ", ".join(f"<code>{E(winpath(n))}</code>" for n in f["needs"]) or "-", E(f["purpose"])]
             for i, f in enumerate(files)])
    for i, (rel, purpose, how, needs) in enumerate(FILES):
        info = files[i]
        text = read(rel)
        d.sub(f"{i + 1}. {winpath(rel)}", f"f-{i + 1}")
        d.raw(f"<div class='meta'><span>Full path: <code>{E(WIN_ROOT + chr(92) + winpath(rel))}</code></span>"
              f"<span>{info['lines']:,} lines</span><span>{info['bytes']:,} bytes</span>"
              f"<span>SHA-256 <code>{info['sha256'][:16]}…</code></span></div>")
        d.p(purpose)
        if how:
            d.ul(how)
        if rel.endswith(".py"):
            rows = python_outline(rel)
            if rows:
                d.raw("<details class='file'><summary>Functions and classes in this file "
                      f"<span class='pill'>{len(rows)}</span></summary><div class='in'>")
                d.table(["Name", "What it does"], rows)
                d.raw("</div></details>")
        d.code(text, winpath(rel), save_as=Path(rel).name)
        d.tick(f"I created {winpath(rel)}")

    guide_text.verify(d, files)
    guide_text.smoke_test(d, read("tests/smoke_test.py"))
    guide_text.first_run(d)
    guide_text.voice_setup(d)
    guide_text.how_it_works(d)
    guide_text.api(d)
    guide_text.data_files(d)
    guide_text.interface(d)
    guide_text.settings(d, json.loads(read("config.json")))
    guide_text.security(d)
    guide_text.tuning(d)
    guide_text.models(d)
    guide_text.troubleshooting(d)
    guide_text.privacy(d)
    guide_text.links(d)
    d.raw(f"<p style='color:var(--faint);margin-top:60px'>Built {time.strftime('%Y-%m-%d %H:%M')} by tools/build_docs.py "
          "from the files in this folder.</p>")
    return d.render()


def build_report() -> str:
    d = Doc("QuantaKai Project Report", "Design, implementation, testing and results", "qk-report")
    report_text.write(d, manifest())
    d.raw(f"<p style='color:var(--faint);margin-top:60px'>Built {time.strftime('%Y-%m-%d %H:%M')} by tools/build_docs.py.</p>")
    return d.render()


def main() -> None:
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "BUILD_GUIDE.html").write_text(build_guide(), encoding="utf-8")
    (ROOT / "docs" / "REPORT.html").write_text(build_report(), encoding="utf-8")
    (HERE / "verify_files.py").write_text(guide_text.verify_script(manifest()), encoding="utf-8")
    (ROOT / "docs" / "manifest.json").write_text(json.dumps({"project": "QuantaKai", "files": manifest()}, indent=2),
                                                 encoding="utf-8")
    print("Wrote BUILD_GUIDE.html, docs/REPORT.html, docs/manifest.json and tools/verify_files.py")


if __name__ == "__main__":
    main()
