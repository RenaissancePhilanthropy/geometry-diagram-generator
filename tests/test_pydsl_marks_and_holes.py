# tests/test_pydsl_marks_and_holes.py
"""Tests for pydsl's congruence/right-angle mark functions and fill()'s
holes= parameter. MarkSegments/MarkRightAngles/Fill.holes are all
existing IR classes, already fully supported by both to_tikz.py and
to_svg.py, that were never exposed to pydsl until this plan. See
docs/superpowers/specs/2026-08-05-pydsl-marks-and-fill-holes-design.md
for the full design rationale, including a real wrinkle: mark_proportional()
renders visually IDENTICAL to mark_equal() (no separate symbol set exists
for "proportional" in either renderer) — kept anyway per explicit user
choice for a script's own semantic clarity, not visual distinction."""
import pytest

from geometry_diagrams.pydsl.builder import Builder, new_builder_context


def test_fresh_mark_group_returns_prefixed_unique_strings():
    builder = Builder()
    g1 = builder._fresh_mark_group("equal")
    g2 = builder._fresh_mark_group("equal")
    g3 = builder._fresh_mark_group("parallel")
    assert g1 != g2
    assert g1.startswith("equal")
    assert g2.startswith("equal")
    assert g3.startswith("parallel")


def test_fresh_mark_group_parallel_prefix_is_literal():
    """Critical correctness property: both renderers route purely on
    group.startswith("parallel") to pick the chevron symbol cycle instead
    of the tick-mark cycle. A kind="parallel" group string that doesn't
    literally start with "parallel" would silently render as tick marks
    instead of chevrons."""
    builder = Builder()
    g = builder._fresh_mark_group("parallel")
    assert g.startswith("parallel")


def test_fresh_mark_group_non_parallel_kinds_do_not_start_with_parallel():
    builder = Builder()
    assert not builder._fresh_mark_group("equal").startswith("parallel")
    assert not builder._fresh_mark_group("proportional").startswith("parallel")


from geometry_diagrams.pydsl.api import (
    arc, circle, draw, fill, mark_equal, mark_parallel, mark_proportional,
    point, polygon, ray, sector, segment,
)


def _recorded_mark_segments(ir):
    from geometry_diagrams.ir.ir import MarkSegments

    return [r for r in ir.render if isinstance(r, MarkSegments)]


def test_mark_equal_records_correct_segs_and_group_prefix():
    with new_builder_context() as builder:
        a, b, c, d = point(0, 0), point(4, 0), point(0, 4), point(4, 4)
        ab, cd = segment(a, b), segment(c, d)
        mark_equal(ab, cd)
        ir = builder.build()
    marks = _recorded_mark_segments(ir)
    assert len(marks) == 1
    assert marks[0].segs == [ab.id, cd.id]
    assert marks[0].group.startswith("equal")
    assert not marks[0].group.startswith("parallel")


def test_mark_parallel_records_group_starting_with_parallel():
    with new_builder_context() as builder:
        a, b, c, d = point(0, 0), point(4, 0), point(0, 4), point(4, 4)
        ab, cd = segment(a, b), segment(c, d)
        mark_parallel(ab, cd)
        ir = builder.build()
    marks = _recorded_mark_segments(ir)
    assert len(marks) == 1
    assert marks[0].segs == [ab.id, cd.id]
    assert marks[0].group.startswith("parallel")


def test_mark_proportional_records_group_prefix_but_not_parallel():
    with new_builder_context() as builder:
        a, b, c, d = point(0, 0), point(4, 0), point(0, 4), point(4, 4)
        ab, cd = segment(a, b), segment(c, d)
        mark_proportional(ab, cd)
        ir = builder.build()
    marks = _recorded_mark_segments(ir)
    assert len(marks) == 1
    assert marks[0].group.startswith("proportional")
    assert not marks[0].group.startswith("parallel")


def test_mark_equal_rejects_fewer_than_2_segments():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        ab = segment(a, b)
        with pytest.raises(ValueError, match="at least 2"):
            mark_equal(ab)
        with pytest.raises(ValueError, match="at least 2"):
            mark_equal()


