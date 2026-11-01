"""collinear / contains / parallel / perpendicular honour a check's ``tol`` on
float coordinates (SymPy's exact tests reject coordinates that agree only up
to rounding or a small deliberate offset)."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.to_sympy import compile_defs

SCALES = [1.0, 0.01, 100.0]


def _sym(points: dict[str, tuple[float, float]], *extra):
    defs = [{"id": k, "kind": "point_fixed", "x": v[0], "y": v[1]} for k, v in points.items()]
    d = ir.DiagramIR.model_validate({
        "canvas": {"xmin": -500, "xmax": 500, "ymin": -500, "ymax": 500},
        "define": defs + list(extra),
    })
    return compile_defs(d)


def _run(sym, check):
    c = ir.DiagramIR.model_validate({
        "canvas": {"xmin": -500, "xmax": 500, "ymin": -500, "ymax": 500},
        "define": [], "checks": [check],
    }).checks[0]
    return run_checks([c], sym)[0].passed


def _seg(i, a, b):
    return {"id": i, "kind": "segment", "a": a, "b": b}


@pytest.mark.parametrize("s", SCALES)
def test_collinear(s):
    sym = _sym({"A": (0, 0), "B": (1 * s, 1 * s), "C": (2.0 * s, 2.0 * s * 1.001)})
    # off the line by ~0.05% of the extent: within the default tolerance
    assert _run(sym, {"kind": "collinear", "points": ["A", "B", "C"]})
    assert not _run(sym, {"kind": "collinear", "points": ["A", "B", "C"], "tol": 1e-9})
    far = _sym({"A": (0, 0), "B": (1 * s, 1 * s), "C": (2.0 * s, 2.0 * s * 1.1)})
    assert not _run(far, {"kind": "collinear", "points": ["A", "B", "C"]})
    assert _run(far, {"kind": "collinear", "points": ["A", "B", "C"], "tol": 0.1})


@pytest.mark.parametrize("s", SCALES)
def test_contains_line_ray_segment(s):
    pts = {"A": (0, 0), "B": (4 * s, 0), "P": (2 * s, 0.004 * s), "Q": (5 * s, 0.0), "R": (-0.003 * s, 0)}
    sym = _sym(pts, _seg("sg", "A", "B"),
               {"id": "ln", "kind": "line_through", "p": "A", "q": "B"},
               {"id": "ry", "kind": "ray", "a": "A", "b": "B"})
    for obj in ("sg", "ln", "ry"):
        assert _run(sym, {"kind": "contains", "p": "P", "obj": obj})
        assert not _run(sym, {"kind": "contains", "p": "P", "obj": obj, "tol": 1e-6})
    # beyond the endpoint: on the line and ray, not on the segment
    assert not _run(sym, {"kind": "contains", "p": "Q", "obj": "sg"})
    assert _run(sym, {"kind": "contains", "p": "Q", "obj": "ln"})
    assert _run(sym, {"kind": "contains", "p": "Q", "obj": "ry"})
    # just behind the ray's origin, within tolerance; far behind is not
    assert _run(sym, {"kind": "contains", "p": "R", "obj": "ry"})
    # not_contains keeps its strict meaning for a point merely near the object
    assert _run(sym, {"kind": "not_contains", "p": "P", "obj": "sg"})


@pytest.mark.parametrize("s", SCALES)
def test_parallel(s):
    sym = _sym({"A": (0, 0), "B": (4 * s, 0), "C": (0, s), "D": (4 * s, 1.004 * s)},
               _seg("l1", "A", "B"), _seg("l2", "C", "D"))
    assert _run(sym, {"kind": "parallel", "l1": "l1", "l2": "l2"})
    assert not _run(sym, {"kind": "parallel", "l1": "l1", "l2": "l2", "tol": 1e-6})
    assert _run(sym, {"kind": "not_parallel", "l1": "l1", "l2": "l2"})


@pytest.mark.parametrize("s", SCALES)
def test_perpendicular(s):
    sym = _sym({"A": (0, 0), "B": (4 * s, 0), "C": (0.005 * s, s), "D": (0, -s)},
               _seg("l1", "A", "B"), _seg("l2", "C", "D"))
    assert _run(sym, {"kind": "perpendicular", "l1": "l1", "l2": "l2"})
    assert not _run(sym, {"kind": "perpendicular", "l1": "l1", "l2": "l2", "tol": 1e-6})
    skew = _sym({"A": (0, 0), "B": (4 * s, 0), "C": (0.5 * s, s), "D": (0, -s)},
                _seg("l1", "A", "B"), _seg("l2", "C", "D"))
    assert not _run(skew, {"kind": "perpendicular", "l1": "l1", "l2": "l2"})
