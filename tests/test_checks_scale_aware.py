"""Check tolerances are relative: the same figure gets the same verdict at
every scale (1, 0.1, 0.01, 100)."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.angle_pairs import _side
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.to_sympy import compile_defs

SCALES = [1.0, 0.1, 0.01, 100.0]
CANVAS = {"xmin": -1000, "xmax": 1000, "ymin": -1000, "ymax": 1000}


def _sym(points, *extra):
    defs = [{"id": k, "kind": "point_fixed", "x": v[0], "y": v[1]} for k, v in points.items()]
    return compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": defs + list(extra)}))


def _run(sym, check):
    c = ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [], "checks": [check]}).checks[0]
    return run_checks([c], sym)[0].passed


def _seg(i, a, b):
    return {"id": i, "kind": "segment", "a": a, "b": b}


@pytest.mark.parametrize("s", SCALES)
def test_opposite_and_same_side(s):
    pts = {"A": (0, 0), "B": (s, 0), "P": (0.3 * s, 0.5 * s), "Q": (0.4 * s, -0.5 * s),
           "R": (0.4 * s, 0.5 * s), "N": (0.3 * s, 0.001 * s), "M": (0.4 * s, -0.001 * s)}
    sym = _sym(pts)

    def side(kind, p, q):
        return _run(sym, {"kind": kind, "p": p, "q": q, "line_a": "A", "line_b": "B"})

    assert side("opposite_side", "P", "Q")
    assert not side("same_side", "P", "Q")
    assert side("same_side", "P", "R")
    assert not side("opposite_side", "P", "R")
    # essentially on the line: neither side
    assert not side("opposite_side", "N", "M")
    assert not side("same_side", "N", "R")


@pytest.mark.parametrize("s", SCALES)
def test_equal_length(s):
    pts = {"A": (0, 0), "B": (s, 0), "C": (0, 1.001 * s), "D": (0, 0.5 * s), "E": (1.1 * s, 3 * s)}
    sym = _sym(pts, _seg("ab", "A", "B"), _seg("ac", "A", "C"), _seg("ad", "A", "D"))
    assert _run(sym, {"kind": "equal_length", "segs": ["ab", "ac"]})
    assert not _run(sym, {"kind": "equal_length", "segs": ["ab", "ad"]})


@pytest.mark.parametrize("s", SCALES)
def test_distinct_points(s):
    sym = _sym({"A": (3 * s, 4 * s), "B": (3 * s, 4 * s * 1.0000001), "C": (3 * s * 1.2, 4 * s)})
    assert not _run(sym, {"kind": "distinct_points", "a": "A", "b": "B"})
    assert _run(sym, {"kind": "distinct_points", "a": "A", "b": "C"})


@pytest.mark.parametrize("s", SCALES)
def test_congruent_triangles(s):
    pts = {"A": (0, 0), "B": (3 * s, 0), "C": (0, 4 * s),
           "D": (10 * s, 10 * s), "E": (13 * s, 10 * s), "F": (10 * s, 14.004 * s),
           "G": (20 * s, 0), "H": (26 * s, 0), "I": (20 * s, 8 * s)}
    sym = _sym(pts, {"id": "t1", "kind": "triangle", "a": "A", "b": "B", "c": "C"},
               {"id": "t2", "kind": "triangle", "a": "D", "b": "E", "c": "F"},
               {"id": "t3", "kind": "triangle", "a": "G", "b": "H", "c": "I"})
    assert _run(sym, {"kind": "congruent_triangles", "t1": "t1", "t2": "t2"})
    assert not _run(sym, {"kind": "congruent_triangles", "t1": "t1", "t2": "t3"})


@pytest.mark.parametrize("s", SCALES)
def test_equal_radius(s):
    sym = _sym({"O": (0, 0), "P": (10 * s, 0)},
               {"id": "c1", "kind": "circle_center_radius", "center": "O", "radius": s},
               {"id": "c2", "kind": "circle_center_radius", "center": "P", "radius": 1.001 * s},
               {"id": "c3", "kind": "circle_center_radius", "center": "P", "radius": 1.5 * s})
    assert _run(sym, {"kind": "equal_radius", "circles": ["c1", "c2"]})
    assert not _run(sym, {"kind": "equal_radius", "circles": ["c1", "c3"]})


@pytest.mark.parametrize("s", SCALES)
def test_angle_pairs_side(s):
    sym = _sym({"A": (0, 0), "B": (s, 0), "P": (0.3 * s, 0.5 * s), "N": (0.3 * s, 1e-12 * s)})
    assert _side(sym["A"], sym["B"], sym["P"]) == 1
    with pytest.raises(ValueError):
        _side(sym["A"], sym["B"], sym["N"])