def test_mark_parallel_rejects_fewer_than_2_segments():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        ab = segment(a, b)
        with pytest.raises(ValueError, match="at least 2"):
            mark_parallel(ab)


def test_mark_proportional_rejects_fewer_than_2_segments():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        ab = segment(a, b)
        with pytest.raises(ValueError, match="at least 2"):
            mark_proportional(ab)


def test_two_separate_mark_equal_calls_get_distinct_groups():
    with new_builder_context() as builder:
        a, b, c, d = point(0, 0), point(4, 0), point(0, 4), point(4, 4)
        e, f = point(1, 1), point(5, 5)
        ab, cd = segment(a, b), segment(c, d)
        ef, cf = segment(e, f), segment(c, f)
        mark_equal(ab, cd)
        mark_equal(ef, cf)
        ir = builder.build()
    marks = _recorded_mark_segments(ir)
    assert len(marks) == 2
    assert marks[0].group != marks[1].group


def test_mark_equal_and_mark_parallel_render_correct_symbols_in_sequence():
    """Render-level test proving the WHOLE pipeline (not just the recorded
    IR) produces the documented symbols: first equal-group -> "|" (1 tick
    per segment), second equal-group -> "||" (2 ticks per segment), the
    parallel-group -> chevrons (2 <line> elements per chevron, since
    to_svg.py's _append_seg_chevrons draws each chevron as two arm lines).
    Every mark element carries a "data-group" attribute equal to the exact
    group string mark_equal()/mark_parallel() generated (confirmed by
    reading to_svg.py's MarkSegments case directly), so marks can be
    counted per group precisely rather than just checking something
    rendered."""
    import xml.etree.ElementTree as ET

    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.to_svg import ir_to_svg
    from geometry_diagrams.ir.ir import MarkSegments

    with new_builder_context() as builder:
        a, b, c, d, e, f, g, h = (
            point(0, 0), point(4, 0), point(0, 4), point(4, 4),
            point(1, 1), point(5, 1), point(1, 5), point(5, 5),
        )
        ab, cd = segment(a, b), segment(c, d)
        ef, gh = segment(e, f), segment(g, h)
        ij, kl = segment(point(2, 2), point(6, 2)), segment(point(2, 6), point(6, 6))
        mark_equal(ab, cd)      # group 1 -> "|" (1 tick/segment)
        mark_equal(ef, gh)      # group 2 -> "||" (2 ticks/segment)
        mark_parallel(ij, kl)   # group 3 -> 1 chevron/segment (2 lines/chevron)
        ir = builder.build()
    mark_ops = [r for r in ir.render if isinstance(r, MarkSegments)]
    assert len(mark_ops) == 3
    group1, group2, group3 = (op.group for op in mark_ops)

    sym = compile_defs(ir)
    svg = ir_to_svg(ir, sym)
    root = ET.fromstring(svg)
    lines = root.findall(".//{http://www.w3.org/2000/svg}line")

    def _lines_for_group(group: str) -> int:
        return len([ln for ln in lines if ln.get("data-group") == group])

    assert _lines_for_group(group1) == 2   # 1 tick x 2 segments
    assert _lines_for_group(group2) == 4   # 2 ticks x 2 segments
    assert _lines_for_group(group3) == 4   # 1 chevron (2 arm-lines) x 2 segments


from geometry_diagrams.pydsl.api import mark_right_angle, triangle


def test_mark_right_angle_records_single_element_angles_list():
    from geometry_diagrams.ir.ir import MarkRightAngles

    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(0, 3)
        t = triangle(a, b, c)
        ref = t.angle_at(a)
        mark_right_angle(ref)
        ir = builder.build()
    marks = [r for r in ir.render if isinstance(r, MarkRightAngles)]
    assert len(marks) == 1
    assert len(marks[0].angles) == 1
    angle_spec = marks[0].angles[0]
    assert angle_spec.a == ref.a.id
    assert angle_spec.o == ref.o.id
    assert angle_spec.b == ref.b.id


