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
