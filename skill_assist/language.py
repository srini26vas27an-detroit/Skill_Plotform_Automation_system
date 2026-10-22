
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    name: str
    extension: str


PYTHON = Language("Python", ".py")
C = Language("C", ".c")
CPP = Language("C++", ".cpp")
JAVA = Language("Java", ".java")
SQL = Language("SQL", ".sql")

BY_NAME = {l.name.lower(): l for l in (PYTHON, C, CPP, JAVA, SQL)}
BY_NAME.update({"c programming": C, "cpp": CPP, "python3": PYTHON})

_ACE_MODES = {
    "python": PYTHON,
    "java": JAVA,
    "sql": SQL,
    "mysql": SQL,
    "pgsql": SQL,
    "sqlserver": SQL,
}

_TEXT_PATTERNS = [
    (CPP, re.compile(r"c\+\+", re.I)),
    (C, re.compile(r"\bc\s+programming\b", re.I)),
    (PYTHON, re.compile(r"\bpython\s*3?\b", re.I)),
    (JAVA, re.compile(r"\bjava\b(?!\s*script)", re.I)),
    (SQL, re.compile(r"\b(?:my)?sql\b", re.I)),
]


def from_ace_mode(mode_id: str | None) -> Language | None:
    """'ace/mode/python' -> Python. c_cpp is ambiguous, so it returns None."""
    if not mode_id:
        return None
    return _ACE_MODES.get(mode_id.rsplit("/", 1)[-1].lower())


def from_text(text: str) -> Language | None:
    """Return a language only if exactly one is mentioned (menus often list several)."""
    found = [lang for lang, pattern in _TEXT_PATTERNS if pattern.search(text)]
    return found[0] if len(found) == 1 else None


def resolve(ace_mode: str | None, text: str) -> Language | None:
    lang = from_ace_mode(ace_mode)
    if lang:
        return lang
    if ace_mode and ace_mode.endswith("c_cpp"):
        return CPP if re.search(r"c\+\+", text, re.I) else (C if re.search(r"\bc\b", text, re.I) else None)
    return from_text(text)


def parse(name: str) -> Language | None:
    return BY_NAME.get(name.strip().lower())