def _fill_holes(ir, obj_id):
    from geometry_diagrams.ir.ir import Fill

    defs = [r for r in ir.render if isinstance(r, Fill) and r.obj == obj_id]
    assert len(defs) == 1
    return defs[0].holes


def test_fill_with_no_holes_still_records_empty_list():
    """Non-regression check: fill()'s pre-existing zero-holes behavior
    must be unchanged after this task."""
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(4, 0), point(2, 3)
        tri = triangle(a, b, c)
        fill(tri, color="red")
        ir = builder.build()
    assert _fill_holes(ir, tri.id) == []


def test_fill_with_one_hole_records_correct_id_list():
    with new_builder_context() as builder:
        p1, p2, p3, p4 = point(0, 0), point(6, 0), point(6, 6), point(0, 6)
        outer = polygon(p1, p2, p3, p4)
        hole_circle = circle(point(3, 3), 1.0)
        fill(outer, holes=[hole_circle])
        ir = builder.build()
    assert _fill_holes(ir, outer.id) == [hole_circle.id]


def test_fill_with_multiple_holes_preserves_order():
    with new_builder_context() as builder:
        p1, p2, p3, p4 = point(0, 0), point(10, 0), point(10, 10), point(0, 10)
        outer = polygon(p1, p2, p3, p4)
        c1 = circle(point(2, 2), 1.0)
        c2 = circle(point(8, 8), 1.0)
        fill(outer, holes=[c1, c2])
        ir = builder.build()
    assert _fill_holes(ir, outer.id) == [c1.id, c2.id]


def test_fill_hole_rejects_point():
    with new_builder_context():
        p1, p2, p3 = point(0, 0), point(4, 0), point(2, 3)
        tri = triangle(p1, p2, p3)
        with pytest.raises(ValueError, match="Point"):
            fill(tri, holes=[point(1, 1)])


def test_fill_hole_rejects_angle_ref():
    with new_builder_context() as builder:
        p1, p2, p3 = point(0, 0), point(4, 0), point(2, 3)
        tri = triangle(p1, p2, p3)
        ref = tri.angle_at(p1)
        with pytest.raises(ValueError, match="AngleRef"):
            fill(tri, holes=[ref])


def test_fill_holes_accepts_a_one_shot_generator():
    """Regression test for the generator-double-iteration bug found
    during spec review: if `holes` were iterated twice without first
    being materialized (once for validation, once for the id-list
    construction), a genuine generator expression would be silently
    exhausted after the first pass, producing an incorrect empty
    holes=[] instead of the real list."""
    with new_builder_context() as builder:
        p1, p2, p3, p4 = point(0, 0), point(6, 0), point(6, 6), point(0, 6)
        outer = polygon(p1, p2, p3, p4)
        hole_circle = circle(point(3, 3), 1.0)
        fill(outer, holes=(h for h in [hole_circle]))
        ir = builder.build()
    assert _fill_holes(ir, outer.id) == [hole_circle.id]


def test_fill_sector_as_outer_shape_and_hole_renders_correctly_under_svg():
    """Coverage test (not a regression test for a fix — no fix was
    needed; see the design spec's 'Correction' section). Locks in
    already-correct behavior: fill() with a sector as either the outer
    shape or a hole must render with the even-odd rule under SVG, with
    no 'unsupported shape type' warning, so this doesn't silently break
    if to_svg.py's _obj_to_svg_subpath is ever touched for something
    else later."""
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.to_svg import ir_to_svg

    with new_builder_context() as builder:
        c = circle(point(0.0, 0.0), 3.0)
        start = point(3.0, 0.0)
        end = point(0.0, 3.0)
        sec = sector(c, start, end)
        p1, p2, p3, p4 = point(0.0, 0.0), point(6.0, 0.0), point(6.0, 6.0), point(0.0, 6.0)
        outer = polygon(p1, p2, p3, p4)
        fill(outer, holes=[sec])
        draw(outer)
        ir = builder.build()
    sym = compile_defs(ir)
    svg = ir_to_svg(ir, sym)
    assert 'fill-rule="evenodd"' in svg


