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
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"angle_A": 60, "angle_B": 70, "side_AB": 3})
    assert op.op == "triangle"
    assert op.spec.angle_A == 60

def test_triangle_op_sides():
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"side_AB": 3, "side_BC": 4, "side_CA": 5})
    assert op.spec.side_AB == 3

def test_triangle_op_right_angle():
    op = TriangleOp(id="T", vertices=["A","B","C"], spec={"right_angle_at": "B", "side_AB": 3, "side_BC": 4})
    assert op.spec.right_angle_at == "B"


# --- TriangleSpec model ---

def test_triangle_spec_sss():
    op = TriangleOp(id="T", vertices=["A","B","C"],
                    spec={"side_AB": 3, "side_BC": 4, "side_CA": 5})
    from recipe.dsl import TriangleSpec
    assert isinstance(op.spec, TriangleSpec)
    assert op.spec.side_AB == 3.0

def test_triangle_spec_sas():
    op = TriangleOp(id="T", vertices=["A","B","C"],
                    spec={"side_AB": 4, "angle_B": 60, "side_BC": 3})
    assert op.spec.angle_B == 60.0

def test_triangle_spec_right_at():
    op = TriangleOp(id="T", vertices=["A","B","C"],
                    spec={"right_angle_at": "B", "side_AB": 3, "side_BC": 4})
    assert op.spec.right_angle_at == "B"

def test_triangle_spec_underdetermined_raises():
    """2 constraints (no right_angle_at) should fail."""
    with pytest.raises(ValidationError):
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"side_AB": 3, "side_BC": 4})

def test_triangle_spec_aaa_raises():
    """Three angles, no side — AAA is underdetermined."""
    with pytest.raises(ValidationError):
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"angle_A": 60, "angle_B": 60, "angle_C": 60})

def test_triangle_spec_right_at_needs_two_constraints():
    """right_angle_at alone is underdetermined (needs 2 more)."""
    with pytest.raises(ValidationError):
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"right_angle_at": "B"})

def test_triangle_spec_extra_key_raises():
    """extra='forbid' means unknown keys raise at parse time."""
    with pytest.raises(ValidationError):
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"side_AB": 3, "side_BC": 4, "side_CA": 5, "oops": 1})

def test_triangle_spec_right_angle_at_invalid_slot_raises():
    """right_angle_at must be A, B, or C."""
    with pytest.raises(ValidationError):
        TriangleOp(id="T", vertices=["A","B","C"],
                   spec={"right_angle_at": "D", "side_AB": 3, "side_BC": 4})

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

def test_point_external_direction_cardinal():
    op = PointExternalOp(id="E", relative_to="c", direction="right", distance_ratio=1.5)
    assert op.direction == "right"

def test_point_external_direction_float():
    op = PointExternalOp(id="E", relative_to="c", direction=45.0, distance_ratio=1.5)
    assert op.direction == 45.0

def test_point_external_direction_string_coerced_to_float():
    """Pydantic v2 coerces '45' → 45.0 for Union[Literal[...], float]."""
    op = PointExternalOp(id="E", relative_to="c", direction="45", distance_ratio=1.5)
    assert op.direction == 45.0

def test_point_external_direction_invalid_string_raises():
    with pytest.raises(ValidationError):
        PointExternalOp(id="E", relative_to="c", direction="diagonal", distance_ratio=1.5)

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


# --- CircumcircleOp / IncircleOp ---

def test_circumcircle_of_triangle():
    """Existing form still works."""
    op = CircumcircleOp(id="cc", of="T", center="O")
    assert op.of == "T"
    assert op.points is None

def test_circumcircle_of_points():
    op = CircumcircleOp(id="cc", points=["A", "B", "C"], center="O")
    assert op.points == ["A", "B", "C"]
    assert op.of is None

def test_circumcircle_neither_raises():
    with pytest.raises(ValidationError):
        CircumcircleOp(id="cc", center="O")  # neither of nor points

def test_circumcircle_both_raises():
    with pytest.raises(ValidationError):
        CircumcircleOp(id="cc", of="T", points=["A", "B", "C"], center="O")

def test_circumcircle_wrong_point_count_raises():
    with pytest.raises(ValidationError):
        CircumcircleOp(id="cc", points=["A", "B"], center="O")  # needs exactly 3

def test_incircle_of_triangle():
    op = IncircleOp(id="ic", of="T", center="I")
    assert op.of == "T"

def test_incircle_of_points():
    op = IncircleOp(id="ic", points=["A", "B", "C"], center="I")
    assert op.points == ["A", "B", "C"]

def test_incircle_neither_raises():
    with pytest.raises(ValidationError):
        IncircleOp(id="ic", center="I")

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
             "spec": {"angle_A": 60, "angle_B": 70, "side_AB": 3}},
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


def test_arc_op_reflex_parses():
    from recipe.dsl import ArcOp
    dsl = RecipeDSL(
        mode="grid",
        construction=[
            {"op": "arc", "id": "a", "center": "O", "start": "A", "end": "B", "reflex": True}
        ],
    )
    arc_op = dsl.construction[0]
    assert isinstance(arc_op, ArcOp)
    assert arc_op.reflex is True


def test_arc_op_reflex_default_false():
    from recipe.dsl import ArcOp
    op = ArcOp(id="a", center="O", start="A", end="B")
    assert op.reflex is False


# ---- PolygonFromSidesOp ----

def test_polygon_from_sides_op_parses():
    from recipe.dsl import PolygonFromSidesOp
    op = PolygonFromSidesOp(id="pent", vertices=["A","B","C","D","E"],
                            side_lengths=[5, 7, 8, 6, 4])
    assert op.op == "polygon_from_sides"
    assert op.vertices == ["A","B","C","D","E"]
    assert op.side_lengths == [5, 7, 8, 6, 4]
    assert op.center is None


