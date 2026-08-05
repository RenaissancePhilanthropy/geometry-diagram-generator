# tests/test_pydsl_arcs_sectors.py
"""Tests for pydsl's arc/sector primitives and the circle() constructor.
circle() wraps the existing CircleCenterRadius IR def (same class
incircle()'s literal-radius branch already uses); arc()/sector() wrap
ArcCenterStartEnd/SectorCenterStartEnd, both already fully supported by
to_sympy.py/to_tikz.py/to_svg.py — this file is pure pydsl-layer exposure,
plus a validation guard against a real off-circle-point rendering bug
found during spec review, and a rounding fix for a float-precision bug in
regular_sectors() at n=2 (see the design spec's "Two real footguns"
section for the full analysis of both)."""
import math

import pytest

from geometry_diagrams.pydsl.api import circle, point
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_circle_records_circle_center_radius_with_correct_fields():
    from geometry_diagrams.ir.ir import CircleCenterRadius

    with new_builder_context() as builder:
        c = point(2.0, 3.0)
        result = circle(c, 5.0)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, CircleCenterRadius) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].center == c.id
    assert defs[0].radius == 5.0
    assert result.center.id == c.id
    assert result.radius == 5.0


def test_circle_rejects_non_positive_radius():
    with new_builder_context():
        c = point(0.0, 0.0)
        with pytest.raises(ValueError, match="positive"):
            circle(c, 0.0)
        with pytest.raises(ValueError, match="positive"):
            circle(c, -3.0)


from geometry_diagrams.pydsl.api import _validate_on_circle


def test_validate_on_circle_accepts_a_point_exactly_on_the_circle():
    with new_builder_context():
        c = circle(point(0.0, 0.0), 5.0)
        on_circle = point(5.0, 0.0)
        _validate_on_circle("arc", c, on_circle, "start")  # must not raise


def test_validate_on_circle_rejects_an_off_circle_point():
    with new_builder_context():
        c = circle(point(0.0, 0.0), 5.0)
        off_circle = point(3.0, 0.0)
        with pytest.raises(ValueError, match="not on the given circle"):
            _validate_on_circle("arc", c, off_circle, "start")
        # role name appears in the message so a script can tell start from end
        with pytest.raises(ValueError, match="start"):
            _validate_on_circle("arc", c, off_circle, "start")
        with pytest.raises(ValueError, match="end"):
            _validate_on_circle("arc", c, off_circle, "end")


def test_validate_on_circle_skips_when_point_coordinates_unknown():
    from geometry_diagrams.ir.ir import LineThrough
    from geometry_diagrams.pydsl.api import point_on
    from geometry_diagrams.pydsl.handles import Line

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 5.0)
        a, b = point(0.0, 0.0), point(4.0, 0.0)
        line_id = builder._fresh_hidden_id("line")
        builder._add(LineThrough(id=line_id, p=a.id, q=b.id))
        unknown = point_on(Line(id=line_id), 0.5)
        _validate_on_circle("arc", c, unknown, "start")  # must not raise — skipped


from geometry_diagrams.pydsl.api import arc, point_on, sector


def test_arc_records_arc_center_start_end_with_correct_fields():
    from geometry_diagrams.ir.ir import ArcCenterStartEnd

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 5.0)
        start = point_on(c, 0.0)
        end = point_on(c, math.pi / 2)
        result = arc(c, start, end, reflex=True)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, ArcCenterStartEnd) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].center == c.center.id
    assert defs[0].start == start.id
    assert defs[0].end == end.id
    assert defs[0].reflex is True


def test_arc_defaults_reflex_to_false():
    from geometry_diagrams.ir.ir import ArcCenterStartEnd

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 5.0)
        start = point_on(c, 0.0)
        end = point_on(c, math.pi / 2)
        result = arc(c, start, end)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, ArcCenterStartEnd) and d.id == result.id]
    assert defs[0].reflex is False


def test_arc_rejects_off_circle_start_with_literal_coordinates():
    with new_builder_context():
        c = circle(point(0.0, 0.0), 5.0)
        bad_start = point(3.0, 0.0)
        end = point(0.0, 5.0)
        with pytest.raises(ValueError, match="not on the given circle"):
            arc(c, bad_start, end)


