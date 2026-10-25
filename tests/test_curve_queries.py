"""Length / radius / area / perimeter queries for the circle-ellipse family.

Every case goes through ``dispatch_query`` (the entry point agents call) and,
for the numbers, the underlying ``query_*`` functions. References are
independent of the implementation: closed forms for circles, circular sectors
and all areas; direct mpmath quadrature of the arc-length integrand for
elliptical lengths.
"""

from __future__ import annotations

import json
import math

import mpmath
import pytest
import sympy
import sympy.geometry as spg

from geometry_diagrams.ir.queries import query_area, query_length, query_perimeter, query_radius
from geometry_diagrams.ir.to_sympy import Arc, EllipticalArc, EllipticalSector, Sector
from geometry_diagrams.strategies.structured import dispatch_query

TAU = 2 * math.pi
O = spg.Point(0, 0)


def _ask(sym, query_type, obj_id, key="object"):
    return json.loads(dispatch_query(sym, query_type, {key: obj_id}))


def _quad_length(a, b, t0, t1):
    with mpmath.workdps(30):
        f = lambda t: mpmath.sqrt((a * mpmath.sin(t)) ** 2 + (b * mpmath.cos(t)) ** 2)
        n = max(1, int(math.ceil((t1 - t0) / (math.pi / 2))))
        return float(mpmath.quad(f, [t0 + (t1 - t0) * i / n for i in range(n + 1)]))


def _pt(cx, cy, a, b, t):
    return spg.Point(cx + a * math.cos(t), cy + b * math.sin(t))


def _radial(a, b, t):
    return math.hypot(a * math.cos(t), b * math.sin(t))


def _ell(cls, a, b, t0, t1, cx=0.0, cy=0.0):
    """Elliptical arc/sector whose CCW parametric sweep is exactly [t0, t1]."""
    reflex = (t1 - t0) > math.pi
    return cls(spg.Point(cx, cy), _pt(cx, cy, a, b, t0), _pt(cx, cy, a, b, t1),
               sympy.Float(a), sympy.Float(b), reflex)


# (hradius, vradius, t0, t1): eccentric 10:1, reflex, and axis-crossing sweeps
ELL_CASES = {
    "minor": (5.0, 3.0, 0.3, 1.9),
    "eccentric": (10.0, 1.0, 0.2, 1.2),
    "eccentric_tall": (1.0, 10.0, 0.4, 2.5),
    "reflex": (5.0, 3.0, 0.5, 5.0),
    "eccentric_reflex": (10.0, 1.0, 0.1, 4.4),
    "axis_crossing": (10.0, 1.0, -0.6, 0.7),
    "reflex_axis_crossing": (5.0, 3.0, -2.0, 2.5),
}


@pytest.fixture
def sym():
    A, B, C = spg.Point(0, 0), spg.Point(3, 0), spg.Point(3, 4)
    s = {
        "seg": spg.Segment(A, B),
        "tri": spg.Triangle(A, B, C),
        "circ": spg.Circle(O, 2),
        "ell": spg.Ellipse(O, 5, 3),
        "arc": Arc(O, spg.Point(2, 0), spg.Point(0, 2), sympy.Integer(2), False),
        "arc_reflex": Arc(O, spg.Point(2, 0), spg.Point(0, 2), sympy.Integer(2), True),
        "sec": Sector(O, spg.Point(2, 0), spg.Point(0, 2), sympy.Integer(2), False),
        "sec_reflex": Sector(O, spg.Point(2, 0), spg.Point(0, 2), sympy.Integer(2), True),
    }
    for name, (a, b, t0, t1) in ELL_CASES.items():
        s[f"earc_{name}"] = _ell(EllipticalArc, a, b, t0, t1)
        s[f"esec_{name}"] = _ell(EllipticalSector, a, b, t0, t1)
    return s


# --- length ------------------------------------------------------------------


