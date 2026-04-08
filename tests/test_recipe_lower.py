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


def test_perpendicular_bisector_emits_base_segment_when_no_explicit_segment():
    """Without an explicit segment op, perp_bisector should auto-emit a drawable segment."""
    dsl = _dsl([
        PointOp(id="A", coords=[0.0, 0.0]),
        PointOp(id="B", coords=[4.0, 0.0]),
        PerpendicularBisectorOp(id="pb_AB", of=["A", "B"], mid="M"),
    ], annotations={"auto_draw_all": True, "auto_label_points": False})
    ir = lower_to_ir(dsl)
    # A Segment between A and B should exist in the IR defines
    segs = [d for d in ir.define if d.kind == "segment" and {d.a, d.b} == {"A", "B"}]
    assert segs, "Expected a segment A-B to be auto-emitted by perp bisector lowering"
    seg_id = segs[0].id
    # That segment should be drawn
    drawn = [r.obj for r in ir.render if r.kind == "draw"]
    assert seg_id in drawn, f"Segment {seg_id!r} not found in draw ops"


def test_perpendicular_bisector_no_duplicate_segment_when_explicit():
    """When the user already defined a segment A-B, perp_bisector should not add another."""
    dsl = _dsl([
        PointOp(id="A", coords=[0.0, 0.0]),
        PointOp(id="B", coords=[4.0, 0.0]),
        SegmentOp(id="seg_AB", endpoints=["A", "B"]),
        PerpendicularBisectorOp(id="pb_AB", of=["A", "B"], mid="M"),
    ], annotations={"auto_draw_all": True, "auto_label_points": False})
    ir = lower_to_ir(dsl)
    segs = [d for d in ir.define if d.kind == "segment" and {d.a, d.b} == {"A", "B"}]
    assert len(segs) == 1, "Should have exactly one segment A-B, not a duplicate"


# ---------------------------------------------------------------------------
# Triangle spec key remapping
# ---------------------------------------------------------------------------

from recipe.lower import _remap_triangle_spec


def test_remap_triangle_spec_noop_when_abc_vertices():
    """No remapping when vertices include A, B, or C."""
    spec = {"angle_A": 60, "side_AB": 3}
    assert _remap_triangle_spec(["A", "B", "C"], spec) == spec


def test_remap_triangle_spec_noop_when_partial_abc_overlap():
    """No remapping when even one vertex is A/B/C."""
    spec = {"angle_A": 60, "angle_B": 70, "side_AB": 3}
    assert _remap_triangle_spec(["A", "D", "E"], spec) == spec


def test_remap_triangle_spec_remaps_angles_and_sides():
    """Full remap for vertices completely disjoint from {A, B, C}."""
    spec = {"angle_A": 50, "angle_B": 70, "side_AB": 5}
    result = _remap_triangle_spec(["D", "E", "F"], spec)
    assert result == {"angle_D": 50, "angle_E": 70, "side_DE": 5}


def test_remap_triangle_spec_right_angle_at():
    """right_angle_at value is also remapped."""
    spec = {"right_angle_at": "A", "side_AB": 3, "side_CA": 4}
    result = _remap_triangle_spec(["P", "Q", "R"], spec)
    assert result["right_angle_at"] == "P"
    assert "side_PQ" in result
    assert "side_RP" in result


def test_remap_triangle_spec_integration_similar_triangles():
    """Two triangles: second with D/E/F vertices and generic A/B/C spec keys should lower."""
    dsl = _dsl([
        TriangleOp(id="triABC", vertices=["A", "B", "C"],
                   spec={"angle_A": 50, "angle_B": 70, "side_AB": 3},
                   center=[2.0, 1.5]),
        TriangleOp(id="triDEF", vertices=["D", "E", "F"],
                   spec={"angle_A": 50, "angle_B": 70, "side_AB": 5},  # generic keys
                   center=[7.0, 2.5]),
    ])
    ir = lower_to_ir(dsl)  # should not raise
    assert any(d.id == "D" for d in ir.define)
    assert any(d.id == "E" for d in ir.define)
    assert any(d.id == "F" for d in ir.define)


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


