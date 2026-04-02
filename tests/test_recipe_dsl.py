# tests/test_recipe_dsl.py
import pytest
from pydantic import ValidationError
from recipe.dsl import (
    RecipeDSL, DSLAnnotations,
    MarkAngle, MarkRightAngle, MarkEqualLengths, MarkParallel, LabelSegment,
    # Foundation ops
    TriangleOp, CircleOp, PolygonOp, PointOp, PointExternalOp, CanvasOp,
    RegularPolygonOp,
    # Derived ops
    MidpointOp, IntersectionOp, PerpendicularOp, ParallelOp,
    LineThroughOp, SegmentOp, RayOp, ReflectionOp, RotationOp,
    PointOnSegmentOp, TangentLineOp, PointAlongOp, ExtendSegmentOp,
    PointFootOp, CircleThrough3Op,
    # Composite ops
    AltitudeOp, CircumcircleOp, IncircleOp, PerpendicularBisectorOp,
    AngleBisectorOp, CentroidOp, PolygonExteriorOp, MedianOp,
)


# ---- Foundation ops ----

def test_triangle_op_angles():
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"angle_A": 60, "angle_B": 70})
    assert op.op == "triangle"
    assert op.spec["angle_A"] == 60

def test_triangle_op_sides():
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"side_AB": 3, "side_BC": 4, "side_CA": 5})
    assert op.spec["side_AB"] == 3

def test_triangle_op_right_angle():
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"right_angle_at": "B", "side_AB": 3, "side_BC": 4})
    assert op.spec["right_angle_at"] == "B"

def test_circle_op_radius():
    op = CircleOp(id="c", center="O", radius=5)
    assert op.op == "circle"
    assert op.radius == 5

def test_circle_op_through():
    op = CircleOp(id="c", center="O", through="A")
    assert op.through == "A"

def test_circle_op_requires_radius_or_through():
    with pytest.raises(ValidationError):
        CircleOp(id="c", center="O")  # neither radius nor through

def test_polygon_op():
    op = PolygonOp(id="P", vertices=["A","B","C","D"])
    assert op.op == "polygon"

def test_point_op():
    op = PointOp(id="X", coords=[1.5, 2.0])
    assert op.op == "point"
    assert op.coords[0] == 1.5

def test_point_external_op():
    op = PointExternalOp(id="E", relative_to="c", direction="right", distance_ratio=1.5)
    assert op.op == "point_external"

def test_canvas_op():
    op = CanvasOp(id="_canvas", x_range=[-2, 8], y_range=[-2, 8])
    assert op.op == "canvas"


# ---- Derived ops ----

def test_midpoint_op():
    op = MidpointOp(id="M", of=["A", "B"])
    assert op.op == "midpoint"

def test_intersection_op():
    op = IntersectionOp(id="P", of=["line1", "circ1"], selector={"kind": "upper_of_line", "a": "A", "b": "B"})
    assert op.op == "intersection"

def test_perpendicular_op_line_id():
    op = PerpendicularOp(id="perp", to_line="L", through="P")
    assert op.op == "perpendicular"
    assert op.to_line == "L"

def test_perpendicular_op_point_pair():
    op = PerpendicularOp(id="perp", to_line=["A", "B"], through="P")
    assert op.to_line == ["A", "B"]

def test_segment_op():
    op = SegmentOp(id="s", endpoints=["A", "B"])
    assert op.op == "segment"

def test_rotation_op_degrees():
    op = RotationOp(id="R", point="A", center="O", angle=90)
    assert op.op == "rotation"
    assert op.angle == 90


# ---- Composite ops ----

def test_altitude_op_to_side():
    op = AltitudeOp(id="alt_A", from_vertex="A", to_side=["B","C"], foot="H")
    assert op.op == "altitude"
    assert op.foot == "H"

def test_altitude_op_triangle():
    op = AltitudeOp(id="alt_A", from_vertex="A", triangle="T", foot="H")
    assert op.triangle == "T"
    assert op.to_side is None

def test_altitude_op_requires_one_of():
    with pytest.raises(ValidationError):
        AltitudeOp(id="alt_A", from_vertex="A", foot="H")  # neither triangle nor to_side

def test_altitude_op_rejects_both():
    with pytest.raises(ValidationError):
        AltitudeOp(id="alt_A", from_vertex="A", triangle="T", to_side=["B","C"], foot="H")

def test_circumcircle_op():
    op = CircumcircleOp(id="cc", of="T", center="O")
    assert op.op == "circumcircle"

def test_incircle_op():
    op = IncircleOp(id="ic", of="T", center="I")
    assert op.op == "incircle"

def test_perpendicular_bisector_op():
    op = PerpendicularBisectorOp(id="pb", of=["A","B"], mid="M")
    assert op.op == "perpendicular_bisector"

def test_angle_bisector_op():
    op = AngleBisectorOp(id="ab", vertex="B", ray1_toward="A", ray2_toward="C")
    assert op.op == "angle_bisector"

def test_centroid_op():
    op = CentroidOp(id="G", of="T")
    assert op.op == "centroid"

def test_polygon_exterior_op():
    op = PolygonExteriorOp(id="sq", base=["A","B"], ref_point="C", n=4,
                           vertices=["sq_v2","sq_v3"])
    assert op.op == "polygon_exterior"

def test_median_op_to_side():
    op = MedianOp(id="med", from_vertex="A", to_side=["B","C"], mid="M_BC")
    assert op.op == "median"

def test_median_op_triangle():
    op = MedianOp(id="med", from_vertex="A", triangle="T", mid="M_BC")
    assert op.triangle == "T"

