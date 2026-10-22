# skill-automation

Human-in-the-loop assistant: reads a practice question in a browser, drafts a solution
with a **local** Ollama model, shows it to you, and (only if you approve) fills the
editor. Run / Submit always stay manual.

Use it to study: read the draft, understand it, and fix it yourself. Don't use it on
graded tests, contests or anywhere the platform's rules forbid assistance or automation.

## Setup (Windows PowerShell)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    playwright install chromium
    copy .env.example .env      # then edit TARGET_URL
    ollama pull qwen2.5-coder:7b

## Usage

    python -m skill_assist ping        # Ollama + model reachable?
    python -m skill_assist diagnose    # inspect editor/selectors (replaces 4 old scripts)
    python -m skill_assist run         # continuous loop (type 'bye' to stop)
    python -m skill_assist run --once  # a single question
    python -m skill_assist run --review  # ask before each insert
    python -m pytest                   # unit tests

Login is remembered in `.browser-profile/` (git-ignored), so you log in once.

## Continuous loop

`run` keeps going until you type `bye`:

1. Waits for a question with a visible editor (main page or iframe).
2. Generates a solution with the local model and **inserts it into the editor**, then reads the
   editor back to verify the code really landed. Method order: editor API (Ace / CodeMirror /
   Monaco) -> keyboard typing fallback.
3. You Run and Submit manually. A successful submit is detected from page text
   (`SUCCESS_PATTERN`, with sensible defaults like "Congratulations" / "all test cases passed").
4. It clicks the site's **Next** button (auto-detected by its label, or `NEXT_SELECTOR`), waits for
   the new question, and repeats. If you navigate yourself, it notices and carries on.

Terminal commands, any time: `next` (or Enter), `skip`, `redo`, `bye`.
If the language can't be detected it asks once and remembers (or set `LANGUAGE=` in `.env`).
Ollama keeps the model loaded between questions (`OLLAMA_KEEP_ALIVE`).

Troubleshooting: if nothing inserts, run `diagnose` and check that the editor is found and
`EDITOR_SELECTOR` matches. If Next isn't clicked, set `NEXT_SELECTOR`. Use `-v` for more logging.

## Layout

    skill_assist/
      config.py     settings from .env (no hard-coded URLs)
      language.py   language from the editor's Ace mode, text as fallback
      llm.py        Ollama client, prompt, reply cleaning
      checks.py     local syntax check (Python, gcc/g++ if installed)
      browser.py    Playwright + Ace editor read/write
      diagnose.py   page/editor inspection
      session.py    continuous loop and terminal commands
      cli.py        run | diagnose | ping
    tests/          pytest for pure logic
    generated/      model output (git-ignored)
