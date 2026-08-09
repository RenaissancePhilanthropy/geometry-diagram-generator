# tests/test_angle_pairs.py
"""Tests for the mark_angle_pair post-compile resolver.

Coordinates mirror geometry_diagrams/recipe/recipes/default/parallel_transversal_angles.yaml:
  A=(0,0), B=(4,0)   -- line L1 (y=0)
  C=(0,2), D=(4,2)   -- line L2 (y=2), parallel to L1
  Transversal from E=(2,-1) to F=(3,3), crossing L1 at G and L2 at H.
Intersection algebra (line Trans: (2+t, -1+4t)):
  L1 (y=0): -1+4t=0 -> t=0.25 -> G=(2.25, 0)
  L2 (y=2): -1+4t=2 -> t=0.75 -> H=(2.75, 2)
The recipe's own notes document the correct hand-picked answers this resolver
must reproduce:
  group 1 (corresponding):        B-G-H  and  D-H-F
  group 2 (alternate_interior):   H-G-A  and  G-H-D
  group 3 (alternate_exterior):   B-G-E  and  C-H-F
"""
from __future__ import annotations

import pytest
import sympy as sp
import sympy.geometry as spg

from geometry_diagrams.ir.ir import (
    AnglePoints, DiagramIR, MarkAngles, PendingAnglePair, PointFixed, Polygon,
    LineThrough, SectorCenterStartEnd,
)
from geometry_diagrams.ir.angle_pairs import resolve_angle_pairs
from geometry_diagrams.ir.checks import check_render_angles
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.to_sympy import compile_defs


def _sym():
    return {
        "A": spg.Point(sp.Float(0), sp.Float(0)),
        "B": spg.Point(sp.Float(4), sp.Float(0)),
        "C": spg.Point(sp.Float(0), sp.Float(2)),
        "D": spg.Point(sp.Float(4), sp.Float(2)),
        "G": spg.Point(sp.Float(2.25), sp.Float(0)),
        "H": spg.Point(sp.Float(2.75), sp.Float(2)),
    }


def _angle_deg(sym, a, o, b):
    ax, ay = float(sym[a].x), float(sym[a].y)
    ox, oy = float(sym[o].x), float(sym[o].y)
    bx, by = float(sym[b].x), float(sym[b].y)
    v1x, v1y = ax - ox, ay - oy
    v2x, v2y = bx - ox, by - oy
    dot = v1x * v2x + v1y * v2y
    cross = abs(v1x * v2y - v1y * v2x)
    import math
    return math.degrees(math.atan2(cross, dot))


def _make_ir(pending: PendingAnglePair) -> DiagramIR:
    return DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=2), PointFixed(id="D", x=4, y=2),
            PointFixed(id="G", x=2.25, y=0), PointFixed(id="H", x=2.75, y=2),
        ],
        pending_angle_pairs=[pending],
    )


def test_corresponding_matches_recipe_answer():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="corresponding",
        ray_ref_v1="B", ray_ref_v2="D", group="1",
    ))
    result = resolve_angle_pairs(diagram_ir, sym)
    assert result.pending_angle_pairs == []
    marks = [r for r in result.render if isinstance(r, MarkAngles)]
    assert len(marks) == 2

    expected_deg = _angle_deg(sym, "B", "G", "H")
    for m in marks:
        a, o, b = m.angles[0].a, m.angles[0].o, m.angles[0].b
        got = _angle_deg(sym, a, o, b)
        assert abs(got - expected_deg) < 1e-6, f"{a}-{o}-{b} = {got} != {expected_deg}"

    # The G-side mark must literally be B-G-H (no synthesis needed at the anchor vertex).
    g_mark = next(m for m in marks if m.angles[0].o == "G")
    assert {g_mark.angles[0].a, g_mark.angles[0].b} == {"B", "H"}
    # The H-side mark must use D (not C) for the line ray.
    h_mark = next(m for m in marks if m.angles[0].o == "H")
    assert h_mark.angles[0].a == "D" or h_mark.angles[0].b == "D"


