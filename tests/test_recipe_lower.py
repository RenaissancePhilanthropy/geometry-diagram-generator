# tests/test_recipe_lower.py
"""Tests for the RecipeDSL → DiagramIR lowering pass.

Tests verify DiagramIR structure: definition kinds, count, field values.
No SymPy or rendering required.
"""
import math
import pytest
from recipe.dsl import (
    RecipeDSL, DSLAnnotations,
    TriangleOp, AltitudeOp, CircumcircleOp, IncircleOp,
    PerpendicularBisectorOp, AngleBisectorOp, CentroidOp, MedianOp,
    PolygonExteriorOp, MidpointOp, PerpendicularOp, ParallelOp,
    LineThroughOp, SegmentOp, IntersectionOp, CircleOp, CanvasOp,
    PolygonOp, PointOp, ReflectionOp, RotationOp, PointOnSegmentOp,
    RegularPolygonOp, PointAlongOp, ExtendSegmentOp,
    PointFootOp, CircleThrough3Op,
)
from recipe.lower import lower_to_ir, LoweringError
from ir.ir import (
    DiagramIR, PointFixed, PointMidpoint, PointFoot, PointTriangleCenter,
    LineThrough, LinePerpendicularThrough, LineParallelThrough,
    LineAngleBisector, CircleCenterPoint, CircleCenterRadius,
    Triangle, Polygon, PolygonExterior, Segment, Ray,
    PointRotate, PointReflect, PointBetween, PointIntersection,
    Draw, DrawPoints, LabelPoint, MarkRightAngles,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dsl(construction, annotations=None, mode="abstract"):
    ops = []
    for item in construction:
        if hasattr(item, "op"):
            ops.append(item)
        else:
            ops.append(item)
    ann = annotations or DSLAnnotations(auto_draw_all=False, auto_label_points=False)
    return RecipeDSL(mode=mode, construction=construction, annotations=ann)


def _kinds(ir: DiagramIR) -> list[str]:
    return [d.kind for d in ir.define]


def _ids(ir: DiagramIR) -> list[str]:
    return [d.id for d in ir.define]


# ---------------------------------------------------------------------------
# Foundation: triangle
# ---------------------------------------------------------------------------

def test_triangle_lowering_emits_three_point_fixed_and_triangle():
    dsl = _dsl([TriangleOp(id="T", vertices=["A","B","C"],
                            spec={"angle_A": 60, "angle_B": 60, "side_AB": 3})])
    ir = lower_to_ir(dsl)
    kinds = _kinds(ir)
    assert kinds.count("point_fixed") == 3
    assert kinds.count("triangle") == 1
    ids_ = _ids(ir)
    assert "A" in ids_
    assert "B" in ids_
    assert "C" in ids_
    assert "T" in ids_

def test_triangle_point_fixed_coords_are_floats():
    dsl = _dsl([TriangleOp(id="T", vertices=["A","B","C"],
                            spec={"side_AB": 3, "side_BC": 4, "side_CA": 5})])
    ir = lower_to_ir(dsl)
    fixed = [d for d in ir.define if d.kind == "point_fixed"]
    for f in fixed:
        assert isinstance(float(f.x), float)
        assert isinstance(float(f.y), float)


# ---------------------------------------------------------------------------
# Composite: altitude
# ---------------------------------------------------------------------------

def test_altitude_expansion():
    """altitude expands to: line_through(__alt_base) + line_perp_through(id) + point_foot(foot)"""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 70, "side_AB": 4}),
        AltitudeOp(id="alt_A", from_vertex="A", to_side=["B","C"], foot="H"),
    ])
    ir = lower_to_ir(dsl)
    ids_ = _ids(ir)
    assert "__alt_A_base" in ids_
    assert "alt_A" in ids_
    assert "H" in ids_

    base = next(d for d in ir.define if d.id == "__alt_A_base")
    alt  = next(d for d in ir.define if d.id == "alt_A")
    foot = next(d for d in ir.define if d.id == "H")

    assert base.kind == "line_through"
    assert base.p == "B" and base.q == "C"
    assert alt.kind == "line_perp_through"
    assert alt.through == "A"
    assert alt.to_line == "__alt_A_base"
    assert foot.kind == "point_foot"
    assert foot.source == "A"
    assert foot.onto == "__alt_A_base"

