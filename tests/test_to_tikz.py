from __future__ import annotations

from ir.ir import (
    AnglePoints,
    Canvas,
    DiagramIR,
    Draw,
    LabelAngle,
    LabelPoint,
    LineAngleBisector,
    LineParallelThrough,
    LinePerpendicularThrough,
    LineTangent,
    LineThrough,
    MarkAngles,
    MarkRightAngles,
    MarkSegments,
    PointFixed,
    PointIntersection,
    PointOn,
    PointOnParam,
    Segment,
    Triangle,
)
import sympy.geometry as spg
from ir.checks import check_render_angles
from ir.to_sympy import compile_defs
from ir.to_tikz import _style_str, ir_to_tikz


def _compile_tikz(diagram: DiagramIR) -> str:
    sym = compile_defs(diagram)
    return ir_to_tikz(diagram, sym)


def test_ir_to_tikz_emits_raw_coordinate_plane():
    diagram = DiagramIR(
        canvas=Canvas(
            xmin=-0.5,
            xmax=4.2,
            ymin=-0.5,
            ymax=3.6,
            grid=True,
            grid_step=1,
            axes=True,
            tick_step=1,
            show_ticks=True,
            show_tick_labels=True,
            show_axis_labels=True,
        ),
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=0, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[Draw(obj="T")],
    )

    tikz = _compile_tikz(diagram)

    assert "\\tkzGrid" not in tikz
    assert "\\tkzAxeXY" not in tikz
    assert "\\draw[gray!35,thin,step=1] (-1,-1) grid (5,4);" in tikz
    assert "\\draw[->,thick] (-0.5,0) -- (4.2,0) node[right] {$x$};" in tikz
    assert "\\draw[->,thick] (0,-0.5) -- (0,3.6) node[above] {$y$};" in tikz
    assert "\\node[below, font=\\small] at (1,0) {1};" in tikz
    assert "\\node[left, font=\\small] at (0,1) {1};" in tikz


def test_ir_to_tikz_expands_bounds_to_include_origin_for_axes():
    diagram = DiagramIR(
        canvas=Canvas(xmin=1, xmax=4, ymin=1, ymax=3, axes=True),
        define=[PointFixed(id="A", x=1, y=1)],
        render=[LabelPoint(p="A", pos="above")],
    )

    tikz = _compile_tikz(diagram)

    assert "\\tkzInit[xmin=0,xmax=4,ymin=0,ymax=3]" in tikz
    assert "\\draw[->,thick] (0,0) -- (4,0);" in tikz
    assert "\\draw[->,thick] (0,0) -- (0,3);" in tikz


def test_ir_to_tikz_label_point_text_preserves_point_name():
    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[LabelPoint(p="A", text=r"A\,(0,0)", pos="below")],
    )

    tikz = _compile_tikz(diagram)

    assert r"\tkzLabelPoint[below](A){$A\,(0,0)$}" in tikz


# ---------------------------------------------------------------------------
# Helpers for angle tests — a simple triangle with three named vertices
# ---------------------------------------------------------------------------

def _triangle_diagram(*render_ops) -> DiagramIR:
    """Return a minimal DiagramIR with points A(0,0), B(4,0), C(2,3)."""
    return DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
        ],
        render=list(render_ops),
    )


# ---------------------------------------------------------------------------
# _style_str unit tests
# ---------------------------------------------------------------------------

def test_style_str_returns_empty_for_unknown_key():
    assert _style_str("custom_style", {}) == ""


def test_style_str_color_fallback_for_known_names():
    assert _style_str("red", {}) == "[color=red]"
    assert _style_str("blue", {}) == "[color=blue]"
    assert _style_str("green", {}) == "[color=green]"


def test_style_str_dict_lookup_takes_precedence():
    styles = {"red": {"color": "red", "thick": True}}
    assert _style_str("red", styles) == "[color=red,thick]"


def test_style_str_returns_empty_for_none():
    assert _style_str(None, {}) == ""


# ---------------------------------------------------------------------------
# MarkAngles TikZ output tests
# ---------------------------------------------------------------------------

def test_mark_angles_color_style():
    diagram = _triangle_diagram(
        MarkAngles(angles=[AnglePoints(a="B", o="A", b="C")], style="red"),
    )
    tikz = _compile_tikz(diagram)
    assert r"\tkzMarkAngle[size=0.5,color=red]" in tikz


