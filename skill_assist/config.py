from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    target_url: str
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    editor_selector: str = "#ctutortxtCode"
    question_selector: str = "body"
    output_dir: Path = Path("generated")
    profile_dir: Path = Path(".browser-profile")
    request_timeout: int = 180
    max_question_chars: int = 6000
    next_selector: str = ""        # CSS selector of the site's "Next" button (optional)
    success_pattern: str = ""      # regex shown on the page after a successful submit (optional)
    keep_alive: str = "60m"        # how long Ollama keeps the model loaded between questions
    language: str = ""             # force a language (Python/C/C++/Java/SQL); empty = auto-detect
    headless: bool = False
    review: bool = False           # True = ask before inserting each draft

    @classmethod
    def load(cls, **overrides: str | None) -> "Settings":
        env = os.environ.get
        values = {
            "target_url": env("TARGET_URL", ""),
            "ollama_url": env("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            "model": env("OLLAMA_MODEL", cls.model),
            "editor_selector": env("EDITOR_SELECTOR", cls.editor_selector),
            "question_selector": env("QUESTION_SELECTOR", cls.question_selector),
            "request_timeout": int(env("REQUEST_TIMEOUT", cls.request_timeout)),
            "max_question_chars": int(env("MAX_QUESTION_CHARS", cls.max_question_chars)),
            "next_selector": env("NEXT_SELECTOR", ""),
            "success_pattern": env("SUCCESS_PATTERN", ""),
            "keep_alive": env("OLLAMA_KEEP_ALIVE", cls.keep_alive),
            "language": env("LANGUAGE", ""),
            "headless": env("HEADLESS", "").lower() in {"1", "true", "yes"},
        }
        values.update({k: v for k, v in overrides.items() if v not in (None, "")})
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.target_url.startswith(("http://", "https://")) or "need_to_paste" in self.target_url:
            raise ConfigError(
                "TARGET_URL is not set. Copy .env.example to .env and set a real URL "
                "(or pass --url)."
            )