# ---------------------------------------------------------------------------
# Ticket 06: mark_equal/mark_parallel/mark_proportional dispatch by handle
# type instead of blindly forwarding whatever ids they're given. A Segment/
# Ray mix produces the existing MarkSegments op; an Arc/Sector mix produces
# the existing MarkArcs op (built in a prior increment); a call mixing a
# straight-line item with a curved one shares one freshly-generated group
# name across both ops (MarkArcs was specifically designed to share
# MarkSegments' group namespace — see ir.MarkArcs's docstring). mark_parallel()
# additionally rejects arcs/sectors outright (chevron marks have no arc-form),
# and anything that isn't a Segment/Ray/Arc/Sector is rejected by all three
# with a clear error naming the offending type.
# ---------------------------------------------------------------------------

def _recorded_mark_arcs(ir):
    from geometry_diagrams.ir.ir import MarkArcs

    return [r for r in ir.render if isinstance(r, MarkArcs)]


def _arc_pair(cx: float = 10.0) -> tuple:
    """Two same-radius arcs on unrelated circles, for the arc/arc and mixed
    segment/arc dispatch tests below."""
    c1 = circle(point(0.0, 0.0), 3.0)
    a1 = arc(c1, point(3.0, 0.0), point(0.0, 3.0))
    c2 = circle(point(cx, 0.0), 3.0)
    a2 = arc(c2, point(cx + 3.0, 0.0), point(cx, 3.0))
    return a1, a2


def test_mark_equal_accepts_a_ray_and_a_segment_as_one_mark_segments_op():
    with new_builder_context() as builder:
        a, b, c, d = point(0, 0), point(4, 0), point(0, 4), point(4, 4)
        seg = segment(a, b)
        r = ray(c, d)
        mark_equal(seg, r)
        ir = builder.build()
    seg_marks = _recorded_mark_segments(ir)
    assert len(seg_marks) == 1
    assert seg_marks[0].segs == [seg.id, r.id]
    assert _recorded_mark_arcs(ir) == []


def test_mark_equal_on_two_arcs_produces_a_mark_arcs_op():
    with new_builder_context() as builder:
        a1, a2 = _arc_pair()
        mark_equal(a1, a2)
        ir = builder.build()
    arc_marks = _recorded_mark_arcs(ir)
    assert len(arc_marks) == 1
    assert arc_marks[0].arcs == [a1.id, a2.id]
    assert _recorded_mark_segments(ir) == []


def test_mark_equal_on_two_sectors_produces_a_mark_arcs_op():
    with new_builder_context() as builder:
        c1 = circle(point(0.0, 0.0), 3.0)
        s1 = sector(c1, point(3.0, 0.0), point(0.0, 3.0))
        c2 = circle(point(10.0, 0.0), 3.0)
        s2 = sector(c2, point(13.0, 0.0), point(10.0, 3.0))
        mark_equal(s1, s2)
        ir = builder.build()
    arc_marks = _recorded_mark_arcs(ir)
    assert len(arc_marks) == 1
    assert arc_marks[0].arcs == [s1.id, s2.id]


def test_mark_equal_mixed_segment_and_arc_share_one_group():
    """The crux of this ticket: a single mark_equal() call mixing a
    straight-line item with a curved one must produce two render ops (one
    MarkSegments, one MarkArcs) that share the SAME group string, so they
    read as one congruence class, not two unrelated ones."""
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        arc1, _ = _arc_pair()
        mark_equal(seg, arc1)
        ir = builder.build()
    seg_marks = _recorded_mark_segments(ir)
    arc_marks = _recorded_mark_arcs(ir)
    assert len(seg_marks) == 1
    assert len(arc_marks) == 1
    assert seg_marks[0].group == arc_marks[0].group


