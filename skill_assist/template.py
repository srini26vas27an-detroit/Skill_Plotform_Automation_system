from __future__ import annotations

import difflib
import re

_INCOMPLETE = re.compile(r"(=\s*$)|_{2,}|\.\.\.|\bTODO\b|write (your )?(code|answer)|your code here", re.I)


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split("\n")


def is_incomplete(line: str) -> bool:
    return bool(_INCOMPLETE.search(line.strip()))


def is_template(starter: str) -> bool:
    return any(l.strip() and is_incomplete(l) for l in _lines(starter))


def missing_fixed_lines(starter: str, draft: str) -> list[str]:
    """Complete starter lines that the draft dropped or changed (order-aware)."""
    draft_lines = [l.strip() for l in _lines(draft)]
    pos = 0
    missing = []
    for line in _lines(starter):
        s = line.strip()
        if not s or is_incomplete(line):
            continue
        try:
            pos = draft_lines.index(s, pos) + 1
        except ValueError:
            missing.append(s)
    return missing


def diff_ops(current: str, new: str) -> list[dict]:
    """Line-level edit script turning `current` into `new`, ordered bottom-to-top."""
    a, b = _lines(current), _lines(new)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ops.append({
            "type": {"replace": "replace", "delete": "delete", "insert": "insert"}[tag],
            "start": i1, "end": i2, "text": "\n".join(b[j1:j2]),
        })
    return sorted(ops, key=lambda o: o["start"], reverse=True)