def test_regular_polygon_star_lowering_reorders_vertices():
    """star=True produces a Polygon with every-2nd-vertex winding."""
    dsl = _dsl([
        PointOp(id="O", coords=[0, 0]),
        RegularPolygonOp(id="star", center="O", radius=3, start_angle=90,
                         vertices=["A","B","C","D","E"], star=True),
    ], mode="grid")
    ir = lower_to_ir(dsl)
    poly = next(d for d in ir.define if d.id == "star")
    assert poly.kind == "polygon"
    assert poly.points == ["A", "C", "E", "B", "D"]


def test_regular_polygon_no_star_lowering_sequential():
    """star=False (default) produces a Polygon with sequential vertex order."""
    dsl = _dsl([
        PointOp(id="O", coords=[0, 0]),
        RegularPolygonOp(id="pent", center="O", radius=3, start_angle=90,
                         vertices=["A","B","C","D","E"]),
    ], mode="grid")
    ir = lower_to_ir(dsl)
    poly = next(d for d in ir.define if d.id == "pent")
    assert poly.kind == "polygon"
    assert poly.points == ["A", "B", "C", "D", "E"]


def test_regular_polygon_star_point_coords_unchanged():
    """star=True does not alter the computed coordinates of the vertices."""
    import math
    dsl_star = _dsl([
        PointOp(id="O", coords=[0, 0]),
        RegularPolygonOp(id="star", center="O", radius=3, start_angle=0,
                         vertices=["A","B","C","D","E"], star=True),
    ], mode="grid")
    dsl_conv = _dsl([
        PointOp(id="O", coords=[0, 0]),
        RegularPolygonOp(id="pent", center="O", radius=3, start_angle=0,
                         vertices=["A","B","C","D","E"]),
    ], mode="grid")
    ir_star = lower_to_ir(dsl_star)
    ir_conv = lower_to_ir(dsl_conv)
    # Point coords should be identical — only the Polygon winding differs
    pts_star = {d.id: (d.x, d.y) for d in ir_star.define if d.kind == "point_fixed" and d.id in list("ABCDE")}
    pts_conv = {d.id: (d.x, d.y) for d in ir_conv.define if d.kind == "point_fixed" and d.id in list("ABCDE")}
    assert pts_star == pts_conv


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


# ---------------------------------------------------------------------------
# Explicit draws and per-element styling
# ---------------------------------------------------------------------------

def _tri_dsl(**ann_kwargs):
    """Helper: 3-4-5 right triangle DSL with custom annotation kwargs."""
    from recipe.dsl import DrawObj
    ann = DSLAnnotations(**ann_kwargs)
    return RecipeDSL(
        construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"side_AB": 3, "side_BC": 4, "side_CA": 5}},
        ],
        annotations=ann,
    )


def test_explicit_draw_with_style_string():
    """draws list with a style string produces a styled Draw render op."""
    from recipe.dsl import DrawObj
    dsl = _tri_dsl(
        auto_draw_all=False,
        auto_label_points=False,
        draws=[DrawObj(obj="T", style="red")],
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    assert len(draw_ops) == 1
    assert draw_ops[0].obj == "T"
    assert draw_ops[0].style == "red"


def test_explicit_draw_with_inline_style_dict():
    """Inline style dict is registered in DiagramIR.styles and referenced by auto-key."""
    from recipe.dsl import DrawObj
    dsl = _tri_dsl(
        auto_draw_all=False,
        auto_label_points=False,
        draws=[DrawObj(obj="T", style={"color": "red", "thick": True})],
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    assert len(draw_ops) == 1
    style_key = draw_ops[0].style
    assert style_key is not None
    assert style_key in ir.styles
    assert ir.styles[style_key]["color"] == "red"
    assert ir.styles[style_key]["thick"] is True


def test_explicit_draw_vertex_pair_shorthand():
    """draws with endpoints auto-creates a segment def and draws it styled."""
    from recipe.dsl import DrawObj
    dsl = _tri_dsl(
        auto_draw_all=False,
        auto_label_points=False,
        draws=[DrawObj(endpoints=["A", "C"], style="blue")],
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    assert len(draw_ops) == 1
    seg_id = draw_ops[0].obj
    seg_def = next((d for d in ir.define if d.id == seg_id), None)
    assert seg_def is not None
    assert seg_def.kind == "segment"
    assert {seg_def.a, seg_def.b} == {"A", "C"}
    assert draw_ops[0].style == "blue"


def test_empty_draws_with_auto_draw_all_false_warns():
    """auto_draw_all=false with no explicit draws emits a UserWarning."""
    import warnings
    dsl = _tri_dsl(auto_draw_all=False, auto_label_points=False)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        lower_to_ir(dsl)
    assert len(w) == 1
    assert issubclass(w[0].category, UserWarning)
    assert "nothing will be drawn" in str(w[0].message).lower()


def test_named_styles_forwarded_to_ir_styles():
    """annotations.styles are forwarded into DiagramIR.styles."""
    from recipe.dsl import DrawObj
    dsl = RecipeDSL(
        construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"side_AB": 3, "side_BC": 4, "side_CA": 5}},
        ],
        annotations=DSLAnnotations(
            auto_draw_all=False,
            auto_label_points=False,
            styles={"highlight": {"color": "red", "thick": True}},
            draws=[DrawObj(obj="T", style="highlight")],
        ),
    )
    ir = lower_to_ir(dsl)
    assert "highlight" in ir.styles
    assert ir.styles["highlight"]["color"] == "red"
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    assert len(draw_ops) == 1
    assert draw_ops[0].style == "highlight"