def test_mark_proportional_mixed_ray_and_sector_share_one_group():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        r = ray(a, b)
        c = circle(point(10.0, 0.0), 3.0)
        sec = sector(c, point(13.0, 0.0), point(10.0, 3.0))
        mark_proportional(r, sec)
        ir = builder.build()
    seg_marks = _recorded_mark_segments(ir)
    arc_marks = _recorded_mark_arcs(ir)
    assert len(seg_marks) == 1
    assert seg_marks[0].segs == [r.id]
    assert len(arc_marks) == 1
    assert arc_marks[0].arcs == [sec.id]
    assert seg_marks[0].group == arc_marks[0].group


def test_mark_equal_only_generates_one_fresh_group_per_call():
    """A mixed call must call _fresh_mark_group() exactly once, not once per
    render op it ends up producing -- otherwise two mixed calls in the same
    diagram couldn't be told apart, and neither would actually share a
    group with its own arc side."""
    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        arc1, arc2 = _arc_pair()
        mark_equal(seg, arc1)                                    # call 1
        mark_equal(arc2, segment(point(20, 0), point(24, 0)))     # call 2
        ir = builder.build()
    seg_marks = _recorded_mark_segments(ir)
    arc_marks = _recorded_mark_arcs(ir)
    assert len(seg_marks) == 2 and len(arc_marks) == 2
    # Each call's own straight/curved op pair shares a group...
    assert seg_marks[0].group == arc_marks[0].group
    assert seg_marks[1].group == arc_marks[1].group
    # ...but the two calls get distinct groups from each other.
    assert seg_marks[0].group != seg_marks[1].group


def test_mark_parallel_rejects_an_arc_naming_its_type():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        arc1, _ = _arc_pair()
        with pytest.raises(ValueError, match="Arc"):
            mark_parallel(seg, arc1)


def test_mark_parallel_rejects_a_sector_naming_its_type():
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        c = circle(point(10.0, 0.0), 3.0)
        sec = sector(c, point(13.0, 0.0), point(10.0, 3.0))
        with pytest.raises(ValueError, match="Sector"):
            mark_parallel(seg, sec)


@pytest.mark.parametrize("mark_fn", [mark_equal, mark_parallel, mark_proportional])
def test_mark_functions_reject_an_unsupported_type_naming_it(mark_fn):
    with new_builder_context():
        a, b = point(0, 0), point(4, 0)
        seg = segment(a, b)
        stray_point = point(1, 1)
        with pytest.raises(ValueError, match="Point"):
            mark_fn(seg, stray_point)


def test_mark_equal_still_rejects_fewer_than_2_items_when_mixed_types_given():
    """Non-regression: the existing 'at least 2' arity check must still
    fire for a single item, regardless of its type."""
    with new_builder_context():
        arc1, _ = _arc_pair()
        with pytest.raises(ValueError, match="at least 2"):
            mark_equal(arc1)


# ---------------------------------------------------------------------------
# End-to-end (builder script -> compiled diagram -> rendered output) for the
# exact 5 scenarios ticket 06's acceptance criteria call out by name.
# ---------------------------------------------------------------------------

def _run_and_render(script: str):
    """Run script through the real sandbox, then compile+render its IR
    through both backends -- proving the WHOLE pipeline (not just IR
    construction) handles the scenario without crashing."""
    from geometry_diagrams.pydsl.sandbox import run_script
    from geometry_diagrams.ir.to_sympy import compile_defs
    from geometry_diagrams.ir.to_svg import ir_to_svg
    from geometry_diagrams.ir.to_tikz import ir_to_tikz

    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    sym = compile_defs(result.diagram_ir)
    svg = ir_to_svg(result.diagram_ir, sym)
    tikz = ir_to_tikz(result.diagram_ir, sym)
    return result, svg, tikz


def test_e2e_ray_marked_equal_to_segment():
    from geometry_diagrams.ir.ir import MarkSegments

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "c = point(0, 3)\n"
        "d = point(4, 3)\n"
        "seg = segment(a, b)\n"
        "r = ray(c, d)\n"
        "mark_equal(seg, r)\n"
        "draw(seg)\n"
        "draw(r)\n"
    )
    result, svg, tikz = _run_and_render(script)
    marks = [op for op in result.diagram_ir.render if isinstance(op, MarkSegments)]
    assert len(marks) == 1
    assert len(marks[0].segs) == 2