def test_alternate_interior_matches_recipe_answer():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="alternate_interior",
        ray_ref_v1="A", ray_ref_v2="D", group="2",
    ))
    result = resolve_angle_pairs(diagram_ir, sym)
    marks = [r for r in result.render if isinstance(r, MarkAngles)]
    assert len(marks) == 2

    expected_deg = _angle_deg(sym, "H", "G", "A")
    for m in marks:
        got = _angle_deg(sym, m.angles[0].a, m.angles[0].o, m.angles[0].b)
        assert abs(got - expected_deg) < 1e-6

    g_mark = next(m for m in marks if m.angles[0].o == "G")
    assert {g_mark.angles[0].a, g_mark.angles[0].b} == {"A", "H"}
    h_mark = next(m for m in marks if m.angles[0].o == "H")
    # Must resolve to D (mirrored from the given ray_ref D... here D IS already
    # the correct natural choice per the hand derivation) and G.
    assert {h_mark.angles[0].a, h_mark.angles[0].b} == {"D", "G"}


def test_alternate_interior_resolves_correctly_even_if_llm_names_the_wrong_point():
    """If the model gives C instead of D at H (the documented common mistake),
    the resolver must still produce the geometrically correct pair — by
    mirroring C through H — not silently reproduce the LLM's mistake. The
    synthesized point lies on the same ray as D (same direction from H) but
    is not necessarily D's exact coordinates, since the mirror construction
    is defined relative to C and H, not D — so this checks angle-equivalence
    to G-H-D, not coordinate-equality with D."""
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="alternate_interior",
        ray_ref_v1="A", ray_ref_v2="C", group="2",  # C, not D
    ))
    result = resolve_angle_pairs(diagram_ir, sym)
    marks = [r for r in result.render if isinstance(r, MarkAngles)]
    h_mark = next(m for m in marks if m.angles[0].o == "H")
    line_ray_id = h_mark.angles[0].a if h_mark.angles[0].a != "G" else h_mark.angles[0].b
    # The resolver must not have reused "C" directly (that would reproduce the LLM's mistake).
    assert line_ray_id != "C"
    # The synthesized point must be angle-equivalent to using D directly (same
    # ray from H) — angle depends only on ray direction, not distance.
    expected_deg = _angle_deg(sym, "G", "H", "D")
    got_deg = _angle_deg(sym, "G", "H", line_ray_id)
    assert abs(got_deg - expected_deg) < 1e-6


def test_alternate_exterior_matches_recipe_answer():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="alternate_exterior",
        ray_ref_v1="B", ray_ref_v2="C", group="3",
    ))
    result = resolve_angle_pairs(diagram_ir, sym)
    marks = [r for r in result.render if isinstance(r, MarkAngles)]
    assert len(marks) == 2

    # E isn't in this sym table (not needed — the resolver never requires it),
    # so instead cross-check the two produced angles measure equal to each other.
    a0, o0, b0 = marks[0].angles[0].a, marks[0].angles[0].o, marks[0].angles[0].b
    a1, o1, b1 = marks[1].angles[0].a, marks[1].angles[0].o, marks[1].angles[0].b
    assert abs(_angle_deg(sym, a0, o0, b0) - _angle_deg(sym, a1, o1, b1)) < 1e-6

    g_mark = next(m for m in marks if m.angles[0].o == "G")
    assert "B" in (g_mark.angles[0].a, g_mark.angles[0].b)


def test_group_is_forwarded_to_both_marks():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="corresponding",
        ray_ref_v1="B", ray_ref_v2="D", group="1",
    ))
    result = resolve_angle_pairs(diagram_ir, sym)
    marks = [r for r in result.render if isinstance(r, MarkAngles)]
    assert all(m.group == "1" for m in marks)