def test_arc_rejects_off_circle_end_with_literal_coordinates():
    """Regression test for the render_util.py::arc_params endpoint-swap
    corruption found during spec review: an off-circle end must be
    rejected exactly like an off-circle start, not silently accepted."""
    with new_builder_context():
        c = circle(point(0.0, 0.0), 5.0)
        start = point(5.0, 0.0)
        bad_end = point(0.0, 3.0)
        with pytest.raises(ValueError, match="not on the given circle"):
            arc(c, start, bad_end)


def test_sector_records_sector_center_start_end_with_correct_fields():
    from geometry_diagrams.ir.ir import SectorCenterStartEnd

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 5.0)
        start = point_on(c, 0.0)
        end = point_on(c, math.pi / 2)
        result = sector(c, start, end)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, SectorCenterStartEnd) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].center == c.center.id
    assert defs[0].start == start.id
    assert defs[0].end == end.id
    assert defs[0].reflex is False


def test_sector_rejects_off_circle_start_and_end():
    with new_builder_context():
        c = circle(point(0.0, 0.0), 5.0)
        good = point(5.0, 0.0)
        bad = point(1.0, 0.0)
        with pytest.raises(ValueError, match="not on the given circle"):
            sector(c, bad, good)
        with pytest.raises(ValueError, match="not on the given circle"):
            sector(c, good, bad)


def test_arc_reflex_field_survives_compilation():
    """Compile-level check that reflex isn't dropped anywhere in the
    pydsl->IR->SymPy path — the actual sweep-angle math is already tested
    in to_sympy.py/to_tikz.py/to_svg.py's own test suites, out of scope
    here."""
    from geometry_diagrams.ir.to_sympy import Arc as SymArc
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 5.0)
        start = point_on(c, 0.0)
        end = point_on(c, math.pi / 2)
        result = arc(c, start, end, reflex=True)
        ir = builder.build()
    sym = compile_defs(ir)
    compiled_arc = sym[result.id]
    assert isinstance(compiled_arc, SymArc)
    assert compiled_arc.reflex is True


from geometry_diagrams.pydsl.api import regular_sectors


def test_regular_sectors_n4_hand_computed_boundary_points():
    from geometry_diagrams.ir.ir import SectorCenterStartEnd
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 1.0)
        result = regular_sectors(c, 4)
        ir = builder.build()
    assert len(result) == 4
    defs = [d for d in ir.define if isinstance(d, SectorCenterStartEnd)]
    assert len(defs) == 4
    for d in defs:
        assert d.reflex is False
    sym = compile_defs(ir)
    # boundary angles 0, pi/2, pi, 3pi/2 -> (1,0), (0,1), (-1,0), (0,-1)
    expected_starts = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    for i, d in enumerate(defs):
        sx, sy = float(sym[d.start].x), float(sym[d.start].y)
        ex, ey = expected_starts[i]
        assert sx == pytest.approx(ex, abs=1e-9)
        assert sy == pytest.approx(ey, abs=1e-9)
    # wraparound: last sector's end must equal the first sector's start
    assert defs[-1].end == defs[0].start


def test_regular_sectors_requires_n_at_least_2():
    with new_builder_context():
        c = circle(point(0.0, 0.0), 1.0)
        with pytest.raises(ValueError, match="n >= 2"):
            regular_sectors(c, 1)


def test_regular_sectors_n2_grid_aligned_center_does_not_duplicate_semicircle():
    """The n=2 case Fable's review flagged: math.sin(math.pi) is
    1.2246e-16, not exactly 0. If regular_sectors() rounded the absolute
    coordinate instead of the offset, this would produce boundary points
    at (1,0) and (-1, 1.2e-16) instead of exactly (-1,0), corrupting the
    rendered pie into two overlapping semicircles."""
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 1.0)
        result = regular_sectors(c, 2)
        ir = builder.build()
    assert len(result) == 2
    sym = compile_defs(ir)
    from geometry_diagrams.ir.ir import PointFixed, SectorCenterStartEnd
    defs = [d for d in ir.define if isinstance(d, SectorCenterStartEnd)]
    p0 = (float(sym[defs[0].start].x), float(sym[defs[0].start].y))
    p1 = (float(sym[defs[1].start].x), float(sym[defs[1].start].y))
    assert p0 == pytest.approx((1.0, 0.0), abs=1e-9)
    assert p1[0] == pytest.approx(-1.0, abs=1e-9)
    assert p1[1] == pytest.approx(0.0, abs=1e-9)  # exactly 0, not 1.2e-16
    # Magnitude-independent invariant: the two boundary points must be exact
    # reflections of each other through the center. Read from the raw
    # PointFixed IR defs, not compile_defs()'s sympy Point objects — sympy's
    # Point constructor calls nsimplify(..., rational=True) on any Float
    # coordinate, which for a "nice" center like this one snaps both the
    # correct and the banned "round the absolute coordinate" form to the
    # exact same rational, silently erasing the ~1e-11 discrepancy the
    # banned form introduces (verified directly: compiling either form's
    # output through compile_defs collapses both to identical rationals for
    # this center, so this invariant must be checked pre-compilation).
    pfs = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    p0_raw, p1_raw = pfs[defs[0].start], pfs[defs[1].start]
    cx, cy = c.center.x, c.center.y
    assert abs((p0_raw.x + p1_raw.x) - 2 * cx) < 1e-13
    assert abs((p0_raw.y + p1_raw.y) - 2 * cy) < 1e-13


