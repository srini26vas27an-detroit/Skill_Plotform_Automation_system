from __future__ import annotations

import json
import re

from .llm import clean_code


def role(slot: dict) -> str:
    """'fixed' if read-only or already holding code; otherwise an empty editable 'blank'."""
    if slot.get("readonly") or (slot.get("value") or "").strip():
        return "fixed"
    return "blank"


def is_slot_layout(slots: list[dict]) -> bool:
    return len(slots) >= 2 and any(role(s) == "blank" for s in slots)


def blank_indexes(slots: list[dict]) -> list[int]:
    return [s["i"] for s in slots if role(s) == "blank"]


def blank_slots(slots: list[dict], blank_idx: list[int] | None = None) -> list[dict]:
    """Blanks by remembered index (stable across retries, when blanks are no longer empty)."""
    idx = set(blank_idx) if blank_idx is not None else set(blank_indexes(slots))
    return [s for s in slots if s["i"] in idx]


def render_layout(slots: list[dict], blank_idx: list[int] | None = None) -> str:
    """Fixed code and blanks in page order, with explicit markers so the model cannot confuse them."""
    idx = set(blank_idx) if blank_idx is not None else set(blank_indexes(slots))
    out, k, prev = [], 0, None
    for s in slots:
        is_blank = s["i"] in idx
        if is_blank:
            k += 1
            out.append(f"[blank {k} - write ONLY what goes here]")
            out.append(f"<<BLANK_{k}>>")
        else:
            if prev != "fixed":
                out.append("[fixed code - already on the page, never repeat it]")
            out.append((s.get("value") or "").rstrip("\n"))
        prev = "blank" if is_blank else "fixed"
    return "\n".join(out)


def adjacent_fixed(slots: list[dict], blank_idx: list[int] | None = None) -> list[tuple[str, str]]:
    """For every blank (in page order): (fixed code right before it, fixed code right after it)."""
    idx = set(blank_idx) if blank_idx is not None else set(blank_indexes(slots))
    groups: list[list[str]] = [[]]          # fixed text between consecutive blanks
    for s in slots:
        if s["i"] in idx:
            groups.append([])
        else:
            groups[-1].append(s.get("value") or "")
    texts = ["\n".join(g) for g in groups]
    return [(texts[k], texts[k + 1]) for k in range(len(texts) - 1)]


_JOIN_SPACE = tuple("=,(+-*/%<>&|[")


def assemble(slots: list[dict], answers: dict[int, str], blank_idx: list[int] | None = None) -> str:
    """The full program as the page would assemble it (used for a syntax check and for display)."""
    idx = set(blank_idx) if blank_idx is not None else set(blank_indexes(slots))
    pieces, k = [], 0
    for s in slots:
        if s["i"] in idx:
            k += 1
            pieces.append(answers.get(k, ""))
        else:
            pieces.append((s.get("value") or "").strip("\n"))
    program = ""
    for piece in pieces:
        if not program:
            program = piece
        else:
            sep = " " if program.rstrip().endswith(_JOIN_SPACE) else "\n"
            program += sep + piece
    return program


_TOKEN = re.compile(r"\w+|[^\w\s]")


def _tokens(text: str) -> list[tuple[str, int]]:
    return [(m.group(), m.start()) for m in _TOKEN.finditer(text)]


def strip_boundary_overlap(answer: str, before: str, after: str, min_tokens: int = 3) -> str:
    """Cut fixed code the model repeated at the start / end of a blank, ignoring formatting.

    Works on tokens, so `int main() {` matches a page that shows `int main()` and `{` on two lines.
    Only the code adjacent to this blank is considered, and only slices anchored to its start/end.
    """
    text = answer

    def anchored(seq: list[str], ref: list[str]) -> bool:
        m = len(seq)
        return any(ref[a : a + m] == seq and (a == 0 or a + m == len(ref)) for a in range(len(ref) - m + 1))

    head = [t for t, _ in _tokens(before)]
    toks = _tokens(text)
    for m in range(min(len(toks), len(head)), min_tokens - 1, -1):
        if anchored([t for t, _ in toks[:m]], head):
            start = toks[m][1] if m < len(toks) else len(text)
            line_start = text.rfind("\n", 0, start) + 1
            text = text[line_start if not text[line_start:start].strip() else start :]
            break

    tail = [t for t, _ in _tokens(after)]
    toks = _tokens(text)
    for m in range(min(len(toks), len(tail)), min_tokens - 1, -1):
        if anchored([t for t, _ in toks[-m:]], tail):
            text = text[: toks[-m][1]]
            break

    cleaned = "\n".join(l.rstrip() for l in text.strip("\n").split("\n")).strip("\n")
    return cleaned if cleaned.strip() else answer