def test_corresponding_synthesized_point_passes_render_angle_check():
    """The 'corresponding' relation always synthesizes a __pair{i}_H_trans point
    at v2 (H). check_render_angles' geometric fallback must accept this
    implicit point because it is directly referenced by the resolved
    MarkAngles triple, even though it's __-prefixed. Regression test for the
    bug where all synthesized points were rejected by the `not
    pid.startswith("__")` filter in _build_linear_pairs."""
    sym = _sym()
    diagram_ir = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=2), PointFixed(id="D", x=4, y=2),
            PointFixed(id="G", x=2.25, y=0), PointFixed(id="H", x=2.75, y=2),
            LineThrough(id="L1", p="A", q="B"),
            LineThrough(id="L2", p="C", q="D"),
            LineThrough(id="Trans", p="G", q="H"),
        ],
        pending_angle_pairs=[PendingAnglePair(
            v1="G", v2="H", relation="corresponding",
            ray_ref_v1="B", ray_ref_v2="D", group="1",
        )],
    )
    sym["Trans"] = spg.Line(sym["G"], sym["H"])
    sym["L2"] = spg.Line(sym["C"], sym["D"])
    sym["L1"] = spg.Line(sym["A"], sym["B"])

    result = resolve_angle_pairs(diagram_ir, sym)

    errors = check_render_angles(result, sym)
    assert errors == [], f"unexpected validation errors: {errors}"


def test_point_on_a_polygon_side_passes_render_angle_check():
    """Regression test: the geometric-containment fallback in
    _build_linear_pairs only checked spg.Line/Segment/Ray, never a
    Polygon/Triangle's own sides — so a point geometrically on a polygon's
    edge, but not structurally one of its own two endpoints, was wrongly
    rejected as 'not on any line/segment/ray through vertex'.

    Square A(0,0) B(4,0) C(4,4) D(0,4); M=(4,2) is the exact midpoint of
    side BC but is defined as an independent PointFixed, not derived from
    B/C — so the only way M can be recognized as lying on side BC is via
    the geometric containment fallback, not the structural pass. Mark the
    angle at vertex B (a real polygon vertex) with M (on side BC) and A
    (on side AB) as its two legs.
    """
    diagram_ir = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=4, y=4),
            PointFixed(id="D", x=0, y=4),
            PointFixed(id="M", x=4, y=2),
            Polygon(id="square", points=["A", "B", "C", "D"]),
        ],
        render=[
            MarkAngles(kind="mark_angles", angles=[AnglePoints(a="A", o="B", b="M")]),
        ],
    )
    sym = compile_defs(diagram_ir)
    errors = check_render_angles(diagram_ir, sym)
    assert errors == [], f"unexpected validation errors: {errors}"


def test_point_on_a_sector_radius_passes_render_angle_check():
    """Regression test: the geometric-containment fallback in
    _build_linear_pairs didn't know about Sector/EllipticalSector's two
    straight radii (center-start and center-end) — so marking a sector's
    own subtended angle at its center, using its start/end points as the
    two legs, was wrongly rejected.

    Center O=(0,0), start S=(2,0), end E=(0,2): a quarter-circle sector.
    Mark the angle at O with S and E as its two legs — the sector's own
    subtended angle.
    """
    diagram_ir = DiagramIR(
        define=[
            PointFixed(id="O", x=0, y=0),
            PointFixed(id="S", x=2, y=0),
            PointFixed(id="E", x=0, y=2),
            SectorCenterStartEnd(id="sec", center="O", start="S", end="E"),
        ],
        render=[
            MarkAngles(kind="mark_angles", angles=[AnglePoints(a="S", o="O", b="E")]),
        ],
    )
    sym = compile_defs(diagram_ir)
    errors = check_render_angles(diagram_ir, sym)
    assert errors == [], f"unexpected validation errors: {errors}"


