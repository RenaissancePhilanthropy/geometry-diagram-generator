# tests/test_recipe_pipeline_smoke.py
"""Integration test: RecipeDSL → DiagramIR → compile_defs → ir_to_tikz.

Does NOT require the Docker renderer (skips render_tikz).
Verifies lowering + SymPy compilation + TikZ codegen work end-to-end.
"""
import pytest
from recipe.dsl import RecipeDSL, DSLAnnotations, TriangleOp, AltitudeOp, CircumcircleOp
from recipe.lower import lower_to_ir
from ir.to_sympy import compile_defs
from ir.checks import run_checks
from ir.to_tikz import ir_to_tikz


@pytest.fixture
def altitude_dsl():
    return RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"angle_A": 60, "angle_B": 70, "side_AB": 4}),
            AltitudeOp(id="alt_A", from_vertex="A", to_side=["B","C"], foot="H"),
        ],
        annotations=DSLAnnotations(auto_draw_all=True, auto_label_points=True),
    )


def test_altitude_compiles_to_sympy(altitude_dsl):
    ir = lower_to_ir(altitude_dsl)
    sym = compile_defs(ir)
    # Should have all key objects
    assert "A" in sym and "B" in sym and "C" in sym
    assert "H" in sym  # foot point
    assert "alt_A" in sym  # altitude line


def test_altitude_checks_pass(altitude_dsl):
    ir = lower_to_ir(altitude_dsl)
    sym = compile_defs(ir)
    results = run_checks(ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    assert len(must_failures) == 0, [r.message for r in must_failures]


def test_altitude_generates_tikz(altitude_dsl):
    ir = lower_to_ir(altitude_dsl)
    sym = compile_defs(ir)
    tikz = ir_to_tikz(ir, sym)
    assert "\\tkzDefPoint" in tikz
    assert len(tikz) > 100


def test_circumcircle_compiles():
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
            CircumcircleOp(id="cc", of="T", center="O"),
        ],
        annotations=DSLAnnotations(auto_draw_all=True, auto_label_points=True),
    )
    ir = lower_to_ir(dsl)
    sym = compile_defs(ir)
    results = run_checks(ir.checks, sym)
    must_failures = [r for r in results if not r.passed and r.check.level == "must"]
    assert len(must_failures) == 0, [r.message for r in must_failures]
    tikz = ir_to_tikz(ir, sym)
    assert "\\tkzDefPoint" in tikz