def test_altitude_auto_generates_perpendicular_check():
    from ir.ir import Perpendicular
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 70, "side_AB": 4}),
        AltitudeOp(id="alt_A", from_vertex="A", to_side=["B","C"], foot="H"),
    ])
    ir = lower_to_ir(dsl)
    perp_checks = [c for c in ir.checks if c.kind == "perpendicular"]
    assert len(perp_checks) == 1
    c = perp_checks[0]
    assert c.l1 == "alt_A"
    assert c.l2 == "__alt_A_base"


# ---------------------------------------------------------------------------
# Composite: circumcircle
# ---------------------------------------------------------------------------

def test_circumcircle_expansion():
    """circumcircle expands to: point_triangle_center(circumcenter) + circle_center_point"""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        CircumcircleOp(id="cc", of="T", center="O"),
    ])
    ir = lower_to_ir(dsl)
    center_def = next(d for d in ir.define if d.id == "O")
    circle_def = next(d for d in ir.define if d.id == "cc")

    assert center_def.kind == "point_triangle_center"
    assert center_def.which == "circumcenter"
    assert center_def.tri == "T"
    assert circle_def.kind == "circle_center_point"
    assert circle_def.center == "O"
    assert circle_def.through == "A"  # first vertex of triangle T


# ---------------------------------------------------------------------------
# Composite: incircle
# ---------------------------------------------------------------------------

def test_incircle_expansion():
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A","B","C"],
         "spec": {"angle_A": 60, "angle_B": 70, "side_AB": 4}},
        {"op": "incircle", "id": "ic", "of": "T", "center": "I"},
    ])
    ir = lower_to_ir(dsl)
    ids = [d.id for d in ir.define]
    assert "I" in ids and "ic" in ids
    circle_def = next(d for d in ir.define if d.id == "ic")
    # Inradius is computed numerically when triangle coordinates are known
    assert isinstance(circle_def.radius, (int, float))
    assert circle_def.radius > 0


# ---------------------------------------------------------------------------
# Composite: perpendicular_bisector
# ---------------------------------------------------------------------------

def test_perpendicular_bisector_expansion():
    """perp_bisector: line_through(__pb_base) + point_midpoint(mid) + line_perp_through(id)"""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        PerpendicularBisectorOp(id="pb", of=["A","B"], mid="M"),
    ])
    ir = lower_to_ir(dsl)
    base = next(d for d in ir.define if d.id == "__pb_base")
    mid  = next(d for d in ir.define if d.id == "M")
    pb   = next(d for d in ir.define if d.id == "pb")

    assert base.kind == "line_through"
    assert set([base.p, base.q]) == {"A", "B"}
    assert mid.kind == "point_midpoint"
    assert set([mid.p, mid.q]) == {"A", "B"}
    assert pb.kind == "line_perp_through"
    assert pb.through == "M"
    assert pb.to_line == "__pb_base"


# ---------------------------------------------------------------------------
# Composite: angle_bisector
# ---------------------------------------------------------------------------

def test_angle_bisector_expansion():
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        AngleBisectorOp(id="ab_B", vertex="B", ray1_toward="A", ray2_toward="C"),
    ])
    ir = lower_to_ir(dsl)
    ab = next(d for d in ir.define if d.id == "ab_B")
    assert ab.kind == "line_angle_bisector"
    assert ab.vertex == "B"
    assert ab.a == "A"
    assert ab.b == "C"


# ---------------------------------------------------------------------------
# Composite: centroid
# ---------------------------------------------------------------------------

def test_centroid_expansion():
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        CentroidOp(id="G", of="T"),
    ])
    ir = lower_to_ir(dsl)
    g = next(d for d in ir.define if d.id == "G")
    assert g.kind == "point_triangle_center"
    assert g.which == "centroid"
    assert g.tri == "T"


# ---------------------------------------------------------------------------
# Composite: median
# ---------------------------------------------------------------------------

def test_median_expansion():
    """median: point_midpoint(mid) + segment(id)"""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        MedianOp(id="med_A", from_vertex="A", to_side=["B","C"], mid="M_BC"),
    ])
    ir = lower_to_ir(dsl)
    mid = next(d for d in ir.define if d.id == "M_BC")
    med = next(d for d in ir.define if d.id == "med_A")

    assert mid.kind == "point_midpoint"
    assert set([mid.p, mid.q]) == {"B", "C"}
    assert med.kind == "segment"
    assert med.a == "A"
    assert med.b == "M_BC"


