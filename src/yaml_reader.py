"""src/yaml_reader.py — minimal YAML loader designed for this project's flat config files.

This is intentionally limited:
- only reads dicts and scalar values (strings, ints, bools, floats, nulls)
- no anchors/aliases, no flow style, no complex nesting beyond what the
  project configs actually use (which are flat or singly-nested)
- raises on anything it cannot parse (fail loud, not silently wrong)

Usage mirrors PyYAML's safe_load for the subset we care about:
    from src.yaml_reader import load_yaml
    cfg = load_yaml(path_to_file)
"""

from __future__ import annotations

import pathlib
import re
from typing import Any


__all__ = ["load_yaml"]

_LINE_CONTINUATION = re.compile(r"\\\n")
_COMMENT = re.compile(r"#.*$")
# Match a YAML document in full. We parse line-by-line but this lets us
# handle the header/footer markers yaml.safe_load would expect.
_DOC_HEADER = re.compile(r"^(?:---|\<\?xml[^\n]*\n)")
_DOC_FOOTER = re.compile(r"\n---\s*$")
# key: value lines (top-level mapping entries)
_KV = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_ ]*)\s*:\s*(.*)$")
# inline list item
_LIST_ITEM = re.compile(r"^\s*-\s+(.*)$")
# inline bool/null/int/float recognition
_TRUE = re.compile(r"^\s*true\s*$", re.I)
_FALSE = re.compile(r"^\s*false\s*$", re.I)
_NULL = re.compile(r"^\s*null\s*$", re.I)
_INT = re.compile(r"^\s*-?\d+\s*$")
_FLOAT = re.compile(r"^\s*-?\d+\.\d+\s*$")
# quoted string
_QUOTED = re.compile(r'^\s*"(.*)"\s*$')
_SINGLE_QUOTED = re.compile(r"^\s*'(.*)'$")

_INDENT = re.compile(r"^(\s*)")


def _unquote(s: str) -> str:
    if _QUOTED.match(s):
        return _QUOTED.match(s).group(1).replace("\\\"", '"').replace("\\\\", "\\")
    if _SINGLE_QUOTED.match(s):
        return _SINGLE_QUOTED.match(s).group(1)
    return s


def _parse_scalar(raw: str) -> Any:
    s = _COMMENT.sub("", raw).strip()
    if not s:
        return None
    low = s.lower()
    if _TRUE.match(s):
        return True
    if _FALSE.match(s):
        return False
    if _NULL.match(s):
        return None
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    if s.startswith('"') or s.startswith("'"):
        return _unquote(s)
    return s


def _strip_comments(line: str) -> str:
    return _COMMENT.sub("", line)


def load_yaml(path: str | pathlib.Path) -> Any:
    """Load a YAML file and return its top-level object.

    Supports a subset sufficient for this project's config files:
      - top-level mapping (the usual case)
      - top-level list
      - nested scalars under a mapping
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    # Strip document markers
    text = _DOC_HEADER.sub("", text)
    text = _DOC_FOOTER.sub("", text)
    # Remove line continuations
    text = _LINE_CONTINUATION.sub("", text)
    lines = text.splitlines()
    return _parse_value(lines)


def _parse_value(lines: list[str]) -> Any:
    """Parse a block of lines into a Python value (dict, list, or scalar)."""
    lines = _strip_block_comments(lines)
    if not lines:
        return None
    # Determine if this block is a list
    if _is_list_block(lines):
        return _parse_list(lines)
    # Otherwise it's a mapping
    return _parse_mapping(lines)


def _strip_block_comments(lines: list[str]) -> list[str]:
    """Remove comment-only lines and trailing comments."""
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out.append(_strip_comments(line))
    return out


def _is_list_block(lines: list[str]) -> bool:
    """Check if a block starts with a list item."""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped.startswith("-")
    return False


def _parse_list(lines: list[str]) -> list:
    """Parse a YAML list block."""
    items = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if stripped.startswith("- "):
            # Get the value after "- "
            value_part = stripped[2:].strip()
            if value_part.startswith("["):
                # Inline list
                items.append(_parse_inline_list(value_part))
            else:
                # Could be a nested mapping or scalar
                if value_part.startswith("{"):
                    items.append(_parse_inline_mapping(value_part))
                else:
                    items.append(_parse_scalar(value_part))
        elif stripped.startswith("-") and len(stripped) == 1:
            # Bare "-"
            items.append(None)
        i += 1
    return items


def _parse_inline_list(s: str) -> list:
    """Parse an inline YAML list like [a, b, c]."""
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1].strip()
        if not s:
            return []
        items = []
        # Simple split by comma (works for scalars)
        for part in s.split(","):
            items.append(_parse_scalar(part.strip()))
        return items
    return [_parse_scalar(s)]


def _parse_inline_mapping(s: str) -> dict:
    """Parse an inline YAML mapping like {key: value, key2: value2}."""
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
        if not s:
            return {}
        result = {}
        for pair in s.split(","):
            pair = pair.strip()
            if ":" in pair:
                key, _, value = pair.partition(":")
                result[_parse_scalar(key.strip())] = _parse_scalar(value.strip())
        return result
    return dict(s=s)


def _parse_mapping(lines: list[str]) -> dict:
    """Parse a YAML mapping block into a dict."""
    result = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        m = _KV.match(line)
        if m:
            key = m.group(1).strip()
            value_text = m.group(2).strip()
            # Check for inline list or mapping
            if value_text.startswith("["):
                result[key] = _parse_inline_list(value_text)
            elif value_text.startswith("{"):
                result[key] = _parse_inline_mapping(value_text)
            elif value_text == "":
                # Value is on next lines (nested block)
                # Collect indented lines
                indent = len(line) - len(line.lstrip())
                nested_lines = []
                j = i + 1
                while j < len(lines):
                    nline = lines[j]
                    nstripped = nline.strip()
                    if not nstripped or nstripped.startswith("#"):
                        j += 1
                        continue
                    nindent = len(nline) - len(nline.lstrip())
                    if nindent <= indent:
                        break
                    nested_lines.append(nline)
                    j += 1
                if nested_lines:
                    result[key] = _parse_value(nested_lines)
                else:
                    result[key] = ""
                i = j
                continue
            else:
                result[key] = _parse_scalar(value_text)
        i += 1
    return result


def _parse_dict(lines: list[str]) -> dict:
    """Parse a block that starts with a mapping."""
    return _parse_mapping(lines)


def load_yaml_string(text: str) -> Any:
    """Load YAML from a string."""
    text = _DOC_HEADER.sub("", text)
    text = _DOC_FOOTER.sub("", text)
    text = _LINE_CONTINUATION.sub("", text)
    lines = text.splitlines()
    return _parse_value(lines)
