from skill_assist.checks import syntax_check
from skill_assist.language import JAVA, PYTHON


def test_python_ok_and_bad():
    assert syntax_check("print(1)", PYTHON) is None
    assert "syntax error" in syntax_check("def (:", PYTHON)


def test_unchecked_language_passes():
    assert syntax_check("anything", JAVA) is None