def test_regular_sectors_n2_non_grid_aligned_center_does_not_duplicate_semicircle():
    """Regression test for the SECOND bug a Fable review round caught: the
    first fix rounded the absolute coordinate (round(center + offset, 10)),
    which still fails ~100% of the time for any center not already sitting
    on a 1e-10 grid, since pydsl (unlike recipe/lower.py) stores raw
    unrounded centers. The correct fix rounds the offset BEFORE adding it
    to the center: circle.center.x + round(radius * cos(angle), 10)."""
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.ir import PointFixed, SectorCenterStartEnd

    with new_builder_context() as builder:
        c = circle(point(1.0 / 3.0, 1.0 / 3.0), 1.0)
        result = regular_sectors(c, 2)
        ir = builder.build()
    assert len(result) == 2
    sym = compile_defs(ir)
    defs = [d for d in ir.define if isinstance(d, SectorCenterStartEnd)]
    p0y = float(sym[defs[0].start].y)
    p1y = float(sym[defs[1].start].y)
    cx, cy = c.center.x, c.center.y
    # Both boundary points must land at exactly cy (angle 0 and pi both have
    # sin(angle) == 0 mathematically) — not off by ~1e-10 in opposite
    # directions, which is what causes the tie-break misclassification.
    assert p0y == pytest.approx(cy, abs=1e-9)
    assert p1y == pytest.approx(cy, abs=1e-9)
    assert p0y == pytest.approx(p1y, abs=1e-12)
    # Magnitude-independent invariant: the two boundary points must be exact
    # reflections of each other through the center. Read from the raw
    # PointFixed IR defs, not compile_defs()'s sympy Point objects — sympy's
    # Point constructor calls nsimplify(..., rational=True) on any Float
    # coordinate, and for this center (1/3) both the correct and the banned
    # "round the absolute coordinate" form land within its snap tolerance of
    # the same exact rationals (4/3, -2/3, 1/3), which erases the ~1e-11
    # discrepancy the banned form introduces if checked post-compilation.
    # Verified directly: this is the actual regression test for that bug —
    # it fails when api.py is mutated to the banned form and passes on the
    # correct form.
    pfs = {d.id: d for d in ir.define if isinstance(d, PointFixed)}
    p0_raw, p1_raw = pfs[defs[0].start], pfs[defs[1].start]
    assert abs((p0_raw.x + p1_raw.x) - 2 * cx) < 1e-13
    assert abs((p0_raw.y + p1_raw.y) - 2 * cy) < 1e-13


def test_regular_sectors_rejects_circumcircle_derived_circle():
    from geometry_diagrams.pydsl.api import circumcircle, triangle

    with new_builder_context():
        a, b, c_pt = point(0.0, 0.0), point(4.0, 0.0), point(2.0, 3.0)
        t = triangle(a, b, c_pt)
        circ = circumcircle(t)
        with pytest.raises(ValueError, match="no known coordinates"):
            regular_sectors(circ, 4)


def test_arcs_sectors_work_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script
    from geometry_diagrams.ir.ir import ArcCenterStartEnd, CircleCenterRadius, SectorCenterStartEnd

    script = (
        "c = circle(point(0.0, 0.0), 5.0)\n"
        "a = point_on(c, 0.0)\n"
        "b = point_on(c, 1.5707963267948966)\n"
        "the_arc = arc(c, a, b)\n"
        "the_sector = sector(c, a, b)\n"
        "draw(the_arc)\n"
        "draw(the_sector)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    kinds = {type(d) for d in result.diagram_ir.define}
    assert CircleCenterRadius in kinds
    assert ArcCenterStartEnd in kinds
    assert SectorCenterStartEnd in kinds