def test_mark_angles_no_style_emits_size_only():
    diagram = _triangle_diagram(
        MarkAngles(angles=[AnglePoints(a="B", o="A", b="C")]),
    )
    tikz = _compile_tikz(diagram)
    assert r"\tkzMarkAngle[size=0.5]" in tikz
    assert "color" not in tikz


def test_mark_angles_style_from_styles_dict():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="B", o="A", b="C")], style="alpha")],
        styles={"alpha": {"color": "blue", "thick": True}},
    )
    tikz = _compile_tikz(diagram)
    assert r"\tkzMarkAngle[size=0.5,color=blue,thick]" in tikz


# ---------------------------------------------------------------------------
# LabelAngle TikZ output tests
# ---------------------------------------------------------------------------

def test_label_angle_color_style():
    diagram = _triangle_diagram(
        LabelAngle(angle=AnglePoints(a="B", o="A", b="C"), text="x", style="blue"),
    )
    tikz = _compile_tikz(diagram)
    assert r"\tkzLabelAngle[color=blue]" in tikz
    assert "{$x$}" in tikz


def test_label_angle_no_style():
    diagram = _triangle_diagram(
        LabelAngle(angle=AnglePoints(a="B", o="A", b="C"), text=r"\alpha"),
    )
    tikz = _compile_tikz(diagram)
    assert r"\tkzLabelAngle(" in tikz
    assert "color" not in tikz


# ---------------------------------------------------------------------------
# MarkSegments TikZ output tests
# ---------------------------------------------------------------------------

def test_mark_segments_different_groups_get_different_marks():
    # Two groups of equal segments should receive escalating tick marks.
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="C", x=4, y=0),
            PointFixed(id="D", x=6, y=0),
            Segment(id="s1", a="A", b="B"),
            Segment(id="s2", a="C", b="D"),
        ],
        render=[
            MarkSegments(segs=["s1"], group="alpha"),
            MarkSegments(segs=["s2"], group="beta"),
        ],
    )
    tikz = _compile_tikz(diagram)
    assert "mark=|" in tikz
    assert "mark=||" in tikz


def test_mark_segments_single_group_gets_single_tick():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            Segment(id="s1", a="A", b="B"),
        ],
        render=[MarkSegments(segs=["s1"], group="alpha")],
    )
    tikz = _compile_tikz(diagram)
    assert "[mark=|]" in tikz


def test_mark_segments_style_overrides_group_mark():
    # An explicit style entry should take precedence over group auto-assignment.
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            PointFixed(id="C", x=4, y=0),
            PointFixed(id="D", x=6, y=0),
            Segment(id="s1", a="A", b="B"),
            Segment(id="s2", a="C", b="D"),
        ],
        styles={"alpha": {"mark": "|||"}},
        render=[
            MarkSegments(segs=["s1"], group="alpha"),
            MarkSegments(segs=["s2"], group="beta"),
        ],
    )
    tikz = _compile_tikz(diagram)
    assert "mark=|||" in tikz   # style dict entry honoured for alpha
    assert "mark=|]" in tikz    # beta gets first auto-assigned symbol


# ---------------------------------------------------------------------------
# check_render_angles tests
# ---------------------------------------------------------------------------

def _transversal_diagram(*render_ops) -> DiagramIR:
    """Two parallel lines cut by a transversal: A,B on line AB; C,D on line CD;
    P1,P2 on transversal; G = intersection of transversal & AB; H = intersection
    of transversal & CD."""
    return DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=3),
            PointFixed(id="B", x=6, y=3),
            PointFixed(id="C", x=0, y=0),
            PointFixed(id="D", x=6, y=0),
            PointFixed(id="P1", x=1, y=5),
            PointFixed(id="P2", x=5, y=-2),
            LineThrough(id="l_AB", p="A", q="B"),
            LineThrough(id="l_CD", p="C", q="D"),
            LineThrough(id="l_t", p="P1", q="P2"),
            PointIntersection(id="G", obj1="l_t", obj2="l_AB"),
            PointIntersection(id="H", obj1="l_t", obj2="l_CD"),
        ],
        render=list(render_ops),
    )


def test_check_render_angles_valid():
    # G is on l_AB (so A,G and B,G are valid) and on l_t (so P1,G and P2,G are valid)
    diagram = _transversal_diagram(
        MarkAngles(angles=[AnglePoints(a="B", o="G", b="P1")]),
    )
    assert check_render_angles(diagram) == []


