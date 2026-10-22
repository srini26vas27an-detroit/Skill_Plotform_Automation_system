from __future__ import annotations

import difflib
import queue
import re
import threading
from dataclasses import dataclass

from playwright.sync_api import Locator, Page

from . import browser, language
from .checks import syntax_check
from .config import Settings
from .llm import LLMError, OllamaClient

STOP_WORDS = {"bye", "quit", "exit", "stop", "q"}
SKIP_WORDS = {"skip", "s"}
REDO_WORDS = {"redo", "retry", "r"}
NEXT_WORDS = {"", "next", "n", "done", "d"}

# Text that commonly appears after a successful submission. Override with SUCCESS_PATTERN.
DEFAULT_SUCCESS = (
    r"congratulations|all (the )?test ?cases? (are |were |have )?passed|"
    r"successfully (submitted|completed|solved)|you have (passed|solved)|\baccepted\b"
)
NEXT_RE = re.compile(
    r"^\s*(next( (question|problem|challenge|program|task))?|continue|go to next( question)?)\s*[»>→]*\s*$",
    re.I,
)


class Stop(Exception):
    """Raised when the user types 'bye'."""


def classify(line: str) -> str:
    """Map a terminal line to 'stop' | 'skip' | 'redo' | 'next' | 'unknown'."""
    w = line.strip().lower()
    if w in STOP_WORDS:
        return "stop"
    if w in SKIP_WORDS:
        return "skip"
    if w in REDO_WORDS:
        return "redo"
    if w in NEXT_WORDS:
        return "next"
    return "unknown"


def same_question(a: str, b: str, threshold: float = 0.85) -> bool:
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a[:2000], b[:2000]).ratio() >= threshold


class Commands:
    """Reads terminal input in the background so the browser loop never blocks."""

    def __init__(self) -> None:
        self.q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                self.q.put(input())
            except EOFError:
                self.q.put("bye")
                return

    def poll(self) -> str | None:
        try:
            return classify(self.q.get_nowait())
        except queue.Empty:
            return None


@dataclass
class State:
    count: int = 0
    last_text: str = ""
    last_url: str = ""
    sticky_lang: language.Language | None = None


