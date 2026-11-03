"""contains (circle, ellipse, arc, sector), tangent, circles_tangent, centroid
and the congruent_arcs radius comparison tolerate a fraction of the involved
radii / size, not an absolute distance: the same figure at any uniform scale
gets the same verdict. Compile-time ``pick`` on an arc keeps its own fixed
tight tolerance."""
from __future__ import annotations

import math

import pytest
import sympy as sp
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import DEFAULT_TOL, _check_one
from geometry_diagrams.ir.errors import PickError
from geometry_diagrams.ir.to_sympy import (
    Arc, EllipticalArc, EllipticalSector, PICK_ON_ARC_TOL, Sector, compile_defs,
    point_on_arc,
)

SCALES = [1e-3, 1.0, 1e3]
CANVAS = {"xmin": -1e6, "xmax": 1e6, "ymin": -1e6, "ymax": 1e6}

# A 0.1% miss passes the default 0.5% tolerance; a 1% miss fails it.
NEAR, FAR = 1.001, 1.01


def _p(x, y):
    return spg.Point2D(x, y)


def _check(sym, **kw):
    c = ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [], "checks": [kw]}).checks[0]
    return _check_one(c, sym, DEFAULT_TOL)


def _polar(r, deg):
    a = math.radians(deg)
    return _p(r * math.cos(a), r * math.sin(a))


# --- contains / not_contains -------------------------------------------------

def _containers(s):
    o = _p(0, 0)
    return {
        "circle": (spg.Circle(o, s), lambda k: _polar(s * k, 45)),
        "ellipse": (spg.Ellipse(o, 2 * s, s), lambda k: _p(2 * s * k, 0)),
        "arc": (Arc(center=o, start=_p(s, 0), end=_p(0, s), radius=sp.Float(s)), lambda k: _polar(s * k, 45)),
        "sector": (Sector(center=o, start=_p(s, 0), end=_p(0, s), radius=sp.Float(s)), lambda k: _polar(s * k, 45)),
        "elliptical_arc": (
            EllipticalArc(center=o, start=_p(2 * s, 0), end=_p(0, s), hradius=sp.Float(2 * s), vradius=sp.Float(s)),
            lambda k: _p(2 * s * math.cos(math.pi / 4) * k, s * math.sin(math.pi / 4) * k),
        ),
        "elliptical_sector": (
            EllipticalSector(center=o, start=_p(2 * s, 0), end=_p(0, s), hradius=sp.Float(2 * s), vradius=sp.Float(s)),
            lambda k: _p(2 * s * math.cos(math.pi / 4) * k, s * math.sin(math.pi / 4) * k),
        ),
    }


@pytest.mark.parametrize("s", SCALES)
@pytest.mark.parametrize("name", ["circle", "ellipse", "arc", "sector", "elliptical_arc", "elliptical_sector"])
def test_contains_curve_tolerates_a_fraction_of_the_radius(s, name):
    obj, at = _containers(s)[name]
    sym = {"c": obj, "near": at(NEAR), "far": at(FAR)}
    assert _check(sym, kind="contains", p="near", obj="c").passed
    assert not _check(sym, kind="contains", p="far", obj="c").passed


@pytest.mark.parametrize("s", SCALES)
@pytest.mark.parametrize("name", ["circle", "ellipse", "arc", "sector", "elliptical_arc", "elliptical_sector"])
def test_not_contains_curve_follows_the_relative_tolerance(s, name):
    obj, at = _containers(s)[name]
    sym = {"c": obj, "near": at(NEAR), "far": at(FAR)}
    assert not _check(sym, kind="not_contains", p="near", obj="c").passed
    assert _check(sym, kind="not_contains", p="far", obj="c").passed


# --- tangent -----------------------------------------------------------------

@pytest.mark.parametrize("s", SCALES)
@pytest.mark.parametrize("name", ["circle", "ellipse", "arc"])
def test_tangent_is_relative_to_the_radius(s, name):
    o = _p(0, 0)
    obj = {
        "circle": spg.Circle(o, s),
        "ellipse": spg.Ellipse(o, 2 * s, s),
        "arc": Arc(center=o, start=_p(-s, 0), end=_p(s, 0), radius=sp.Float(s)),
    }[name]
    sym = {
        "c": obj,
        "near": spg.Line(_p(-1, s * NEAR), _p(1, s * NEAR)),
        "far": spg.Line(_p(-1, s * FAR), _p(1, s * FAR)),
    }
    if name == "arc":  # the arc's top half; the touch point (0, s) is on its sweep
        sym["c"] = Arc(center=o, start=_p(s, 0), end=_p(-s, 0), radius=sp.Float(s))
    assert _check(sym, kind="tangent", line="near", circle="c").passed
    assert not _check(sym, kind="tangent", line="far", circle="c").passed


# --- circles_tangent ---------------------------------------------------------

@pytest.mark.parametrize("s", SCALES)
def test_circles_tangent_external_is_relative(s):
    sym = {
        "a": spg.Circle(_p(0, 0), s),
        "near": spg.Circle(_p(2 * s * NEAR, 0), s),
        "far": spg.Circle(_p(2 * s * FAR, 0), s),
    }
    assert _check(sym, kind="circles_tangent", c1="a", c2="near").passed
    assert not _check(sym, kind="circles_tangent", c1="a", c2="far").passed