def test_check_render_angles_invalid_foreign_point():
    # H is on l_CD and l_t; B is only on l_AB — not connected to H
    diagram = _transversal_diagram(
        MarkAngles(angles=[AnglePoints(a="B", o="H", b="P1")]),
    )
    errors = check_render_angles(diagram)
    assert len(errors) == 1
    assert "'B'" in errors[0]
    assert "'H'" in errors[0]


def test_check_render_angles_intersection_inherits_both_lines():
    # G is on l_t, so P1 and G are a valid pair via l_t
    # G is on l_AB, so A and G are a valid pair via l_AB
    diagram = _transversal_diagram(
        MarkAngles(angles=[AnglePoints(a="A", o="G", b="P2")]),
    )
    assert check_render_angles(diagram) == []


def test_check_render_angles_valid_segment():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Segment(id="AB", a="A", b="B"),
            Segment(id="AC", a="A", b="C"),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="B", o="A", b="C")])],
    )
    assert check_render_angles(diagram) == []


def test_check_render_angles_triangle_vertices():
    # Triangle edges are inferred: A-B, B-C, A-C
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=2, y=3),
            Triangle(id="T", a="A", b="B", c="C"),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="B", o="A", b="C")])],
    )
    assert check_render_angles(diagram) == []


def test_check_render_angles_line_perp_through():
    # Typical perpendicular bisector: M is midpoint of A-B, perp line through M,
    # P_up is a point on the perp line.
    # Angle triple (A, M, P_up) must be valid:
    #   {A,M} via midpoint virtual segment; {M,P_up} via perp line (new fix).
    from ir.ir import PointMidpoint
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            LineThrough(id="l_AB", p="A", q="B"),
            PointMidpoint(id="M", p="A", q="B"),
            LinePerpendicularThrough(id="perp", through="M", to_line="l_AB"),
            PointOn(id="P_up", on="perp", how=PointOnParam(t=0.5)),
        ],
        render=[MarkRightAngles(angles=[AnglePoints(a="A", o="M", b="P_up")])],
    )
    assert check_render_angles(diagram) == []


def test_check_render_angles_line_parallel_through():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=4, y=0),
            PointFixed(id="C", x=1, y=2),
            LineThrough(id="l_AB", p="A", q="B"),
            LineParallelThrough(id="l_par", through="C", to_line="l_AB"),
            PointOn(id="D", on="l_par", how=PointOnParam(t=0.5)),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="B", o="A", b="D")])],
    )
    # A is only on l_AB; D is only on l_par → {A,D} not a valid pair
    errors = check_render_angles(diagram)
    assert len(errors) == 1


def test_check_render_angles_line_angle_bisector():
    # V is vertex of the bisector (registered on bis), D is a point on bis.
    # Angle triple (V, D_other, ...) — test valid case: (V, D, ...) where V-D share bis.
    # Also test that V connects to A via a segment for a full angle triple (A, V, D).
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=2),
            PointFixed(id="V", x=0, y=0),
            PointFixed(id="B", x=2, y=0),
            Segment(id="VA", a="V", b="A"),
            LineAngleBisector(id="bis", a="A", vertex="V", b="B"),
            PointOn(id="D", on="bis", how=PointOnParam(t=0.5)),
        ],
        render=[MarkAngles(angles=[AnglePoints(a="A", o="V", b="D")])],
    )
    assert check_render_angles(diagram) == []


# ---------------------------------------------------------------------------
# Guard tests: render ops referencing undefined IDs should skip, not crash
# ---------------------------------------------------------------------------

def test_ir_to_tikz_skips_draw_with_missing_id():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
        ],
        render=[Draw(obj="AM")],
    )
    sym = compile_defs(diagram)
    tikz = ir_to_tikz(diagram, sym)
    assert "AM" not in tikz


def test_ir_to_tikz_valid_draw_still_works():
    diagram = DiagramIR(
        define=[
            PointFixed(id="A", x=0, y=0),
            PointFixed(id="B", x=3, y=0),
            Segment(id="AB", a="A", b="B"),
        ],
        render=[Draw(obj="AB")],
    )
    sym = compile_defs(diagram)
    tikz = ir_to_tikz(diagram, sym)
    assert "\\tkzDrawSegment" in tikz
    assert "(A,B)" in tikz