# ---------------------------------------------------------------------------
# Derived: passthroughs
# ---------------------------------------------------------------------------

def test_midpoint_passthrough():
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        MidpointOp(id="M", of=["A","B"]),
    ])
    ir = lower_to_ir(dsl)
    m = next(d for d in ir.define if d.id == "M")
    assert m.kind == "point_midpoint"
    assert m.p == "A" and m.q == "B"

def test_perpendicular_passthrough():
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        LineThroughOp(id="L", points=["A","B"]),
        PerpendicularOp(id="perp", to_line="L", through="C"),
    ])
    ir = lower_to_ir(dsl)
    perp = next(d for d in ir.define if d.id == "perp")
    assert perp.kind == "line_perp_through"
    assert perp.to_line == "L"
    assert perp.through == "C"

def test_segment_passthrough():
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        SegmentOp(id="s", endpoints=["A","B"]),
    ])
    ir = lower_to_ir(dsl)
    s = next(d for d in ir.define if d.id == "s")
    assert s.kind == "segment"
    assert s.a == "A" and s.b == "B"

def test_rotation_degrees_to_radians():
    """RotationOp angle (degrees) must be converted to radians in IR."""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        RotationOp(id="R", point="A", center="B", angle=90),
    ])
    ir = lower_to_ir(dsl)
    r = next(d for d in ir.define if d.id == "R")
    assert r.kind == "point_rotate"
    # angle should be π/2 radians (approximately 1.5707...)
    angle_val = float(r.angle) if isinstance(r.angle, (int, float)) else float(r.angle)
    assert abs(angle_val - math.pi/2) < 1e-9

def test_intersection_with_selector():
    """IntersectionOp selector dict is lowered to a PickRule."""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        CircleOp(id="c", center="A", radius=2),
        LineThroughOp(id="L", points=["B","C"]),
        IntersectionOp(id="P", of=["L","c"],
                       selector={"kind": "upper_of_line", "a": "B", "b": "C"}),
    ])
    ir = lower_to_ir(dsl)
    p = next(d for d in ir.define if d.id == "P")
    assert p.kind == "point_intersection"
    assert p.pick is not None
    assert p.pick.kind == "upper_of_line"


# ---------------------------------------------------------------------------
# Auto-annotation
# ---------------------------------------------------------------------------

def test_auto_draw_all_emits_draw_ops():
    """auto_draw_all=True emits Draw for each non-point non-implicit object."""
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
            SegmentOp(id="seg", endpoints=["A","B"]),
        ],
        annotations=DSLAnnotations(auto_draw_all=True, auto_label_points=False),
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    drawn_ids = {r.obj for r in draw_ops}
    assert "T" in drawn_ids
    assert "seg" in drawn_ids
    # Implicit __ IDs should NOT appear
    assert not any(oid.startswith("__") for oid in drawn_ids)

def test_auto_label_points_emits_label_ops():
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
        ],
        annotations=DSLAnnotations(auto_draw_all=False, auto_label_points=True),
    )
    ir = lower_to_ir(dsl)
    label_ops = [r for r in ir.render if r.kind == "label_point"]
    labeled = {r.p for r in label_ops}
    assert {"A","B","C"}.issubset(labeled)

def test_auto_mark_right_angles_emits_mark_op():
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"right_angle_at": "B", "side_AB": 3, "side_BC": 4}),
        ],
        annotations=DSLAnnotations(auto_draw_all=False, auto_label_points=False,
                                    auto_mark_right_angles=True),
    )
    ir = lower_to_ir(dsl)
    mark_ops = [r for r in ir.render if r.kind == "mark_right_angles"]
    assert len(mark_ops) == 1

def test_implicit_ids_excluded_from_auto_draw():
    """__-prefixed IDs from composite ops must not appear in auto-draw."""
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(id="T", vertices=["A","B","C"],
                       spec={"angle_A": 60, "angle_B": 70, "side_AB": 4}),
            AltitudeOp(id="alt_A", from_vertex="A", to_side=["B","C"], foot="H"),
        ],
        annotations=DSLAnnotations(auto_draw_all=True, auto_label_points=False),
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    drawn_ids = {r.obj for r in draw_ops}
    assert "__alt_A_base" not in drawn_ids


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

