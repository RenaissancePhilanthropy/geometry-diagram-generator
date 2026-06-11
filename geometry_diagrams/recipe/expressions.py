"""Public expression evaluator for the recipe layer.

Wraps ir.to_sympy._eval_expr with a clean float-returning interface
and a recipe-layer exception type.
"""
from __future__ import annotations

from typing import Any

from ..ir.to_sympy import _eval_expr
from ..ir.errors import ExprEvalError


class ExpressionError(ValueError):
    """Raised when expression evaluation fails in the recipe layer."""


def eval_expr(
    raw: int | float | str,
    params: dict[str, Any],
    *,
    sym=None,
) -> float:
    """Evaluate a geometric expression to a Python float.

    Args:
        raw: A numeric literal or expression string (e.g. "length(A, B) * 2").
        params: Named parameter substitutions (e.g. {"r": sympy.S(3)}).
        sym: Optional SymTable (dict mapping IDs to SymPy geometry objects).
             Required for length(), radius(), angle() calls.

    Returns:
        Python float result.

    Raises:
        ExpressionError: If evaluation fails (wraps ExprEvalError or other errors).
    """
    try:
        result = _eval_expr(raw, params, def_id="recipe_eval", sym=sym)
        return float(result.evalf())
    except ExprEvalError as e:
        raise ExpressionError(str(e)) from e
    except Exception as e:
        raise ExpressionError(f"Expression evaluation failed for {raw!r}: {e}") from e