def clean_answer(answer: str, before: str, after: str, all_fixed: list[str]) -> str:
    """Remove any fixed code the model copied into a blank (exact blocks first, then boundaries)."""
    return strip_boundary_overlap(strip_fixed_overlap(answer, all_fixed), before, after)


def strip_fixed_overlap(answer: str, fixed_fragments: list[str]) -> str:
    """Remove fixed code the model wrongly repeated inside a blank (it would run twice).

    A fixed fragment is removed from the answer only if it appears there as a contiguous block of
    lines (whitespace-insensitive). Tiny fragments such as ')' or 'print(' are ignored, since they
    could legitimately appear inside an answer.
    """
    lines = answer.split("\n")
    for frag in fixed_fragments:
        want = [l.strip() for l in frag.split("\n") if l.strip()]
        if len(want) < 2 and sum(len(w) for w in want) < 12:
            continue
        idx = [i for i, l in enumerate(lines) if l.strip()]
        view = [lines[i].strip() for i in idx]
        for start in range(len(view) - len(want) + 1):
            if view[start : start + len(want)] == want:
                drop = set(idx[start : start + len(want)])
                lines = [l for i, l in enumerate(lines) if i not in drop]
                break
    cleaned = "\n".join(lines).strip("\n")
    return cleaned if cleaned.strip() else answer


def parse_answers(raw: str, count: int) -> dict[int, str]:
    """Parse the model's reply into {1: text, 2: text, ...}. Raises ValueError if incomplete."""
    text = clean_code(raw) if "```" in raw else raw.strip()
    data = None
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict):
        answers: dict[int, str] = {}
        for key, value in data.items():
            m = re.search(r"\d+", str(key))
            if m:
                answers[int(m.group())] = value if isinstance(value, str) else json.dumps(value)
        missing = [i for i in range(1, count + 1) if i not in answers]
        if missing:
            raise ValueError(f"model omitted blank(s) {missing}")
        return {i: answers[i].strip("\n") for i in range(1, count + 1)}
    if count == 1 and text:
        return {1: text}
    raise ValueError("could not parse the model's answer as JSON")


def build_prompt(question: str, language: str, layout: str, count: int,
                 previous: str = "", feedback: str = "", problem: str = "") -> str:
    parts = [
        f"This is a fill-in-the-blanks {language} question.\n",
        f"Question page text:\n---\n{question}\n---\n",
        "Code layout. Fixed code is already on the page and cannot change; each editable blank is marked "
        "<<BLANK_k>>. Fixed fragments and blanks are joined in order, so a blank continues the fragment "
        "before it (e.g. 'numList =' followed by a blank means numList = <blank>). Example for C: if the "
        "fixed code already has '#include', 'int main() {' and 'return 0; }', a blank holds ONLY the "
        "statements that go inside main - no #include, no main, no return, no closing brace.\n"
        f"---\n{layout}\n---\n",
    ]
    if previous.strip() and feedback.strip():
        parts.append(
            f"Your previous answers:\n---\n{previous}\n---\nThey FAILED. The judge reported:\n---\n"
            f"{feedback}\n---\nUse the input / expected output to correct them; do not repeat them.\n"
        )
    if problem:
        parts.append(f"Your last answer had a problem, fix it: {problem}\n")
    example = ", ".join(f'"{i}": "..."' for i in range(1, count + 1))
    parts.append(
        f"Return ONLY a JSON object with exactly {count} key(s) giving the exact text to type in each "
        f"blank, like {{{example}}}. A blank must contain ONLY what belongs in that box: never repeat or "
        "copy any fixed code from the layout (it is already on the page and would run twice). "
        "No explanation, no markdown."
    )
    return "\n".join(parts)