def test_canvas_op_sets_ir_canvas():
    dsl = RecipeDSL(
        mode="grid",
        construction=[
            CanvasOp(id="_canvas", x_range=[-1, 9], y_range=[-1, 9]),
            PointOp(id="A", coords=[0.0, 0.0]),
        ],
        annotations=DSLAnnotations(auto_draw_all=False, auto_label_points=False),
    )
    ir = lower_to_ir(dsl)
    assert ir.canvas is not None
    assert ir.canvas.xmin == -1
    assert ir.canvas.xmax == 9

def test_auto_canvas_computed_from_triangle():
    """Without explicit canvas op, lowering auto-computes canvas from solved coords."""
    dsl = _dsl([
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "side_AB": 3}),
    ])
    ir = lower_to_ir(dsl)
    assert ir.canvas is not None
    assert ir.canvas.xmin < ir.canvas.xmax
    assert ir.canvas.ymin < ir.canvas.ymax


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unknown_triangle_in_circumcircle_raises():
    with pytest.raises(LoweringError):
        lower_to_ir(_dsl([
            CircumcircleOp(id="cc", of="T_missing", center="O"),
        ]))


def test_polygon_exterior_lowering():
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A","B","C"],
         "spec": {"angle_A": 60, "angle_B": 70, "side_AB": 4}},
        {"op": "polygon_exterior", "id": "sq", "base": ["A","B"],
         "ref_point": "C", "n": 4, "vertices": ["sq_v2","sq_v3"]},
    ])
    ir = lower_to_ir(dsl)
    ids = [d.id for d in ir.define]
    assert "sq" in ids
    sq_def = next(d for d in ir.define if d.id == "sq")
    # base [A,B] should be in the polygon exterior def
    assert sq_def.a == "A" and sq_def.b == "B"
    assert sq_def.ref == "C"
    assert sq_def.sides == 4


def test_multiple_triangles_circumcircle():
    """Circumcircle expansion correctly finds vertices of the referenced triangle."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T1", "vertices": ["A","B","C"],
         "spec": {"angle_A": 60, "angle_B": 70, "side_AB": 4}},
        {"op": "triangle", "id": "T2", "vertices": ["P","Q","R"],
         "spec": {"angle_P": 50, "angle_Q": 60, "side_PQ": 4}},
        {"op": "circumcircle", "id": "cc2", "of": "T2", "center": "O2"},
    ])
    ir = lower_to_ir(dsl)
    cc2 = next(d for d in ir.define if d.id == "cc2")
    # The circumcircle of T2 should reference a T2 vertex, not a T1 vertex
    assert cc2.through in ["P", "Q", "R"]


def test_altitude_triangle_field():
    """Altitude can be specified with triangle= field; lowering infers opposite side."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A","B","C"],
         "spec": {"angle_A": 60, "angle_B": 70, "side_AB": 4}},
        {"op": "altitude", "id": "alt_A", "from_vertex": "A", "triangle": "T", "foot": "H"},
    ])
    ir = lower_to_ir(dsl)
    ids = [d.id for d in ir.define]
    assert "H" in ids and "alt_A" in ids
    # The implicit base line should reference B and C (the vertices opposite A)
    base_def = next(d for d in ir.define if d.id == "__alt_A_base")
    assert set([base_def.p, base_def.q]) == {"B", "C"}


def test_perpendicular_point_pair_to_line():
    """PerpendicularOp with to_line=[A,B] emits an implicit LineThroughOp."""
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [4, 0]},
        {"op": "point", "id": "P", "coords": [2, 3]},
        {"op": "perpendicular", "id": "perp", "to_line": ["A","B"], "through": "P"},
    ])
    ir = lower_to_ir(dsl)
    ids = [d.id for d in ir.define]
    assert "perp" in ids
    # implicit reference line should be emitted
    assert "__perp_ref" in ids


def test_visible_false_excluded_from_auto_draw():
    """ops with visible=False are not included in auto_draw render ops."""
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [4, 0]},
        {"op": "line_through", "id": "aux_line", "points": ["A","B"], "visible": False},
    ])
    ir = lower_to_ir(dsl)
    draw_ids = [r.obj for r in ir.render if isinstance(r, Draw)]
    assert "aux_line" not in draw_ids


# ---------------------------------------------------------------------------
# Marks and labels lowering
# ---------------------------------------------------------------------------

