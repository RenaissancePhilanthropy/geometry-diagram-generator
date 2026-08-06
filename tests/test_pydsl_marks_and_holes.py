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
    mark_equal, mark_parallel, mark_proportional, point, segment,
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