def test_vertex_pair_shorthand_reuses_existing_segment():
    """If a segment [A,B] already exists in construction, draws reuses it."""
    from recipe.dsl import DrawObj
    dsl = RecipeDSL(
        construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"side_AB": 3, "side_BC": 4, "side_CA": 5}},
            {"op": "segment", "id": "s_AB", "endpoints": ["A", "B"]},
        ],
        annotations=DSLAnnotations(
            auto_draw_all=False,
            auto_label_points=False,
            draws=[DrawObj(endpoints=["A", "B"], style="green")],
        ),
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    assert len(draw_ops) == 1
    assert draw_ops[0].obj == "s_AB"  # reuses existing, not __mark_seg_A_B


def test_auto_draw_all_with_explicit_draw_deduplicates():
    """When auto_draw_all=true, objects in explicit draws are not auto-drawn."""
    from recipe.dsl import DrawObj
    dsl = RecipeDSL(
        construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"side_AB": 3, "side_BC": 4, "side_CA": 5}},
        ],
        annotations=DSLAnnotations(
            auto_draw_all=True,
            auto_label_points=False,
            draws=[DrawObj(obj="T", style="red")],
        ),
    )
    ir = lower_to_ir(dsl)
    draw_ops = [r for r in ir.render if r.kind == "draw"]
    # T should appear exactly once (from explicit draws, not auto-draw)
    t_draws = [r for r in draw_ops if r.obj == "T"]
    assert len(t_draws) == 1
    assert t_draws[0].style == "red"


# ---------------------------------------------------------------------------
# Annotation validation checks
# ---------------------------------------------------------------------------

def test_mark_right_angle_emits_check():
    """MarkRightAngle on explicit vertices emits a RightAngle check with source."""
    from ir.ir import RightAngle
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"right_angle_at": "C"}},
    ], annotations={"marks": [{"kind": "mark_right_angle", "a": "A", "vertex": "C", "b": "B"}]})
    ir = lower_to_ir(dsl)
    ra_checks = [c for c in ir.checks if c.kind == "right_angle"]
    # One from triangle spec, one from annotation
    annotation_checks = [c for c in ra_checks if c.source and c.source.startswith("annotation: ")]
    assert len(annotation_checks) == 1
    assert annotation_checks[0].angle.o == "C"
    assert annotation_checks[0].source.startswith("annotation: ")


def test_mark_angle_group_emits_angle_equal_checks():
    """Two MarkAngles with the same group emit one AngleEqual check with source."""
    from ir.ir import AngleEqual
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 3]},
        {"op": "point", "id": "D", "coords": [1, 0]},
        {"op": "point", "id": "E", "coords": [4, 0]},
        {"op": "point", "id": "F", "coords": [1, 3]},
    ], annotations={"marks": [
        {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "group": 1},
        {"kind": "mark_angle", "a": "E", "vertex": "D", "b": "F", "group": 1},
    ]})
    ir = lower_to_ir(dsl)
    ae_checks = [c for c in ir.checks if c.kind == "angle_equal"]
    assert len(ae_checks) == 1
    assert ae_checks[0].source.startswith("annotation: ")


