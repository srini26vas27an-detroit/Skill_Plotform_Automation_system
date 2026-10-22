
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .language import C, CPP, PYTHON, Language


def syntax_check(code: str, language: Language) -> str | None:
    """Return an error message, or None if OK / not checkable."""
    if language == PYTHON:
        try:
            compile(code, "<generated>", "exec")
        except SyntaxError as e:
            return f"Python syntax error: {e}"
        return None
    if language in (C, CPP):
        compiler = shutil.which("gcc" if language == C else "g++")
        if not compiler:
            return None
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / f"s{language.extension}"
            src.write_text(code, encoding="utf-8")
            r = subprocess.run([compiler, "-fsyntax-only", str(src)], capture_output=True, text=True, timeout=20)
            return r.stderr.strip() or None if r.returncode else None
    return None
