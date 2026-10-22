from skill_assist.llm import build_prompt, clean_code


def test_clean_code_plain():
    assert clean_code("print(1)\n") == "print(1)"


def test_clean_code_fenced_with_prose():
    raw = "Here you go:\n```python\nprint(1)\n```\nHope that helps!"
    assert clean_code(raw) == "print(1)"


def test_clean_code_fence_without_trailing_newline_issue():
    assert clean_code("```\nint x;\n```") == "int x;"


def test_prompt_includes_starter_only_when_present():
    assert "starter code" not in build_prompt("Q", "Python")
    assert "def f():" in build_prompt("Q", "Python", "def f():\n    pass")