def test_mark_angle_group_three_emits_pairwise():
    """Three MarkAngles with group=1 emit three pairwise AngleEqual checks."""
    from ir.ir import AngleEqual
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [1, 0]},
        {"op": "point", "id": "C", "coords": [0, 1]},
        {"op": "point", "id": "D", "coords": [2, 0]},
        {"op": "point", "id": "E", "coords": [3, 0]},
        {"op": "point", "id": "F", "coords": [2, 1]},
        {"op": "point", "id": "G", "coords": [4, 0]},
        {"op": "point", "id": "H", "coords": [5, 0]},
        {"op": "point", "id": "I", "coords": [4, 1]},
    ], annotations={"marks": [
        {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "group": 1},
        {"kind": "mark_angle", "a": "E", "vertex": "D", "b": "F", "group": 1},
        {"kind": "mark_angle", "a": "H", "vertex": "G", "b": "I", "group": 1},
    ]})
    ir = lower_to_ir(dsl)
    ae_checks = [c for c in ir.checks if c.kind == "angle_equal"]
    assert len(ae_checks) == 3


def test_mark_equal_lengths_emits_check():
    """MarkEqualLengths on 2 segments emits an EqualLength check with source."""
    from ir.ir import EqualLength
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 3]},
        {"op": "point", "id": "D", "coords": [3, 3]},
    ], annotations={"marks": [
        {"kind": "mark_equal_lengths", "segments": [["A", "B"], ["C", "D"]], "group": 1},
    ]})
    ir = lower_to_ir(dsl)
    el_checks = [c for c in ir.checks if c.kind == "equal_length"]
    assert len(el_checks) == 1
    assert el_checks[0].source.startswith("annotation: ")
    assert len(el_checks[0].segs) == 2


def test_mark_parallel_emits_check():
    """MarkParallel on 2 segments emits one Parallel check with source."""
    from ir.ir import Parallel
    dsl = RecipeDSL(construction=[
        {"op": "point", "id": "A", "coords": [0, 0]},
        {"op": "point", "id": "B", "coords": [3, 0]},
        {"op": "point", "id": "C", "coords": [0, 2]},
        {"op": "point", "id": "D", "coords": [3, 2]},
    ], annotations={"marks": [
        {"kind": "mark_parallel", "segments": [["A", "B"], ["C", "D"]], "group": 1},
    ]})
    ir = lower_to_ir(dsl)
    par_checks = [c for c in ir.checks if c.kind == "parallel"]
    assert len(par_checks) == 1
    assert par_checks[0].source.startswith("annotation: ")


def test_mark_angle_at_of_shorthand():
    """mark_angle with at/of shorthand produces correct AnglePoints."""
    from ir.ir import MarkAngles
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
    ], annotations={"marks": [
        {"kind": "mark_angle", "at": "A", "of": "T", "group": 1},
    ]})
    ir = lower_to_ir(dsl)
    mark_ops = [r for r in ir.render if r.kind == "mark_angles"]
    assert len(mark_ops) == 1
    angle = mark_ops[0].angles[0]
    assert angle.o == "A"
    assert set([angle.a, angle.b]) == {"B", "C"}


