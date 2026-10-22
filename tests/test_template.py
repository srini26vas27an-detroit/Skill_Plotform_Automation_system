from skill_assist import template as T

STARTER = 'N = \nif not(N == 100 or N == 200 or N == 300):\n    print ("YES")\nelse:\n    print ("NO")'


def test_detects_template():
    assert T.is_template(STARTER)
    assert not T.is_template("def f(x):\n    return x")


def test_missing_fixed_lines():
    ok = STARTER.replace("N = ", "N = 100")
    assert T.missing_fixed_lines(STARTER, ok) == []
    rewritten = "N = int(input())\nprint('NO')"
    assert T.missing_fixed_lines(STARTER, rewritten)  # fixed lines were dropped


def test_diff_ops_touch_only_changed_line():
    new = STARTER.replace("N = ", "N = 100")
    ops = T.diff_ops(STARTER, new)
    assert len(ops) == 1 and ops[0]["start"] == 0 and ops[0]["end"] == 1 and ops[0]["text"] == "N = 100"


def test_diff_ops_ordered_bottom_to_top():
    ops = T.diff_ops("a\nb\nc", "a2\nb\nc2\nd")
    assert [o["start"] for o in ops] == sorted([o["start"] for o in ops], reverse=True)