class TestLength:
    def test_segment_unchanged(self, sym):
        assert _ask(sym, "length", "seg", "segment") == {"length": pytest.approx(3.0)}

    def test_circular_arc_and_sector(self, sym):
        assert _ask(sym, "length", "arc", "segment")["length"] == pytest.approx(math.pi, rel=1e-12)
        assert _ask(sym, "length", "sec", "segment")["length"] == pytest.approx(math.pi, rel=1e-12)

    def test_reflex_circular(self, sym):
        want = 3 * math.pi
        assert _ask(sym, "length", "arc_reflex", "segment")["length"] == pytest.approx(want, rel=1e-12)
        assert _ask(sym, "length", "sec_reflex", "segment")["length"] == pytest.approx(want, rel=1e-12)

    @pytest.mark.parametrize("name", list(ELL_CASES))
    @pytest.mark.parametrize("kind", ["earc", "esec"])
    def test_elliptical(self, sym, kind, name):
        a, b, t0, t1 = ELL_CASES[name]
        want = _quad_length(a, b, t0, t1)
        assert _ask(sym, "length", f"{kind}_{name}", "segment")["length"] == pytest.approx(want, rel=1e-9)
        assert query_length(sym, f"{kind}_{name}")["length"] == pytest.approx(want, rel=1e-9)

    def test_id_key_accepted(self, sym):
        assert _ask(sym, "length", "arc", "id")["length"] == pytest.approx(math.pi)

    @pytest.mark.parametrize("obj", ["circ", "ell"])
    def test_full_curve_points_to_perimeter(self, sym, obj):
        err = _ask(sym, "length", obj, "segment")["error"]
        assert "perimeter" in err and obj in err

    def test_polygon_rejected(self, sym):
        err = _ask(sym, "length", "tri", "segment")["error"]
        assert "'tri' is not a Segment, arc or sector" in err and "got Triangle" in err

    def test_object_key_accepted(self, sym):
        assert _ask(sym, "length", "arc", "object")["length"] == pytest.approx(math.pi)
        assert _ask(sym, "length", "arc", "object") == query_length(sym, "arc")


# --- radius ------------------------------------------------------------------


class TestRadius:
    def test_circle_arc_sector_keep_single_radius(self, sym):
        for obj in ("circ", "arc", "arc_reflex", "sec", "sec_reflex"):
            out = _ask(sym, "radius", obj, "circle")
            assert set(out) == {"radius"}, obj
            assert out["radius"] == pytest.approx(2.0)

    def test_ellipse_returns_both_radii(self, sym):
        assert _ask(sym, "radius", "ell", "circle") == {"hradius": 5.0, "vradius": 3.0}

    @pytest.mark.parametrize("kind", ["earc", "esec"])
    def test_elliptical_arc_and_sector(self, sym, kind):
        assert _ask(sym, "radius", f"{kind}_eccentric", "circle") == {"hradius": 10.0, "vradius": 1.0}
        assert query_radius(sym, f"{kind}_eccentric_tall") == {"hradius": 1.0, "vradius": 10.0}

    def test_segment_rejected(self, sym):
        err = _ask(sym, "radius", "seg", "circle")["error"]
        assert "'seg' is not a Circle, Ellipse, arc or sector" in err

    def test_object_key_accepted(self, sym):
        assert _ask(sym, "radius", "circ", "object")["radius"] == pytest.approx(2.0)


# --- area --------------------------------------------------------------------


class TestArea:
    def test_polygon_unchanged(self, sym):
        assert _ask(sym, "area", "tri")["area"] == pytest.approx(6.0)

    def test_circle_and_ellipse(self, sym):
        assert _ask(sym, "area", "circ")["area"] == pytest.approx(math.pi * 4)
        assert _ask(sym, "area", "ell")["area"] == pytest.approx(math.pi * 15)

    def test_circular_sectors(self, sym):
        assert _ask(sym, "area", "sec")["area"] == pytest.approx(math.pi * 4 / 4)
        assert _ask(sym, "area", "sec_reflex")["area"] == pytest.approx(math.pi * 4 * 3 / 4)

    @pytest.mark.parametrize("name", list(ELL_CASES))
    def test_elliptical_sector(self, sym, name):
        a, b, t0, t1 = ELL_CASES[name]
        want = a * b / 2 * (t1 - t0)
        assert _ask(sym, "area", f"esec_{name}")["area"] == pytest.approx(want, rel=1e-12)
        assert query_area(sym, f"esec_{name}")["area"] == pytest.approx(want, rel=1e-12)

    def test_off_center_elliptical_sector_same_area(self):
        s = {"e": _ell(EllipticalSector, 10.0, 1.0, 0.2, 1.2, cx=7.0, cy=-3.0)}
        assert _ask(s, "area", "e")["area"] == pytest.approx(10 * 1 / 2 * 1.0, rel=1e-12)

    @pytest.mark.parametrize("obj", ["arc", "arc_reflex", "earc_minor", "earc_reflex"])
    def test_open_arc_is_a_clean_error(self, sym, obj):
        err = _ask(sym, "area", obj)["error"]
        assert "an open arc has no area; use a sector" in err
        assert obj in err

    def test_segment_rejected(self, sym):
        err = _ask(sym, "area", "seg")["error"]
        assert "'seg' is not a Polygon, circle, ellipse or sector" in err


