# tests/test_pydsl_labels.py
"""Tests for pydsl label support: Point.label(), segment()/Segment.label(),
AngleRef.label(), and label_text() — all wrapping IR RenderOp kinds
(LabelPoint/LabelSegment/LabelAngle/LabelFreeText) that already exist and
are already rendered by to_tikz.py/to_svg.py."""
import pytest

from geometry_diagrams.pydsl.api import arc, circle, label_text, line_through, point, point_on, segment, triangle
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.ir.ir import (
    LabelAngle,
    LabelFreeText,
    LabelPoint,
    LabelSegment,
    Segment as SegmentDef,
)


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


def test_segment_between_two_points_is_a_segment_def():
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


def test_line_label_records_label_segment():
    """Line.label() wraps the same LabelSegment op as Segment.label() —
    line_label_endpoints() in render_util.py resolves a Line-family def to
    a real point pair at render time, so no new IR op is needed."""
    with new_builder_context() as builder:
        a = point(0, 0)
        b = point(4, 0)
        ell = line_through(a, b)
        ell.label("ell")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == ell.id]
    assert len(matches) == 1
    assert matches[0].text == "ell"
    assert matches[0].pos is None


def test_arc_label_records_label_segment():
    with new_builder_context() as builder:
        c = circle(point(0, 0), 5)
        start = point_on(c, 0.0)
        end = point_on(c, 0.25)
        a = arc(c, start, end)
        a.label("alpha")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == a.id]
    assert len(matches) == 1
    assert matches[0].text == "alpha"


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


def test_point_label_autofixes_python_escaped_latex_command():
    # A script author writing "\angle ABD" in a normal (non-raw) string
    # literal has Python's own parser consume the backslash as an escape
    # before this code ever runs — "\a" becomes BEL (0x07) — so the text
    # this function actually receives is "\x07ngle ABD".
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("\angle ABD")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert matches[0].text == "∠ ABD"


def test_point_label_rejects_unrecognizable_control_character():
    with new_builder_context():
        p = point(1, 2)
        with pytest.raises(ValueError, match="non-printable control character"):
            p.label("\bogus")


def test_point_label_leaves_clean_text_unchanged():
    with new_builder_context() as builder:
        p = point(1, 2)
        p.label("∠ ABD")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelPoint) and r.p == p.id]
    assert matches[0].text == "∠ ABD"


def test_segment_label_autofixes_python_escaped_latex_command():
    # \b is a real Python escape (backspace, 0x08) — same corruption
    # mechanism as \a, applied to a macro starting with "b".
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        s = segment(a, b)
        s.label("\beta")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelSegment) and r.seg == s.id]
    assert matches[0].text == "β"


def test_angle_ref_label_autofixes_python_escaped_latex_command():
    # \v is a real Python escape (vertical tab, 0x0B) — same corruption
    # mechanism as \a, applied to a macro starting with "v".
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(1, 3)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        ref.label("\varepsilon")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelAngle) and r.angle.o == b.id]
    assert matches[0].text == "ε"


def test_label_text_autofixes_python_escaped_latex_command():
    with new_builder_context() as builder:
        label_text("\angle", at=(1.0, 2.0))
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, LabelFreeText)]
    assert matches[0].text == "∠"


def test_labels_and_segment_work_through_the_real_sandbox():
    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "a.label('A')\n"
        "s = segment(a, b)\n"
        "s.label('r')\n"
        "draw(s)\n"
        "draw_points(a, b)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    point_labels = [r for r in result.diagram_ir.render if isinstance(r, LabelPoint)]
    seg_labels = [r for r in result.diagram_ir.render if isinstance(r, LabelSegment)]
    assert any(r.text == "A" for r in point_labels)
    assert any(r.text == "r" for r in seg_labels)
