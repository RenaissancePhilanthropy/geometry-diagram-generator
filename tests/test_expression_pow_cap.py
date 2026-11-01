"""The expression evaluator caps ``**`` and rejects non-finite results."""
from __future__ import annotations

import time

import pytest

from geometry_diagrams.ir.errors import ExprEvalError
from geometry_diagrams.ir.to_sympy import _eval_expr
from geometry_diagrams.recipe.expressions import ExpressionError, eval_expr


@pytest.mark.parametrize("raw", ["9**9**9", "2**100000000", "2**-100000", "10**400", "0**-1"])
def test_eval_expr_rejects_runaway_pow(raw):
    start = time.monotonic()
    with pytest.raises(ExpressionError):
        eval_expr(raw, {})
    assert time.monotonic() - start < 5


@pytest.mark.parametrize("raw", ["9**9**9", "2**100000000", "10**400", "0**-1"])
def test_ir_evaluator_rejects_runaway_pow(raw):
    with pytest.raises(ExprEvalError):
        _eval_expr(raw, {}, def_id="d")


@pytest.mark.parametrize(
    "raw,expected",
    [("2**10", 1024.0), ("2**-2", 0.25), ("4**0.5", 2.0), ("(-8)**(1/3) * 0 + 3**3", 27.0), ("2**1000 / 2**999", 2.0)],
)
def test_ordinary_pow_unchanged(raw, expected):
    assert eval_expr(raw, {}) == pytest.approx(expected)


def test_eval_expr_rejects_non_finite_literal():
    with pytest.raises(ExpressionError):
        eval_expr(float("inf"), {})
