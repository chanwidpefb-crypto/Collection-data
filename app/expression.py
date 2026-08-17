"""Safe arithmetic expression evaluator for server-side "factor expression" fields.

Used by Modbus TCP Server / OPC UA Server register mappings, e.g.:

    tank1_level * 1.0
    (temp_c * 9 / 5) + 32
    min(setpoint, max_limit)

Only arithmetic operators, numeric literals, tag-name lookups and a small
allow-listed set of functions are permitted -- no attribute access, no
function calls outside the allow-list, no comprehensions, no imports. This
makes it safe to evaluate expressions that ultimately come from user-entered
configuration.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Callable, Mapping

_BIN_OPS: dict[type, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type, Callable] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_FUNCTIONS: dict[str, Callable] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
}


class ExpressionError(ValueError):
    pass


def _eval_node(node: ast.AST, variables: Mapping[str, float]):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ExpressionError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ExpressionError(f"unknown tag: {node.id}")
        return variables[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, variables))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise ExpressionError("only whitelisted functions may be called")
        if node.keywords:
            raise ExpressionError("keyword arguments are not supported")
        args = [_eval_node(a, variables) for a in node.args]
        return _FUNCTIONS[node.func.id](*args)
    raise ExpressionError(f"unsupported expression syntax: {ast.dump(node)}")


def evaluate(expression: str, variables: Mapping[str, float]) -> float:
    """Evaluate an arithmetic expression against a mapping of tag name -> value.

    Raises ExpressionError on invalid syntax, disallowed constructs, or a
    reference to a tag that isn't present in `variables`.
    """
    expression = expression.strip()
    if not expression:
        raise ExpressionError("expression is empty")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid syntax: {exc}") from exc
    return _eval_node(tree.body, variables)


def referenced_names(expression: str) -> set[str]:
    """Return the set of tag names referenced by an expression (for validation/UI)."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid syntax: {exc}") from exc
    call_func_ids = {n.func.id for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in call_func_ids}
