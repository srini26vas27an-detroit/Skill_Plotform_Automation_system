from skill_assist import language as L


def test_ace_modes():
    assert L.from_ace_mode("ace/mode/python") is L.PYTHON
    assert L.from_ace_mode("ace/mode/java") is L.JAVA
    assert L.from_ace_mode("ace/mode/mysql") is L.SQL
    assert L.from_ace_mode("ace/mode/c_cpp") is None
    assert L.from_ace_mode(None) is None


def test_c_cpp_disambiguated_by_text():
    assert L.resolve("ace/mode/c_cpp", "Practice | C++ | Arrays") is L.CPP
    assert L.resolve("ace/mode/c_cpp", "Course: C Programming") is L.C


def test_text_fallback_requires_single_language():
    assert L.from_text("Python 3 question") is L.PYTHON
    assert L.from_text("Menu: Python Java SQL C Programming") is None  # ambiguous nav bar
    assert L.from_text("Learn JavaScript") is None  # not Java


def test_parse():
    assert L.parse(" c++ ") is L.CPP
    assert L.parse("nonsense") is None