def test_median_op_requires_one_of():
    with pytest.raises(ValidationError):
        MedianOp(id="med", from_vertex="A", mid="M_BC")  # neither triangle nor to_side

def test_median_op_rejects_both():
    with pytest.raises(ValidationError):
        MedianOp(id="med", from_vertex="A", triangle="T", to_side=["B","C"], mid="M_BC")

def test_regular_polygon_op():
    op = RegularPolygonOp(id="hex", center="O", radius=3, start_angle=0,
                          vertices=["H0","H1","H2","H3","H4","H5"])
    assert op.op == "regular_polygon"
    assert len(op.vertices) == 6

def test_regular_polygon_star_valid():
    op = RegularPolygonOp(id="star", center="O", radius=3, start_angle=90,
                          vertices=["A","B","C","D","E"], star=True)
    assert op.star is True

def test_regular_polygon_star_rejects_even_n():
    with pytest.raises(ValidationError):
        RegularPolygonOp(id="star", center="O", radius=3,
                         vertices=["A","B","C","D","E","F"], star=True)

def test_regular_polygon_star_rejects_small_n():
    with pytest.raises(ValidationError):
        RegularPolygonOp(id="star", center="O", radius=3,
                         vertices=["A","B","C"], star=True)

def test_point_along_op():
    op = PointAlongOp(**{"op": "point_along", "id": "D", "from": "A", "on": "line1",
                         "distance": 2, "toward": "B"})
    assert op.op == "point_along"
    assert op.from_ == "A"
    assert op.toward == "B"

def test_extend_segment_op():
    op = ExtendSegmentOp(id="E", segment=["A","B"], beyond="B", by=1.5)
    assert op.op == "extend_segment"
    assert op.beyond == "B"


# ---- Annotations ----

def test_annotations_defaults():
    ann = DSLAnnotations()
    assert ann.auto_draw_all is True
    assert ann.auto_label_points is True
    assert ann.auto_mark_right_angles is False

def test_annotations_explicit_marks():
    ann = DSLAnnotations(
        marks=[{"kind": "mark_right_angle", "a": "H", "vertex": "A", "b": "B"}]
    )
    assert len(ann.marks) == 1
    assert isinstance(ann.marks[0], MarkRightAngle)

def test_annotations_equal_lengths():
    ann = DSLAnnotations(
        marks=[{"kind": "mark_equal_lengths", "segments": [["A","B"],["C","D"]]}]
    )
    assert isinstance(ann.marks[0], MarkEqualLengths)

def test_annotations_invalid_mark_rejected():
    with pytest.raises(ValidationError):
        DSLAnnotations(marks=[{"kind": "not_a_real_mark", "x": 1}])

def test_tangent_line_op_from_point():
    op = TangentLineOp(id="t", circle="c", from_point="P")
    assert op.from_point == "P"
    assert op.at is None

def test_tangent_line_op_at():
    op = TangentLineOp(id="t", circle="c", at="Q")
    assert op.at == "Q"

def test_tangent_line_op_requires_exactly_one():
    with pytest.raises(ValidationError):
        TangentLineOp(id="t", circle="c")  # neither
    with pytest.raises(ValidationError):
        TangentLineOp(id="t", circle="c", at="Q", from_point="P")  # both

def test_point_foot_op():
    op = PointFootOp(id="F", source="P", onto="L")
    assert op.op == "point_foot"
    assert op.source == "P"
    assert op.onto == "L"

def test_circle_through_3_op():
    op = CircleThrough3Op(id="cc", through=["A","B","C"], center="O")
    assert op.op == "circle_through_3"
    assert len(op.through) == 3


# ---- RecipeDSL top-level ----

def test_recipe_dsl_minimal():
    dsl = RecipeDSL(
        mode="abstract",
        construction=[
            {"op": "triangle", "id": "T", "vertices": ["A","B","C"],
             "spec": {"angle_A": 60, "angle_B": 70}},
        ]
    )
    assert dsl.mode == "abstract"
    assert len(dsl.construction) == 1

def test_recipe_dsl_reserved_id_rejected():
    """IDs starting with __ are reserved for lowering intermediates."""
    with pytest.raises(ValidationError):
        RecipeDSL(
            mode="abstract",
            construction=[{"op": "point", "id": "__bad", "coords": [0, 0]}]
        )

def test_dsl_op_visible_default():
    op = PointOp(id="X", coords=[1, 2])
    assert op.visible is True

def test_dsl_op_visible_false():
    op = LineThroughOp(id="aux", points=["A","B"], visible=False)
    assert op.visible is False

def test_recipe_dsl_mode_enum():
    with pytest.raises(ValidationError):
        RecipeDSL(mode="invalid", construction=[])

def test_dsl_op_base_rejects_reserved_id():
    """DSLOpBase field_validator rejects __ prefix even when constructing ops directly."""
    with pytest.raises(ValidationError):
        PointOp(id="__hidden", coords=[0, 0])

def test_ray_op():
    op = RayOp(**{"op": "ray", "id": "r", "from": "A", "through": "B"})
    assert op.op == "ray"
    assert op.from_ == "A"
    assert op.through == "B"

def test_parallel_op():
    op = ParallelOp(id="par", to_line="L", through="P")
    assert op.op == "parallel"

def test_reflection_op():
    op = ReflectionOp(id="R", point="A", over="L")
    assert op.op == "reflection"

def test_point_on_segment_op():
    op = PointOnSegmentOp(id="D", segment=["A","B"], ratio=0.5)
    assert op.op == "point_on_segment"
    assert op.ratio == 0.5
