from __future__ import annotations

from playwright.sync_api import Page

from .browser import editor_state, open_page
from .config import Settings

CANDIDATES = [".ace_editor", ".CodeMirror", ".monaco-editor", "[contenteditable='true']", "textarea"]


def _describe(page: Page, selector: str, limit: int = 5) -> None:
    loc = page.locator(selector)
    count = loc.count()
    print(f"\n{selector}: {count} element(s)")
    for i in range(min(count, limit)):
        el = loc.nth(i)
        print(
            f"  [{i}] tag={el.evaluate('e => e.tagName')} id={el.get_attribute('id')!r} "
            f"class={el.get_attribute('class')!r} visible={el.is_visible()}"
        )


def run(settings: Settings) -> None:
    with open_page(settings) as page:
        input("Log in if needed, open a practice question, then press Enter... ")
        print("URL:", page.url)

        print("\n== Frames ==")
        for i, f in enumerate(page.frames):
            print(f"  [{i}] {f.url}")

        print("\n== Editor candidates ==")
        for sel in CANDIDATES:
            _describe(page, sel)

        print(f"\n== Configured editor ({settings.editor_selector}) ==")
        from .browser import find_editor

        editor = find_editor(page, settings)
        if editor is None:
            print("  NOT FOUND - update EDITOR_SELECTOR using the candidates above.")
        else:
            state = editor_state(editor)
            print("  editor API available:", state.get("available"), "| kind:", state.get("kind"))
            print("  mode:", state.get("mode"))
            print("  current content:", repr((state.get("value") or "")[:200]))

        print("\n== Buttons ==")
        _describe(page, "button, input[type='button']", limit=10)

        print("\n== Visible text preview (set QUESTION_SELECTOR to narrow this) ==")
        print(page.locator(settings.question_selector).first.inner_text()[:1500])
        input("\nPress Enter to close the browser... ")
