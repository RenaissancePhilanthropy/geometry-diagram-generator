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


def test_corner_square_at_right_angle_vertex_compiles():
    """Corner-square pattern: point_along+perpendicular+intersection → right angles."""
    from recipe.lower import lower_to_ir
    from ir.to_sympy import compile_defs
    from recipe.dsl import RecipeDSL

    dsl = RecipeDSL.model_validate({
        "mode": "grid",
        "construction": [
            {"op": "point", "id": "B", "coords": [0, 0]},
            {"op": "point", "id": "A", "coords": [3, 0]},
            {"op": "point", "id": "C", "coords": [0, 4]},
            {"op": "segment", "id": "seg_BA", "endpoints": ["B", "A"]},
            {"op": "segment", "id": "seg_BC", "endpoints": ["B", "C"]},
            {"op": "point_along", "id": "S1", "on": "seg_BA",
             "from": "B", "distance": 0.4, "toward": "A"},
            {"op": "point_along", "id": "S3", "on": "seg_BC",
             "from": "B", "distance": 0.4, "toward": "C"},
            {"op": "perpendicular", "id": "perp_S1", "to_line": "seg_BA", "through": "S1"},
            {"op": "perpendicular", "id": "perp_S3", "to_line": "seg_BC", "through": "S3"},
            {"op": "intersection", "id": "S2", "of": ["perp_S1", "perp_S3"],
             "selector": {"kind": "closest_to", "p": "B"}},
            {"op": "polygon", "id": "corner_sq", "vertices": ["B", "S1", "S2", "S3"]},
            {"op": "fill", "id": "shade_sq", "obj": "corner_sq", "opacity": 0.3},
            {"op": "segment", "id": "seg_AC", "endpoints": ["A", "C"]},
            {"op": "point_foot", "id": "foot_H", "source": "S2", "onto": "seg_AC"},
            {"op": "segment", "id": "dist_seg", "endpoints": ["S2", "foot_H"]},
        ],
        "annotations": {"auto_draw_all": True, "auto_label_points": False},
    })
    ir_obj = lower_to_ir(dsl)
    sym = compile_defs(ir_obj)

    # S2 should be at approximately (0.4, 0.4)
    S2 = sym["S2"]
    assert abs(float(S2.x.evalf()) - 0.4) < 1e-4
    assert abs(float(S2.y.evalf()) - 0.4) < 1e-4

    assert "foot_H" in sym
    assert "dist_seg" in sym


def test_fill_on_polygon_compiles_to_fill_render_op():
    """FillOp referencing a polygon id lowers to a Fill render op."""
    from recipe.lower import lower_to_ir
    from recipe.dsl import RecipeDSL
    from ir.ir import Fill

    dsl = RecipeDSL.model_validate({
        "mode": "grid",
        "construction": [
            {"op": "point", "id": "A", "coords": [0, 5]},
            {"op": "point", "id": "B", "coords": [4, 5]},
            {"op": "point", "id": "C", "coords": [4, 0]},
            {"op": "polygon", "id": "region", "vertices": ["A", "B", "C"]},
            {"op": "fill", "id": "shade", "obj": "region", "opacity": 0.4},
        ],
        "annotations": {"auto_draw_all": True, "auto_label_points": False},
    })
    ir_obj = lower_to_ir(dsl)
    fill_ops = [r for r in ir_obj.render if isinstance(r, Fill)]
    assert len(fill_ops) == 1
    assert fill_ops[0].obj == "region"
    assert abs(fill_ops[0].opacity - 0.4) < 1e-6