def test_collinear_ray_ref_raises_retryable_ircompileerror():
    """If the LLM names a point ON the transversal itself (G-H line) as the
    ray_ref for the other line, _side cannot determine a side. This must
    surface as an IRCompileError (retryable by the strategy's LangGraph loop),
    not a bare ValueError."""
    sym = _sym()
    sym["T"] = spg.Point(sp.Float(2.5), sp.Float(1))  # on segment G-H, collinear
    diagram_ir = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=2), PointFixed(id="D", x=4, y=2),
            PointFixed(id="G", x=2.25, y=0), PointFixed(id="H", x=2.75, y=2),
            PointFixed(id="T", x=2.5, y=1),
        ],
        pending_angle_pairs=[PendingAnglePair(
            v1="G", v2="H", relation="corresponding",
            ray_ref_v1="B", ray_ref_v2="T", group="1",
        )],
    )
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    assert not isinstance(excinfo.value, ValueError)
    msg = str(excinfo.value)
    assert "T" in msg
    assert "other line" in msg.lower()


def test_unknown_point_id_raises_retryable_ircompileerror():
    """A nonexistent ray_ref id must surface as an actionable IRCompileError,
    not a bare KeyError, so the retry loop can catch it."""
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="corresponding",
        ray_ref_v1="NOPE", ray_ref_v2="D", group="1",
    ))
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    assert not isinstance(excinfo.value, KeyError)
    assert "NOPE" in str(excinfo.value)


def test_no_pending_pairs_is_a_noop():
    diagram_ir = DiagramIR(define=[PointFixed(id="A", x=0, y=0)])
    result = resolve_angle_pairs(diagram_ir, {"A": spg.Point(sp.Float(0), sp.Float(0))})
    assert result is diagram_ir


def test_non_point_ray_ref_raises_retryable_ircompileerror():
    """If the LLM names a line id (e.g. rays_along: ["L2", ...]) instead of a
    point id, `_lookup` must not let a raw AttributeError (from calling .x on
    a Line2D) escape the retry loop — it must raise IRCompileError naming the
    offending id and explaining it's not a point."""
    sym = _sym()
    sym["L2"] = spg.Line(sym["C"], sym["D"])
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="corresponding",
        ray_ref_v1="B", ray_ref_v2="L2", group="1",
    ))
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    assert not isinstance(excinfo.value, AttributeError)
    msg = str(excinfo.value)
    assert "L2" in msg
    assert "not a point" in msg.lower()


def test_non_parallel_lines_raise_ircompileerror():
    """The resolver assumes the two non-transversal lines through the vertices
    are parallel and never verifies it. If an LLM places the second line at
    the wrong slope (D moved off y=2), the two resolved angles are no longer
    equal, and tick-marking them as equal would be a silent rendering bug.
    The resolver must catch this and raise IRCompileError mentioning
    PARALLEL, rather than silently emit equal-looking tick marks."""
    sym = _sym()
    sym["D"] = spg.Point(sp.Float(4), sp.Float(3))  # C-D no longer parallel to A-B
    diagram_ir = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=2), PointFixed(id="D", x=4, y=3),
            PointFixed(id="G", x=2.25, y=0), PointFixed(id="H", x=2.75, y=2),
        ],
        pending_angle_pairs=[PendingAnglePair(
            v1="G", v2="H", relation="alternate_interior",
            ray_ref_v1="A", ray_ref_v2="D", group="1",
        )],
    )
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    assert "PARALLEL" in str(excinfo.value)


def test_v1_equals_v2_raises_ircompileerror():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="G", relation="corresponding",
        ray_ref_v1="B", ray_ref_v2="D", group="1",
    ))
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    assert "distinct" in str(excinfo.value).lower()


def test_ray_ref_coincides_with_vertex_raises_ircompileerror():
    sym = _sym()
    diagram_ir = _make_ir(PendingAnglePair(
        v1="G", v2="H", relation="corresponding",
        ray_ref_v1="G", ray_ref_v2="D", group="1",
    ))
    with pytest.raises(IRCompileError) as excinfo:
        resolve_angle_pairs(diagram_ir, sym)
    msg = str(excinfo.value)
    assert "G" in msg
    assert "coincides with its vertex" in msg.lower()