class Session:
    def __init__(self, settings: Settings, client: OllamaClient, page: Page, once: bool = False):
        self.s, self.client, self.page, self.once = settings, client, page, once
        self.cmd = Commands()
        self.state = State()
        self.success = re.compile(settings.success_pattern or DEFAULT_SUCCESS, re.I)

    # ---- helpers -----------------------------------------------------
    def _sleep(self, ms: int = 1000) -> None:
        self.page.wait_for_timeout(ms)  # keeps Playwright's event loop alive

    def _next_command(self, allowed: set[str]) -> str:
        """Block until the user types one of the allowed commands ('stop' always raises)."""
        while True:
            c = self.cmd.poll()
            if c == "stop":
                raise Stop
            if c in allowed:
                return c
            self._sleep(300)

    def _read_line(self) -> str:
        while True:
            try:
                line = self.cmd.q.get(timeout=0.3)
            except queue.Empty:
                self._sleep(100)
                continue
            if line.strip().lower() in STOP_WORDS:
                raise Stop
            return line

    def _page_text(self) -> str:
        try:
            return browser.question_text(self.page, self.s)
        except Exception:
            return ""

    def _body(self) -> str:
        try:
            return self.page.locator("body").inner_text()
        except Exception:
            return ""

    # ---- steps -------------------------------------------------------
    def wait_for_new_question(self) -> str:
        print("\nWaiting for a question with a visible editor... (type 'bye' to stop)")
        last_status = 0.0
        import time as _t

        while True:
            c = self.cmd.poll()
            if c == "stop":
                raise Stop
            editor = browser.find_editor(self.page, self.s)
            text = self._page_text() if editor is not None else ""
            changed = self.page.url != self.state.last_url or not same_question(text, self.state.last_text)
            ready = editor is not None and bool(text) and (changed or self.state.count == 0)

            if c in {"next", "redo"}:  # "I'm on a question - start now"
                if editor is not None and text:
                    print("OK, using the question on screen now.")
                    self._sleep(500)
                    return self._page_text() or text
                print("No editor on this page yet, so there is nothing to do. " + browser.why_no_editor(self.page, self.s))
            elif c == "skip":
                print("Nothing to skip: no question is open yet.")

            if ready:
                self._sleep(1500)  # let the page and editor finish loading
                return self._page_text() or text

            if _t.time() - last_status > 10:
                last_status = _t.time()
                if editor is None:
                    print("[waiting] " + browser.why_no_editor(self.page, self.s))
                else:
                    print("[waiting] Editor found, but this looks like the same question as the last one. "
                          "Open the next question, or type 'next' to use this one anyway.")
            self._sleep(500)

    def pick_language(self, text: str, mode: str | None) -> language.Language:
        if self.s.language:
            forced = language.parse(self.s.language)
            if forced:
                return forced
        if self.state.sticky_lang:
            return self.state.sticky_lang
        detected = language.resolve(mode, text)
        if detected:
            return detected
        print(f"Could not detect the language (editor mode: {mode}).")
        while True:
            print("Type the language: C, C++, Python, Java or SQL")
            chosen = language.parse(self._read_line())
            if chosen:
                self.state.sticky_lang = chosen  # remembered for the rest of the session
                return chosen

    def draft_and_insert(self, text: str) -> bool:
        editor = browser.wait_for_editor(self.page, self.s)
        ed = browser.editor_state(editor)
        n = self.state.count + 1
        if not ed.get("available"):
            print("Note: no editor API found; will fall back to keyboard typing.")
        lang = self.pick_language(text, ed.get("mode"))
        print(f"\n=== Question {n} | {lang.name} | editor: {ed.get('kind')} ===")
        print(text[:500] + ("\n[...]" if len(text) > 500 else ""))

        print("\nGenerating with the local model...")
        code = ""
        for _ in range(2):  # one automatic retry on a syntax error
            code = self.client.generate(text, lang.name, starter_code=ed.get("value") or "")
            problem = syntax_check(code, lang)
            if not problem:
                break
            print(f"Draft had an error ({problem.splitlines()[0]}); retrying...")

        out = self.s.output_dir
        out.mkdir(exist_ok=True)
        path = out / f"q{n:03d}_solution{lang.extension}"
        path.write_text(code, encoding="utf-8")
        print(f"--- Draft (saved to {path}) ---\n{code}\n")

        if self.s.review:
            print("Insert? Type y to insert, anything else to skip:")
            if self._read_line().strip().lower() not in {"y", "yes"}:
                return False
        method = browser.set_editor_code(browser.wait_for_editor(self.page, self.s), code)
        print(f"Inserted into the editor and verified (method: {method}).")
        return True

    def wait_for_submit(self) -> str:
        """Returns 'next' | 'skip' | 'redo' | 'moved'. Raises Stop on 'bye'."""
        start_url = self.page.url
        baseline = bool(self.success.search(self._body()))
        auto = "I'll detect the submission automatically, or type" if not baseline else "Type"
        print(f"Now Run and Submit in the browser. {auto}: next | skip | redo | bye")
        while True:
            c = self.cmd.poll()
            if c == "stop":
                raise Stop
            if c in {"skip", "redo", "next"}:
                return c
            if self.page.url != start_url:
                print("Page changed - you moved on yourself.")
                return "moved"
            if not baseline and self.success.search(self._body()):
                print("Submission detected.")
                self._sleep(1500)
                return "next"
            self._sleep(1000)

    def _find_next_button(self) -> Locator | None:
        if self.s.next_selector:
            for frame in self.page.frames:
                loc = frame.locator(self.s.next_selector).first
                if loc.count() and loc.is_visible():
                    return loc
            return None
        for frame in self.page.frames:
            for finder in (
                lambda f: f.get_by_role("button", name=NEXT_RE),
                lambda f: f.get_by_role("link", name=NEXT_RE),
                lambda f: f.get_by_text(NEXT_RE),
            ):
                try:
                    loc = finder(frame).first
                    if loc.count() and loc.is_visible():
                        return loc
                except Exception:
                    continue
        return None

    def go_next(self) -> None:
        self.state.last_text = self._page_text()
        self.state.last_url = self.page.url
        btn = self._find_next_button()
        if btn is None:
            print("Could not find a Next button. Open the next question yourself - I'll pick it up.")
            print("(Set NEXT_SELECTOR in .env to make this automatic; run `diagnose` to find it.)")
            return
        btn.click()
        print("Clicked Next.")

    def handle_question(self, text: str) -> str:
        while True:  # 'redo' repeats the same question
            try:
                inserted = self.draft_and_insert(text)
            except Stop:
                raise
            except LLMError as e:
                print(f"Model error: {e}")
                inserted = False
            except Exception as e:  # keep the loop alive, show the cause
                print(f"Error while inserting: {type(e).__name__}: {e}")
                inserted = False

            if inserted:
                action = self.wait_for_submit()
            else:
                print("Nothing was inserted. Type: redo | skip | bye")
                action = self._next_command({"skip", "redo", "next"})
                action = "skip" if action == "next" else action
            if action == "redo":
                text = self._page_text() or text
                continue
            return action

    # ---- main loop ---------------------------------------------------
    def run(self) -> None:
        print("Log in and open a question. Commands any time: next | skip | redo | bye")
        try:
            while True:
                text = self.wait_for_new_question()
                action = self.handle_question(text)
                self.state.count += 1
                if self.once:
                    break
                if action == "moved":
                    self.state.last_text, self.state.last_url = "", ""
                else:
                    self.go_next()
        except Stop:
            pass
        print("Bye! Stopped.")