def test_mark_right_angle_at_of_shorthand():
    """mark_right_angle with at/of shorthand produces correct AnglePoints."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"right_angle_at": "C"}},
    ], annotations={"marks": [
        {"kind": "mark_right_angle", "at": "C", "of": "T"},
    ]})
    ir = lower_to_ir(dsl)
    mark_ops = [r for r in ir.render if r.kind == "mark_right_angles"]
    # one from auto_mark_right_angles is off; just the explicit annotation
    annotation_marks = [r for r in mark_ops]
    assert any(r.angles[0].o == "C" for r in annotation_marks)
    # RightAngle check should reference C
    ra_checks = [c for c in ir.checks if c.kind == "right_angle" and
                 c.source and c.source.startswith("annotation: ")]
    assert len(ra_checks) == 1
    assert ra_checks[0].angle.o == "C"


def test_mark_angle_at_of_unknown_triangle():
    """mark_angle with of= pointing to nonexistent triangle raises LoweringError."""
    with pytest.raises(LoweringError, match="nonexistent"):
        lower_to_ir(RecipeDSL(construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        ], annotations={"marks": [
            {"kind": "mark_angle", "at": "A", "of": "nonexistent"},
        ]}))


def test_mark_angle_at_of_vertex_not_in_triangle():
    """mark_angle with at= pointing to a vertex not in the triangle raises LoweringError."""
    with pytest.raises(LoweringError, match="Z"):
        lower_to_ir(RecipeDSL(construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        ], annotations={"marks": [
            {"kind": "mark_angle", "at": "Z", "of": "T"},
        ]}))


def test_mark_angle_both_forms_rejected():
    """Providing both (a,vertex,b) and (at,of) should raise a pydantic ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RecipeDSL(construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        ], annotations={"marks": [
            {"kind": "mark_angle", "a": "A", "vertex": "B", "b": "C", "at": "A", "of": "T"},
        ]})


def test_mark_angle_neither_form_rejected():
    """Providing neither (a,vertex,b) nor (at,of) should raise a pydantic ValidationError."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RecipeDSL(construction=[], annotations={"marks": [
            {"kind": "mark_angle"},
        ]})


def test_mark_angle_expected_numeric_pass():
    """mark_angle with expected=60 on a 60-degree angle raises no error."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
    ], annotations={"marks": [
        {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "expected": 60},
    ]})
    ir = lower_to_ir(dsl)  # should not raise
    assert ir is not None


def test_mark_angle_expected_numeric_fail():
    """mark_angle with expected value far from actual angle raises LoweringError with both values."""
    with pytest.raises(LoweringError, match="120"):
        lower_to_ir(RecipeDSL(construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        ], annotations={"marks": [
            {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "expected": 120},
        ]}))


def test_mark_angle_expected_category_pass():
    """mark_angle with expected='acute' on an acute angle raises no error."""
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
    ], annotations={"marks": [
        {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "expected": "acute"},
    ]})
    ir = lower_to_ir(dsl)  # should not raise
    assert ir is not None


def test_mark_angle_expected_category_fail():
    """mark_angle with expected='obtuse' on an acute angle raises LoweringError."""
    with pytest.raises(LoweringError, match="obtuse"):
        lower_to_ir(RecipeDSL(construction=[
            {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
             "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        ], annotations={"marks": [
            {"kind": "mark_angle", "a": "B", "vertex": "A", "b": "C", "expected": "obtuse"},
        ]}))


def test_mark_angle_expected_skips_without_coords():
    """mark_angle expected check silently skips if a vertex has no known coords."""
    # IntersectionOp produces a point with no _coord_floats entry
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"angle_A": 60, "angle_B": 60, "side_AB": 3}},
        {"op": "line_through", "id": "l1", "points": ["A", "B"]},
        {"op": "line_through", "id": "l2", "points": ["A", "C"]},
        {"op": "intersection", "id": "X", "of": ["l1", "l2"]},
    ], annotations={"marks": [
        {"kind": "mark_angle", "a": "A", "vertex": "X", "b": "C", "expected": 45},
    ]})
    ir = lower_to_ir(dsl)  # should not raise
    assert ir is not None


def test_annotation_check_source_in_message():
    """Mismatched MarkRightAngle annotation → failure message contains [annotation: mark_right_angle."""
    from ir.to_sympy import compile_defs
    from ir.checks import run_checks

    # 3-4-5 right triangle, right angle at C; mark a non-right angle at A
    dsl = RecipeDSL(construction=[
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"side_AB": 3, "side_BC": 4, "side_CA": 5}},
    ], annotations={"marks": [
        {"kind": "mark_right_angle", "a": "B", "vertex": "A", "b": "C"},
    ]})
    ir = lower_to_ir(dsl)
    sym = compile_defs(ir)
    results = run_checks(ir.checks, sym)
    failed = [r for r in results if not r.passed]
    assert any("annotation: mark_right_angle" in r.message for r in failed)