# --- perimeter ---------------------------------------------------------------


class TestPerimeter:
    def test_polygon_unchanged(self, sym):
        assert _ask(sym, "perimeter", "tri")["perimeter"] == pytest.approx(12.0)

    def test_circle_and_ellipse(self, sym):
        assert _ask(sym, "perimeter", "circ")["perimeter"] == pytest.approx(TAU * 2)
        want = _quad_length(5.0, 3.0, 0.0, TAU)
        assert _ask(sym, "perimeter", "ell")["perimeter"] == pytest.approx(want, rel=1e-9)

    def test_circular_sector_is_two_radii_plus_arc(self, sym):
        assert _ask(sym, "perimeter", "sec")["perimeter"] == pytest.approx(4 + math.pi, rel=1e-12)
        assert _ask(sym, "perimeter", "sec_reflex")["perimeter"] == pytest.approx(4 + 3 * math.pi, rel=1e-12)

    @pytest.mark.parametrize("name", list(ELL_CASES))
    def test_elliptical_sector(self, sym, name):
        a, b, t0, t1 = ELL_CASES[name]
        want = _radial(a, b, t0) + _radial(a, b, t1) + _quad_length(a, b, t0, t1)
        assert _ask(sym, "perimeter", f"esec_{name}")["perimeter"] == pytest.approx(want, rel=1e-9)
        assert query_perimeter(sym, f"esec_{name}")["perimeter"] == pytest.approx(want, rel=1e-9)

    def test_elliptical_sector_radii_are_endpoint_distances_not_axes(self):
        # a quarter of a 10:1 ellipse: the straight edges are 10 and 1 long.
        s = {"e": _ell(EllipticalSector, 10.0, 1.0, 0.0, math.pi / 2)}
        want = 10 + 1 + _quad_length(10.0, 1.0, 0.0, math.pi / 2)
        assert _ask(s, "perimeter", "e")["perimeter"] == pytest.approx(want, rel=1e-9)

    @pytest.mark.parametrize("obj", ["arc", "earc_minor"])
    def test_open_arc_points_to_length(self, sym, obj):
        err = _ask(sym, "perimeter", obj)["error"]
        assert "use length" in err and obj in err

    def test_segment_rejected(self, sym):
        err = _ask(sym, "perimeter", "seg")["error"]
        assert "'seg' is not a Polygon, circle, ellipse or sector" in err


# --- degenerate (zero-radius) curves -------------------------------------------


class TestDegenerateSector:
    """A zero-radius sector gets a clean, named error from every curve query
    (never a bare ZeroDivisionError message)."""

    @pytest.fixture
    def zero(self):
        return {"z": Sector(O, O, spg.Point(1, 0), sympy.Integer(0), False)}

    @pytest.mark.parametrize("qt", ["length", "area", "perimeter"])
    def test_clean_degenerate_message(self, zero, qt):
        err = _ask(zero, qt, "z")["error"]
        assert "degenerate radius" in err
        assert "division" not in err


# --- the description models see ------------------------------------------------


def _descriptions():
    from evals.run import _make_query_tool
    from geometry_diagrams import facade
    from tests.test_prism_true_length import _agent_query_tool_description, _strategy_classes

    for features in (frozenset(), frozenset({"solids"})):
        for cls in _strategy_classes():
            yield f"{cls.__name__}/{sorted(features)}", _agent_query_tool_description(cls, features)
        yield f"facade/{sorted(features)}", facade.query_diagram_description(features)
        yield f"eval/{sorted(features)}", _make_query_tool({}, features).description


def test_every_query_description_states_the_curve_family_support():
    for name, text in _descriptions():
        for word in ("arc", "sector", "ellipse", "hradius"):
            assert word in text, (name, word)