def test_e2e_two_arcs_marked_equal():
    from geometry_diagrams.ir.ir import MarkArcs

    script = (
        "c1 = circle(point(0.0, 0.0), 3.0)\n"
        "a1 = arc(c1, point(3.0, 0.0), point(0.0, 3.0))\n"
        "c2 = circle(point(10.0, 0.0), 3.0)\n"
        "a2 = arc(c2, point(13.0, 0.0), point(10.0, 3.0))\n"
        "mark_equal(a1, a2)\n"
        "draw(a1)\n"
        "draw(a2)\n"
    )
    result, svg, tikz = _run_and_render(script)
    marks = [op for op in result.diagram_ir.render if isinstance(op, MarkArcs)]
    assert len(marks) == 1
    assert len(marks[0].arcs) == 2


def test_e2e_mixed_segment_and_arc_group_shares_one_mark():
    from geometry_diagrams.ir.ir import MarkArcs, MarkSegments

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "seg = segment(a, b)\n"
        "c1 = circle(point(10.0, 0.0), 3.0)\n"
        "arc1 = arc(c1, point(13.0, 0.0), point(10.0, 3.0))\n"
        "mark_equal(seg, arc1)\n"
        "draw(seg)\n"
        "draw(arc1)\n"
    )
    result, svg, tikz = _run_and_render(script)
    seg_marks = [op for op in result.diagram_ir.render if isinstance(op, MarkSegments)]
    arc_marks = [op for op in result.diagram_ir.render if isinstance(op, MarkArcs)]
    assert len(seg_marks) == 1
    assert len(arc_marks) == 1
    assert seg_marks[0].group == arc_marks[0].group


def test_e2e_mark_parallel_rejects_an_arc():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "seg = segment(a, b)\n"
        "c1 = circle(point(10.0, 0.0), 3.0)\n"
        "arc1 = arc(c1, point(13.0, 0.0), point(10.0, 3.0))\n"
        "mark_parallel(seg, arc1)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is not None
    assert "Arc" in result.error


def test_e2e_unsupported_type_rejected_by_all_three():
    from geometry_diagrams.pydsl.sandbox import run_script

    for fn_name in ("mark_equal", "mark_parallel", "mark_proportional"):
        script = (
            "a = point(0, 0)\n"
            "b = point(4, 0)\n"
            "seg = segment(a, b)\n"
            "stray = point(1, 1)\n"
            f"{fn_name}(seg, stray)\n"
        )
        result = run_script(script, timeout_seconds=10.0)
        assert result.error is not None, f"{fn_name} should have rejected a Point"
        assert "Point" in result.error, f"{fn_name}: {result.error!r}"


def test_marks_and_holes_work_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script
    from geometry_diagrams.ir.ir import Fill, MarkRightAngles, MarkSegments

    script = (
        "a = point(0, 0)\n"
        "b = point(4, 0)\n"
        "c = point(0, 3)\n"
        "d = point(4, 3)\n"
        "t = triangle(a, b, c)\n"
        "ab = segment(a, b)\n"
        "cd = segment(c, d)\n"
        "mark_equal(ab, cd)\n"
        "mark_right_angle(t.angle_at(a))\n"
        "outer = polygon(point(0,0), point(6,0), point(6,6), point(0,6))\n"
        "hole = circle(point(3, 3), 1.0)\n"
        "fill(outer, color='blue', holes=[hole])\n"
        "draw(t)\n"
        "draw(outer)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    mark_seg_defs = [r for r in result.diagram_ir.render if isinstance(r, MarkSegments)]
    right_angle_defs = [r for r in result.diagram_ir.render if isinstance(r, MarkRightAngles)]
    fill_defs = [r for r in result.diagram_ir.render if isinstance(r, Fill)]
    assert len(mark_seg_defs) == 1
    assert len(right_angle_defs) == 1
    assert len(fill_defs) == 1
    assert fill_defs[0].holes != []
