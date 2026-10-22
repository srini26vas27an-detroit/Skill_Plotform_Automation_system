
from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys

from . import browser
from .config import ConfigError, Settings
from .llm import LLMError, OllamaClient
from .session import Session

log = logging.getLogger("skill_assist")


def cmd_run(settings: Settings, once: bool) -> int:
    client = OllamaClient(settings)
    client.check()  # fail fast before opening a browser
    with browser.open_page(settings) as page:
        Session(settings, client, page, once=once).run()
    # The background stdin reader is blocked in input(); exit hard to avoid a noisy shutdown error.
    sys.stdout.flush()
    os._exit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill_assist", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["run", "diagnose", "ping"])
    parser.add_argument("--url", help="Override TARGET_URL")
    parser.add_argument("--model", help="Override OLLAMA_MODEL")
    parser.add_argument("--once", action="store_true", help="Handle a single question then stop")
    parser.add_argument("--review", action="store_true", help="Ask before inserting each draft")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    try:
        if args.command == "ping":
            settings = Settings.load(model=args.model, target_url=args.url or "https://placeholder.invalid")
            OllamaClient(settings).check()
            print(f"OK: Ollama reachable, model '{settings.model}' available.")
            return 0
        settings = Settings.load(target_url=args.url, model=args.model)
        if args.review:
            settings = dataclasses.replace(settings, review=True)
        if args.command == "diagnose":
            from . import diagnose

            diagnose.run(settings)
            return 0
        return cmd_run(settings, args.once)
    except (ConfigError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