@pytest.mark.parametrize("s", SCALES)
def test_circles_tangent_internal_is_relative(s):
    sym = {
        "big": spg.Circle(_p(0, 0), 2 * s),
        "near": spg.Circle(_p(s * 1.002, 0), s),
        "far": spg.Circle(_p(s * 1.03, 0), s),
    }
    assert _check(sym, kind="circles_tangent", c1="big", c2="near").passed
    assert not _check(sym, kind="circles_tangent", c1="big", c2="far").passed


@pytest.mark.parametrize("s", SCALES)
def test_circles_tangent_identical_circles_still_fail(s):
    sym = {"a": spg.Circle(_p(0, 0), s), "b": spg.Circle(_p(0, 0), s)}
    assert not _check(sym, kind="circles_tangent", c1="a", c2="b").passed


# --- centroid ----------------------------------------------------------------

@pytest.mark.parametrize("s", SCALES)
def test_centroid_is_relative_to_the_triangle_size(s):
    base = {"A": _p(0, 0), "B": _p(3 * s, 0), "C": _p(0, 3 * s)}
    near = {**base, "G": _p(s * 1.01, s)}
    far = {**base, "G": _p(s * 1.1, s)}
    chk = dict(kind="centroid", g="G", a="A", b="B", c="C")
    assert _check(near, **chk).passed
    assert not _check(far, **chk).passed


# --- congruent_arcs ----------------------------------------------------------

def _arcs(s, k):
    defs = [
        {"id": "O1", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "S1", "kind": "point_fixed", "x": s, "y": 0},
        {"id": "E1", "kind": "point_fixed", "x": 0, "y": s},
        {"id": "a1", "kind": "arc_center_start_end", "center": "O1", "start": "S1", "end": "E1"},
        {"id": "O2", "kind": "point_fixed", "x": 5 * s, "y": 0},
        {"id": "S2", "kind": "point_fixed", "x": 5 * s + s * k, "y": 0},
        {"id": "E2", "kind": "point_fixed", "x": 5 * s, "y": s * k},
        {"id": "a2", "kind": "arc_center_start_end", "center": "O2", "start": "S2", "end": "E2"},
        # elliptical pair, same quarter sweep
        {"id": "P1", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "T1", "kind": "point_fixed", "x": 2 * s, "y": 0},
        {"id": "U1", "kind": "point_fixed", "x": 0, "y": s},
        {"id": "e1", "kind": "elliptical_arc_center_start_end", "center": "P1",
         "hradius": 2 * s, "vradius": s, "start": "T1", "end": "U1"},
        {"id": "P2", "kind": "point_fixed", "x": 9 * s, "y": 0},
        {"id": "T2", "kind": "point_fixed", "x": 9 * s + 2 * s * k, "y": 0},
        {"id": "U2", "kind": "point_fixed", "x": 9 * s, "y": s * k},
        {"id": "e2", "kind": "elliptical_arc_center_start_end", "center": "P2",
         "hradius": 2 * s * k, "vradius": s * k, "start": "T2", "end": "U2"},
    ]
    return compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": defs}))


@pytest.mark.parametrize("s", SCALES)
@pytest.mark.parametrize("pair", [("a1", "a2"), ("e1", "e2")])
def test_congruent_arcs_radii_are_relative(s, pair):
    arcs = list(pair)
    assert _check(_arcs(s, NEAR), kind="congruent_arcs", arcs=arcs).passed
    assert not _check(_arcs(s, FAR), kind="congruent_arcs", arcs=arcs).passed


# --- pick on arcs keeps its own tight tolerance ------------------------------

def _pick_defs(s, radius_factor):
    """A line meets the circle |O|=s at two points; the arc `arc2` is centred
    at the origin with radius s*radius_factor, so the candidates lie
    s*(radius_factor-1) off it."""
    r2 = s * radius_factor
    return [
        {"id": "O", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "R", "kind": "point_fixed", "x": s, "y": 0},
        {"id": "c", "kind": "circle_center_point", "center": "O", "through": "R"},
        {"id": "P", "kind": "point_fixed", "x": s / 2, "y": -2 * s},
        {"id": "Q", "kind": "point_fixed", "x": s / 2, "y": 2 * s},
        {"id": "L", "kind": "line_through", "p": "P", "q": "Q"},
        {"id": "S2", "kind": "point_fixed", "x": r2, "y": 0},
        {"id": "E2", "kind": "point_fixed", "x": 0, "y": r2},
        {"id": "arc2", "kind": "arc_center_start_end", "center": "O", "start": "S2", "end": "E2"},
        {"id": "X", "kind": "point_intersection", "obj1": "c", "obj2": "L",
         "pick": {"kind": "on_object", "obj": "arc2"}},
    ]


@pytest.mark.parametrize("s", SCALES)
def test_pick_on_arc_keeps_its_tight_tolerance(s):
    # Exactly on the arc: resolves to the upper candidate.
    sym = compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": _pick_defs(s, 1.0)}))
    assert abs(float(sym["X"].x) - s / 2) < 1e-9 * max(s, 1)
    assert float(sym["X"].y) > 0
    # 0.01% off the arc: well inside the check's relative tolerance, yet pick
    # still rejects every candidate.
    with pytest.raises(PickError, match="no candidate lies on"):
        compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": _pick_defs(s, 1.0001)}))


def test_point_on_arc_tolerance_is_the_callers():
    arc = Arc(center=_p(0, 0), start=_p(1, 0), end=_p(0, 1), radius=sp.Integer(1))
    p = _polar(1.001, 45)
    assert not point_on_arc(p, arc, PICK_ON_ARC_TOL)
    assert point_on_arc(p, arc, 5e-3)
