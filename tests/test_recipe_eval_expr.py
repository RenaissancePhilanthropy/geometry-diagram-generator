# tests/test_recipe_eval_expr.py
import pytest
import sympy as sp
import sympy.geometry as spg
from geometry_diagrams.ir.to_sympy import _eval_expr
from geometry_diagrams.ir.errors import ExprEvalError

# Minimal sym table for testing
SYM = {
    "A": spg.Point(0, 0),
    "B": spg.Point(3, 0),
    "C": spg.Point(0, 4),
    "circ": spg.Circle(spg.Point(0, 0), sp.Integer(5)),
}

def test_length_function():
    result = _eval_expr("length(A, B)", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 3.0) < 1e-9

def test_length_pythagoras():
    result = _eval_expr("length(A, C)", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 4.0) < 1e-9

def test_radius_function():
    result = _eval_expr("radius(circ)", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 5.0) < 1e-9

def test_angle_function_right():
    # Angle at A (origin) between B(3,0) and C(0,4) → 90 degrees
    result = _eval_expr("angle(B, A, C)", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 90.0) < 1e-6

def test_angle_function_60():
    # Equilateral triangle: angle at each vertex = 60°
    sym2 = {
        "P": spg.Point(0, 0),
        "Q": spg.Point(2, 0),
        "R": spg.Point(1, float(sp.sqrt(3).evalf())),
    }
    result = _eval_expr("angle(P, Q, R)", {}, def_id="test", sym=sym2)
    assert abs(float(result.evalf()) - 60.0) < 1e-4

def test_geo_func_without_sym_raises():
    with pytest.raises(ExprEvalError):
        _eval_expr("length(A, B)", {}, def_id="test", sym=None)

def test_plain_number_still_works():
    assert _eval_expr(3.14, {}, def_id="test") == sp.S(3.14)

def test_plain_expr_still_works():
    result = _eval_expr("pi / 2", {}, def_id="test")
    assert abs(float(result.evalf()) - 1.5707963) < 1e-6

def test_params_still_work():
    result = _eval_expr("2 * r", {"r": sp.S(3)}, def_id="test")
    assert float(result.evalf()) == 6.0

def test_arithmetic_with_geo():
    result = _eval_expr("length(A, B) * 2", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 6.0) < 1e-9

def test_sympy_reserved_name_collision():
    # "E" is sp.E (Euler's number) in SymPy globals; sym injection should override it
    sym_e = {"E": spg.Point(1, 0), "B": spg.Point(4, 0)}
    result = _eval_expr("length(E, B)", {}, def_id="test", sym=sym_e)
    assert abs(float(result.evalf()) - 3.0) < 1e-9

def test_radius_on_non_circle_raises():
    sym_pt = {"A": spg.Point(0, 0)}
    with pytest.raises(ExprEvalError):
        _eval_expr("radius(A)", {}, def_id="test", sym=sym_pt)

def test_angle_without_sym_raises():
    with pytest.raises(ExprEvalError):
        _eval_expr("angle(A, B, C)", {}, def_id="test", sym=None)

def test_length_unknown_id_raises():
    with pytest.raises(ExprEvalError):
        _eval_expr("length(X, Y)", {}, def_id="test", sym=SYM)

def test_sqrt_function():
    result = _eval_expr("sqrt(2)", {}, def_id="test")
    assert abs(float(result.evalf()) - 1.41421356) < 1e-6

def test_subtraction():
    result = _eval_expr("10 - 3", {}, def_id="test")
    assert float(result.evalf()) == 7.0

def test_unary_minus():
    result = _eval_expr("-r", {"r": sp.S(3)}, def_id="test")
    assert float(result.evalf()) == -3.0

def test_unary_plus():
    result = _eval_expr("+r", {"r": sp.S(3)}, def_id="test")
    assert float(result.evalf()) == 3.0

def test_negative_literal():
    result = _eval_expr("-2.5", {}, def_id="test")
    assert float(result.evalf()) == -2.5

def test_power():
    result = _eval_expr("2 ** 3", {}, def_id="test")
    assert float(result.evalf()) == 8.0

def test_modulo():
    result = _eval_expr("7 % 3", {}, def_id="test")
    assert float(result.evalf()) == 1.0

def test_parenthesized_arithmetic():
    result = _eval_expr("(2 + 3) * 4", {}, def_id="test")
    assert float(result.evalf()) == 20.0

def test_nested_arithmetic_precedence():
    result = _eval_expr("2 + 3 * 4 - 1", {}, def_id="test")
    assert float(result.evalf()) == 13.0

def test_sqrt_of_arithmetic_expression():
    result = _eval_expr("sqrt(3 * 3 + 4 * 4)", {}, def_id="test")
    assert abs(float(result.evalf()) - 5.0) < 1e-9

def test_multiple_params_combined():
    result = _eval_expr("a + b * c", {"a": sp.S(1), "b": sp.S(2), "c": sp.S(3)}, def_id="test")
    assert float(result.evalf()) == 7.0

def test_geo_function_combined_with_param():
    result = _eval_expr("length(A, B) + r", {"r": sp.S(1)}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 4.0) < 1e-9

def test_nested_geo_function_calls():
    # Heron's-formula-style nesting, as used by recipe/lower.py for triangle area.
    result = _eval_expr(
        "sqrt(length(A, B) * length(A, C) - length(B, C))",
        {},
        def_id="test",
        sym=SYM,
    )
    expected = (3.0 * 4.0 - 5.0) ** 0.5
    assert abs(float(result.evalf()) - expected) < 1e-9

def test_radius_combined_with_arithmetic():
    result = _eval_expr("radius(circ) * 2 + 1", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 11.0) < 1e-9

def test_angle_divided_by_constant():
    result = _eval_expr("angle(B, A, C) / 2", {}, def_id="test", sym=SYM)
    assert abs(float(result.evalf()) - 45.0) < 1e-6

def test_int_literal_still_works():
    assert _eval_expr(3, {}, def_id="test") == sp.S(3)

def test_rejects_arbitrary_code_execution():
    with pytest.raises(ExprEvalError):
        _eval_expr("__import__('os').popen('echo PWNED').read()", {}, def_id="test")

def test_rejects_attribute_access():
    with pytest.raises(ExprEvalError):
        _eval_expr("(1).__class__", {}, def_id="test")

def test_rejects_unknown_function_call():
    with pytest.raises(ExprEvalError):
        _eval_expr("eval('1')", {}, def_id="test")

def test_rejects_non_name_call_target():
    with pytest.raises(ExprEvalError):
        _eval_expr("length.__call__(A, B)", {}, def_id="test", sym=SYM)
