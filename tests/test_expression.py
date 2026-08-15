import pytest

from app.expression import ExpressionError, evaluate, referenced_names


def test_simple_arithmetic():
    assert evaluate("2 + 3 * 4", {}) == 14


def test_tag_reference():
    assert evaluate("tank1_level * 1.5", {"tank1_level": 10}) == 15


def test_multiple_tags():
    assert evaluate("(temp_c * 9 / 5) + 32", {"temp_c": 100}) == 212


def test_functions():
    assert evaluate("min(a, b)", {"a": 3, "b": 7}) == 3
    assert evaluate("max(a, b)", {"a": 3, "b": 7}) == 7
    assert evaluate("abs(a)", {"a": -5}) == 5
    assert evaluate("round(a)", {"a": 2.6}) == 3


def test_bare_tag_name():
    assert evaluate("pressure", {"pressure": 42.0}) == 42.0


def test_unknown_tag_raises():
    with pytest.raises(ExpressionError):
        evaluate("unknown_tag * 2", {})


def test_unsupported_call_raises():
    with pytest.raises(ExpressionError):
        evaluate("__import__('os').system('echo hi')", {})


def test_attribute_access_blocked():
    with pytest.raises(ExpressionError):
        evaluate("a.__class__", {"a": 1})


def test_string_literal_blocked():
    with pytest.raises(ExpressionError):
        evaluate("'x'", {})


def test_empty_expression_raises():
    with pytest.raises(ExpressionError):
        evaluate("   ", {})


def test_invalid_syntax_raises():
    with pytest.raises(ExpressionError):
        evaluate("2 +", {})


def test_referenced_names():
    assert referenced_names("a * 2 + b") == {"a", "b"}
    assert referenced_names("min(a, max(b, c))") == {"a", "b", "c"}
