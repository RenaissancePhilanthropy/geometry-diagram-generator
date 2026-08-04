# tests/test_pydsl_labels.py
"""Tests for pydsl label support: Point.label(), segment()/Segment.label(),
AngleRef.label(), and label_text() — all wrapping IR RenderOp kinds
(LabelPoint/LabelSegment/LabelAngle/LabelFreeText) that already exist and
are already rendered by to_tikz.py/to_svg.py."""
import pytest

from geometry_diagrams.pydsl.api import point
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import LabelPoint


def test_point_label_records_label_point():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert len(matches) == 1
    assert matches[0].text == "A"
    assert matches[0].pos == "auto"
    assert matches[0].show_coords is False


def test_point_label_with_pos_and_show_coords():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("A", pos="above left", show_coords=True)
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert matches[0].pos == "above left"
    assert matches[0].show_coords is True


from geometry_diagrams.pydsl.api import segment, triangle
from geometry_diagrams.ir.ir import LabelSegment


def test_segment_between_two_points_is_a_segment_def():
    from geometry_diagrams.ir.ir import Segment as SegmentDef

    with new_builder_context() as builder:
        a = point(0, 0)
        b = point(4, 0)
        s = segment(a, b)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, SegmentDef) and d.id == s.id]
    assert len(defs) == 1
    assert {defs[0].a, defs[0].b} == {a.id, b.id}


def test_segment_dedups_with_itself_regardless_of_argument_order():
    with new_builder_context():
        a = point(0, 0)
        b = point(4, 0)
        s1 = segment(a, b)
        s2 = segment(b, a)
    assert s1.id == s2.id


def test_segment_rejects_the_same_point_twice():
    with new_builder_context():
        a = point(0, 0)
        with pytest.raises(ValueError, match="two distinct points"):
            segment(a, a)


def test_segment_label_from_standalone_segment():
    with new_builder_context() as builder:
        a = point(0, 0)
        b = point(4, 0)
        s = segment(a, b)
        s.label("r")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == s.id]
    assert len(matches) == 1
    assert matches[0].text == "r"
    assert matches[0].pos is None


def test_segment_label_from_triangle_side():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        s = t.side(a, b)
        s.label("AB")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == s.id]
    assert len(matches) == 1
    assert matches[0].text == "AB"


from geometry_diagrams.ir.ir import LabelAngle


def test_angle_ref_label_records_label_angle():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        ref.label("θ")
        ir = builder.build()
    matches = [
        r for r in ir.render
        if isinstance(r, LabelAngle) and r.angle.o == b.id
    ]
    assert len(matches) == 1
    assert matches[0].text == "θ"
    assert {matches[0].angle.a, matches[0].angle.b} == {a.id, c.id}
    assert matches[0].pos is None


from geometry_diagrams.pydsl.api import label_text
from geometry_diagrams.ir.ir import LabelFreeText


def test_label_text_at_explicit_coordinates():
    with new_builder_context() as builder:
        label_text("h", at=(1.0, 2.0))
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "h"
    assert matches[0].at == [1.0, 2.0]
    assert matches[0].centroid_of is None


def test_label_text_at_triangle_centroid():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        label_text("T", centroid_of=t)
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "T"
    assert matches[0].at is None
    assert matches[0].centroid_of == t.id


def test_label_text_requires_exactly_one_of_at_or_centroid_of():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        with pytest.raises(ValueError, match="exactly one"):
            label_text("h", at=(0, 0), centroid_of=t)


def test_label_text_neither_at_nor_centroid_of_raises_without_a_builder():
    # No new_builder_context() at all — proves the exactly-one-of check
    # runs before get_builder(), so this is ValueError, not RuntimeError.
    with pytest.raises(ValueError, match="exactly one"):
        label_text("h")
