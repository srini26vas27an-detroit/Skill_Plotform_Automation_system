import pytest

from skill_assist import slots as S

LAYOUT = [
    {"i": 0, "kind": "ace", "readonly": True, "value": "numList ="},
    {"i": 1, "kind": "ace", "readonly": False, "value": ""},
    {"i": 2, "kind": "ace", "readonly": True, "value": "print("},
    {"i": 3, "kind": "textarea", "readonly": False, "value": ""},
    {"i": 4, "kind": "ace", "readonly": True, "value": ")"},
]


def test_roles_and_layout():
    assert [S.role(s) for s in LAYOUT] == ["fixed", "blank", "fixed", "blank", "fixed"]
    assert S.is_slot_layout(LAYOUT)
    assert not S.is_slot_layout(LAYOUT[:1])
    lay = S.render_layout(LAYOUT)
    assert lay.count("<<BLANK_") == 2 and "numList =" in lay and "already on the page" in lay
    assert len(S.blank_slots(LAYOUT)) == 2


def test_parse_answers_variants():
    assert S.parse_answers('```json\n{"1": "[1, 2]", "2": "sum(numList)"}\n```', 2) == {1: "[1, 2]", 2: "sum(numList)"}
    assert S.parse_answers('Sure! {"BLANK_1": "5", "BLANK_2": "6"}', 2) == {1: "5", 2: "6"}
    assert S.parse_answers("100", 1) == {1: "100"}       # bare answer is fine for a single blank


def test_parse_answers_rejects_incomplete():
    with pytest.raises(ValueError):
        S.parse_answers('{"1": "x"}', 2)
    with pytest.raises(ValueError):
        S.parse_answers("not json at all", 2)


def test_strip_fixed_overlap_removes_repeated_fixed_block():
    fixed = ['numbers = [1,2,3]\nmodifyvalues(numbers)\nfor num in numbers:\n    print (num, end=" ")']
    answer = ('def modifyvalues(items):\n    items[0] = 500\n\n'
              'numbers = [1,2,3]\nmodifyvalues(numbers)\nfor num in numbers:\n    print (num, end=" ")')
    assert S.strip_fixed_overlap(answer, fixed) == "def modifyvalues(items):\n    items[0] = 500"


def test_strip_fixed_overlap_keeps_legit_content_and_tiny_fragments():
    assert S.strip_fixed_overlap("sum(x)", [")", "print("]) == "sum(x)"
    assert S.strip_fixed_overlap("a = 1\nb = 2", ["c = 3\nd = 4"]) == "a = 1\nb = 2"
    only_fixed = "x = 1\ny = 2"
    assert S.strip_fixed_overlap(only_fixed, [only_fixed]) == only_fixed   # never return an empty answer


C_SLOTS = [
    {"i": 0, "kind": "ace", "readonly": True, "value": "#include <stdio.h>\n\nint main()\n{"},
    {"i": 1, "kind": "ace", "readonly": False, "value": ""},
    {"i": 2, "kind": "ace", "readonly": True, "value": "    return 0;\n}"},
]
WHOLE_PROGRAM = '#include <stdio.h>\n\nint main() {\n    printf("Brave\\n");\n    return 0;\n}'


def test_clean_answer_strips_whole_program_with_different_brace_style():
    fixed = [s["value"] for s in C_SLOTS if s["readonly"]]
    (before, after), = S.adjacent_fixed(C_SLOTS)
    assert S.clean_answer(WHOLE_PROGRAM, before, after, fixed) == '    printf("Brave\\n");'


def test_clean_answer_keeps_a_correct_answer_untouched():
    fixed = [s["value"] for s in C_SLOTS if s["readonly"]]
    (before, after), = S.adjacent_fixed(C_SLOTS)
    ok = '    printf("Brave\\n");'
    assert S.clean_answer(ok, before, after, fixed) == ok


def test_clean_answer_partial_repeat_only_head():
    (before, after), = S.adjacent_fixed(C_SLOTS)
    partial = 'int main()\n{\n    printf("hi");'
    assert S.clean_answer(partial, before, after, []) == '    printf("hi");'


def test_assemble_joins_operator_endings_with_space():
    program = S.assemble(LAYOUT, {1: "[1, 2, 3]", 2: "sum(numList)"})
    assert program.startswith("numList = [1, 2, 3]\nprint( sum(numList)")
    compile(program, "<t>", "exec")      # valid Python


def test_adjacent_fixed_multiple_blanks():
    pairs = S.adjacent_fixed(LAYOUT)
    assert pairs[0] == ("numList =", "print(") and pairs[1] == ("print(", ")")
