import pytest
import sympy as sp
import sympy.geometry as spg
from geometry_diagrams.recipe.expressions import eval_expr, ExpressionError

SYM = {
    "A": spg.Point(0, 0),
    "B": spg.Point(3, 0),
    "C": spg.Point(0, 4),
    "circ": spg.Circle(spg.Point(0, 0), sp.Integer(5)),
}


def test_numeric_literal():
    assert eval_expr(3.14, {}) == pytest.approx(3.14)

def test_plain_expr():
    result = eval_expr("2 + 3", {})
    assert result == pytest.approx(5.0)

def test_length():
    result = eval_expr("length(A, B)", {}, sym=SYM)
    assert result == pytest.approx(3.0)

def test_radius():
    result = eval_expr("radius(circ)", {}, sym=SYM)
    assert result == pytest.approx(5.0)

def test_angle_right():
    result = eval_expr("angle(B, A, C)", {}, sym=SYM)
    assert result == pytest.approx(90.0, abs=1e-4)

def test_params():
    result = eval_expr("2 * r", {"r": sp.S(3)})
    assert result == pytest.approx(6.0)

def test_geo_without_sym_raises():
    with pytest.raises(ExpressionError):
        eval_expr("length(A, B)", {})

def test_unknown_id_raises():
    with pytest.raises(ExpressionError):
        eval_expr("length(X, Y)", {}, sym=SYM)

def test_returns_float():
    result = eval_expr("length(A, B)", {}, sym=SYM)
    assert isinstance(result, float)