def test_mark_angle_lowered():
    """marks: [{kind: mark_angle, ...}] → MarkAngles render op."""
    from ir.ir import MarkAngles
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 3]},
    ], annotations={"marks": [{"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C"}]})
    ir = lower_to_ir(dsl)
    mark_ops = [r for r in ir.render if isinstance(r, MarkAngles)]
    assert len(mark_ops) == 1
    assert mark_ops[0].angles[0].a == "B"
    assert mark_ops[0].angles[0].o == "A"
    assert mark_ops[0].angles[0].b == "C"


def test_mark_right_angle_lowered():
    """marks: [{kind: mark_right_angle, ...}] → MarkRightAngles render op."""
    from ir.ir import MarkRightAngles
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 3]},
    ], annotations={"marks": [{"kind": "mark_right_angle", "a": "B", "vertex": "A", "b": "C"}]})
    ir = lower_to_ir(dsl)
    mark_ops = [r for r in ir.render if isinstance(r, MarkRightAngles)]
    assert len(mark_ops) == 1
    assert mark_ops[0].angles[0].o == "A"


def test_mark_equal_lengths_lowered():
    """marks: [{kind: mark_equal_lengths, ...}] → MarkSegments + implicit segment defs."""
    from ir.ir import MarkSegments, Segment
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 3]},
        {"op": "point", "id": "D", "coords": [3, 3]},
    ], annotations={"marks": [{"kind": "mark_equal_lengths", "segments": [["A", "B"], ["C", "D"]], "group": 1}]})
    ir = lower_to_ir(dsl)
    seg_marks = [r for r in ir.render if isinstance(r, MarkSegments)]
    assert len(seg_marks) == 1
    assert len(seg_marks[0].segs) == 2
    # Each seg_id should correspond to a Segment def
    def_ids = {d.id for d in ir.define}
    for seg_id in seg_marks[0].segs:
        assert seg_id in def_ids


def test_label_segment_lowered():
    """labels: [{kind: label_segment, ...}] → LabelSegment render op."""
    from ir.ir import LabelSegment
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "segment", "id": "s1", "endpoints": ["A", "B"]},
    ], annotations={"labels": [{"kind": "label_segment", "endpoints": ["A", "B"], "text": "5cm"}]})
    ir = lower_to_ir(dsl)
    label_ops = [r for r in ir.render if isinstance(r, LabelSegment)]
    assert len(label_ops) == 1
    assert label_ops[0].text == "5cm"
    # Should reuse the existing segment, not create a duplicate
    seg_defs = [d for d in ir.define if hasattr(d, 'a') and hasattr(d, 'b') and {getattr(d,'a'), getattr(d,'b')} == {"A","B"}]
    assert len(seg_defs) == 1


def test_triangle_center_places_centroid():
    """Triangle with center:[x,y] has centroid at the requested location."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "t1", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}, "center": [0, 0]},
    ])
    ir = lower_to_ir(dsl)
    coords = {d.id: (d.x, d.y) for d in ir.define if hasattr(d, 'x') and hasattr(d, 'y')}
    xs = [coords["A"][0], coords["B"][0], coords["C"][0]]
    ys = [coords["A"][1], coords["B"][1], coords["C"][1]]
    assert abs(sum(xs)/3 - 0.0) < 1e-6
    assert abs(sum(ys)/3 - 0.0) < 1e-6


def test_two_triangles_with_centers_non_overlapping():
    """Two triangles with different centers are spatially separated."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "t1", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 50, "angle_B": 70, "side_AB": 3}, "center": [2, 2]},
        {"op": "triangle", "id": "t2", "vertices": ["D", "E", "F"],
         "spec": {"angle_D": 50, "angle_E": 70, "side_DE": 5}, "center": [8, 2]},
    ])
    ir = lower_to_ir(dsl)
    coords = {d.id: (d.x, d.y) for d in ir.define if hasattr(d, 'x') and hasattr(d, 'y')}
    t1_xs = [coords["A"][0], coords["B"][0], coords["C"][0]]
    t2_xs = [coords["D"][0], coords["E"][0], coords["F"][0]]
    # Centroids should be ~2 and ~8 apart — no overlap
    assert abs(sum(t1_xs)/3 - 2.0) < 1e-6
    assert abs(sum(t2_xs)/3 - 8.0) < 1e-6
