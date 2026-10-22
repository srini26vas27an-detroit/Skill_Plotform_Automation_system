
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Locator, Page, sync_playwright

from .config import Settings

_EDITOR_JS_COMMON = """
const hostOf = el => (el.classList && el.classList.contains('ace_editor')) ? el
    : ((el.closest && el.closest('.ace_editor')) || el);
const getEditor = el => {
  const host = hostOf(el);
  if (host.env && host.env.editor) return {kind: 'ace', ed: host.env.editor};
  if (window.ace && typeof window.ace.edit === 'function') {
    try { return {kind: 'ace', ed: window.ace.edit(host)}; } catch (e) {}
  }
  const cmHost = host.CodeMirror ? host : (host.closest && host.closest('.CodeMirror'));
  if (cmHost && cmHost.CodeMirror) return {kind: 'codemirror', ed: cmHost.CodeMirror};
  if (window.monaco && window.monaco.editor) {
    const models = window.monaco.editor.getModels();
    if (models.length) return {kind: 'monaco', ed: models[0]};
  }
  return null;
};
"""

_GET_JS = "el => {" + _EDITOR_JS_COMMON + """
  const h = getEditor(el);
  if (!h) return {available: false};
  let mode = null, value = '';
  if (h.kind === 'ace') { const m = h.ed.getSession().getMode(); mode = m && m.$id; value = h.ed.getValue(); }
  else if (h.kind === 'codemirror') { mode = String(h.ed.getOption('mode') || ''); value = h.ed.getValue(); }
  else { mode = h.ed.getLanguageId ? h.ed.getLanguageId() : null; value = h.ed.getValue(); }
  return {available: true, kind: h.kind, mode: mode, value: value};
}"""

_SET_JS = "(el, code) => {" + _EDITOR_JS_COMMON + """
  const h = getEditor(el);
  if (!h) return null;
  if (h.kind === 'ace') { h.ed.setValue(code, -1); h.ed.focus(); }
  else { h.ed.setValue(code); }
  const ta = document.getElementById('txtCode');   // some sites mirror the editor here
  if (ta) {
    ta.value = code;
    ta.dispatchEvent(new Event('input', {bubbles: true}));
    ta.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return h.kind;
}"""


class EditorNotFound(RuntimeError):
    pass


@contextmanager
def open_page(settings: Settings) -> Iterator[Page]:
    """Launch Chromium with a persistent profile so you only log in once."""
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(settings.profile_dir), headless=settings.headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(settings.target_url, wait_until="domcontentloaded")
            yield page
        finally:
            ctx.close()


FALLBACK_SELECTORS = [".ace_editor", ".CodeMirror", ".monaco-editor"]


def find_editor(page: Page, settings: Settings) -> Locator | None:
    """Look for the editor in the main page and every iframe.

    Tries EDITOR_SELECTOR first, then common editor classes (Ace/CodeMirror/Monaco).
    """
    for selector in [settings.editor_selector, *FALLBACK_SELECTORS]:
        for frame in page.frames:
            try:
                loc = frame.locator(selector).first
                if loc.count() and loc.is_visible():
                    return loc
            except Exception:
                continue
    return None


def why_no_editor(page: Page, settings: Settings) -> str:
    """Human-readable hint for why the editor wasn't found."""
    present = []
    for selector in [settings.editor_selector, *FALLBACK_SELECTORS]:
        for frame in page.frames:
            try:
                n = frame.locator(selector).count()
            except Exception:
                n = 0
            if n:
                present.append(f"{selector} x{n} (hidden)")
                break
    where = f"URL: {page.url}"
    if present:
        return f"Editor elements exist but none is visible yet: {', '.join(present)}. {where}"
    return (
        f"No editor ('{settings.editor_selector}', .ace_editor, .CodeMirror, .monaco-editor) on this page. {where}. "
        "Open a question page that shows the code editor. If you're already on one, "
        "run `diagnose` and set EDITOR_SELECTOR."
    )


def wait_for_editor(page: Page, settings: Settings, timeout_ms: int = 20_000) -> Locator:
    deadline = time.time() + timeout_ms / 1000
    while True:
        loc = find_editor(page, settings)
        if loc is not None:
            return loc
        if time.time() >= deadline:
            raise EditorNotFound(
                f"Editor '{settings.editor_selector}' not visible. Run `diagnose` and fix EDITOR_SELECTOR."
            )
        page.wait_for_timeout(300)


def question_text(page: Page, settings: Settings) -> str:
    return page.locator(settings.question_selector).first.inner_text().strip()


def editor_state(editor: Locator) -> dict:
   
    return editor.evaluate(_GET_JS)


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").strip().split("\n"))


def set_editor_code(editor: Locator, code: str) -> str:
    """Insert code and verify it landed. Returns the method used; raises if nothing worked."""
    page = editor.page
    try:
        kind = editor.evaluate(_SET_JS, code)
    except Exception:
        kind = None
    if kind:
        page.wait_for_timeout(150)
        if _norm(editor_state(editor).get("value", "")) == _norm(code):
            return kind

    # Fallback: type it in like a user would paste it.
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.insert_text(code)
    page.wait_for_timeout(200)
    state = editor_state(editor)
    if state.get("available") and _norm(state.get("value", "")) != _norm(code):
        raise RuntimeError("Inserted code does not match what the editor now contains.")
    return "keyboard"