def test_polygon_from_sides_op_mismatched_lengths():
    from recipe.dsl import PolygonFromSidesOp
    with pytest.raises(ValidationError):
        PolygonFromSidesOp(id="quad", vertices=["A","B","C","D"],
                           side_lengths=[3, 4, 5])


def test_polygon_from_sides_op_too_few_vertices():
    from recipe.dsl import PolygonFromSidesOp
    with pytest.raises(ValidationError):
        PolygonFromSidesOp(id="seg", vertices=["A","B"],
                           side_lengths=[3, 4])


# ---- Selector → PickRule ----

def test_intersection_selector_accepts_pick_rule_dict():
    """Dict coerced to PickRule at parse time."""
    op = IntersectionOp(
        id="P", of=["L1", "C1"],
        selector={"kind": "upper_of_line", "a": "A", "b": "B"},
    )
    from ir.ir import PickUpperOfLine
    assert isinstance(op.selector, PickUpperOfLine)

def test_intersection_selector_accepts_none():
    op = IntersectionOp(id="P", of=["L1", "C1"])
    assert op.selector is None

def test_intersection_selector_rejects_invalid_kind():
    """Invalid kind raises ValidationError at parse time, not lowering time."""
    with pytest.raises(ValidationError):
        IntersectionOp(
            id="P", of=["L1", "C1"],
            selector={"kind": "not_a_real_kind"},
        )

def test_tangent_line_selector_accepts_pick_rule_dict():
    op = TangentLineOp(
        id="T", circle="C", from_point="P",
        selector={"kind": "closest_to", "p": "Q"},
    )
    from ir.ir import PickClosestTo
    assert isinstance(op.selector, PickClosestTo)

def test_tangent_line_selector_rejects_invalid():
    with pytest.raises(ValidationError):
        TangentLineOp(
            id="T", circle="C", from_point="P",
            selector={"kind": "bogus"},
        )


# ---- Label pos field ----

def test_label_segment_has_pos_field_defaulting_to_auto():
    from recipe.dsl import LabelSegment
    lbl = LabelSegment(kind="label_segment", endpoints=["A", "B"], text="4")
    assert lbl.pos == "auto"

def test_label_segment_pos_above():
    from recipe.dsl import LabelSegment
    lbl = LabelSegment(kind="label_segment", endpoints=["A", "B"], text="4", pos="above")
    assert lbl.pos == "above"

def test_label_segment_pos_invalid_raises():
    from recipe.dsl import LabelSegment
    with pytest.raises(ValidationError):
        LabelSegment(kind="label_segment", endpoints=["A", "B"], text="4", pos="diagonal")

def test_label_angle_has_pos_field_defaulting_to_auto():
    from recipe.dsl import LabelAngle
    lbl = LabelAngle(kind="label_angle", a="A", vertex="B", b="C", text="60°")
    assert lbl.pos == "auto"


# --- RectangleSpec model ---

def test_rectangle_spec_two_adjacent_sides():
    from recipe.dsl import RectangleOp, RectangleSpec
    op = RectangleOp(id="R", vertices=["A","B","C","D"],
                     spec={"side_AB": 4, "side_BC": 3})
    assert isinstance(op.spec, RectangleSpec)
    assert op.spec.side_AB == 4.0
    assert op.spec.side_BC == 3.0

def test_rectangle_spec_with_rotation():
    from recipe.dsl import RectangleOp
    op = RectangleOp(id="R", vertices=["A","B","C","D"],
                     spec={"side_AB": 4, "side_BC": 3, "rotation": 30.0})
    assert op.spec.rotation == 30.0

def test_rectangle_spec_opposite_sides_raises():
    """side_AB + side_CD are opposite, not adjacent — should fail."""
    from recipe.dsl import RectangleOp
    with pytest.raises(ValidationError):
        RectangleOp(id="R", vertices=["A","B","C","D"],
                    spec={"side_AB": 4, "side_CD": 4})

def test_rectangle_spec_only_one_side_raises():
    from recipe.dsl import RectangleOp
    with pytest.raises(ValidationError):
        RectangleOp(id="R", vertices=["A","B","C","D"],
                    spec={"side_AB": 4})

def test_rectangle_spec_extra_key_raises():
    from recipe.dsl import RectangleOp
    with pytest.raises(ValidationError):
        RectangleOp(id="R", vertices=["A","B","C","D"],
                    spec={"side_AB": 4, "side_BC": 3, "oops": 1})


# --- DSLCheck union ---

def test_dsl_check_distance():
    from recipe.dsl import CheckDistance
    c = CheckDistance(points=["A", "B"], expected=5.0)
    assert c.check == "distance"

def test_dsl_check_parallel():
    from recipe.dsl import CheckParallel
    c = CheckParallel(seg1=["A", "B"], seg2=["C", "D"])
    assert c.check == "parallel"

def test_recipe_dsl_checks_field_accepts_typed_checks():
    from recipe.dsl import CheckDistance, CheckPerpendicular
    r = RecipeDSL(
        construction=[PointOp(id="A", coords=[0, 0]), PointOp(id="B", coords=[3, 0])],
        checks=[
            {"check": "distance", "points": ["A", "B"], "expected": 3.0},
            {"check": "perpendicular", "seg1": ["A", "B"], "seg2": ["B", "C"]},
        ],
    )
    assert len(r.checks) == 2
    assert isinstance(r.checks[0], CheckDistance)

def test_recipe_dsl_checks_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        RecipeDSL(
            construction=[PointOp(id="A", coords=[0, 0])],
            checks=[{"check": "nonexistent_kind", "foo": "bar"}],
        )
