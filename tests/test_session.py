from skill_assist.session import classify, same_question


def test_classify():
    assert classify("bye") == "stop"
    assert classify(" QUIT ") == "stop"
    assert classify("") == "next"
    assert classify("skip") == "skip"
    assert classify("redo") == "redo"
    assert classify("hello?") == "unknown"


def test_same_question():
    a = "Print the sum of two numbers. " * 20
    assert same_question(a, a + " 12:01")
    assert not same_question(a, "Reverse a string and print it. " * 20)
    assert not same_question("", a)
