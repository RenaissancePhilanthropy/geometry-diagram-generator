"""Prism compile cost: projections are cached. The faces keep SymPy's validating
polygon constructor on purpose: it is what rejects a degenerate (tiny) prism
with an IRCompileError (tests/test_post_review_fixes.py)."""
from __future__ import annotations

import time

import pytest
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import check_render_angles
from geometry_diagrams.ir.derived import REGISTRY, effective_defs
from geometry_diagrams.ir.prism import Projection, projection_for
from geometry_diagrams.ir.to_sympy import compile_defs

CANVAS = {"xmin": -5, "xmax": 15, "ymin": -5, "ymax": 15}
# A generous bound: the validating constructor took several seconds here.
BUDGET_SECONDS = 8.0


def _diagram(render=(), **prism_kw):
    return ir.DiagramIR.model_validate({
        "canvas": CANVAS,
        "define": [
            {"id": "O", "kind": "point_fixed", "x": 0, "y": 0},
            {"id": "P", "kind": "rectangular_prism", "origin": "O",
             "length": 4, "width": 3, "height": 2, **prism_kw},
        ],
        "render": list(render),
    })


def test_custom_oblique_projection_compiles_within_budget():
    diagram = _diagram(depth_angle=37.5, depth_scale=0.43)
    start = time.monotonic()
    compile_defs(diagram)
    assert time.monotonic() - start < BUDGET_SECONDS


def test_angle_marks_at_prism_corners_still_validate():
    diagram = _diagram(render=[
        ir.MarkRightAngles(angles=[ir.AnglePoints(a="P_v100", o="P_v000", b="P_v010")]),
    ])
    sym = compile_defs(diagram)
    assert check_render_angles(diagram, sym) == []


def test_projection_is_cached():
    assert projection_for("oblique", "right", 37.5, 0.43) is projection_for("oblique", "right", 37.5, 0.43)
    proj = projection_for()
    assert isinstance(proj, Projection)
    assert proj.viewer is proj.viewer
    with pytest.raises(ValueError):
        projection_for("isometric", "right", 30.0, None)
    with pytest.raises(ValueError):
        projection_for("isometric", "right", 30.0, None)
