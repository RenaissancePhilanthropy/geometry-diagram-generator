"""Tests for IR schema (geometry_diagrams/ir/ir.py)."""


def test_elliptical_arc_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalArcCenterStartEnd, DiagramIR

    stmt = EllipticalArcCenterStartEnd(
        id="ea1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=False,
    )
    assert stmt.kind == "elliptical_arc_center_start_end"
    assert stmt.hradius == 4 and stmt.vradius == 1


def test_elliptical_sector_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalSectorCenterStartEnd

    stmt = EllipticalSectorCenterStartEnd(
        id="es1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=True,
    )
    assert stmt.kind == "elliptical_sector_center_start_end"
    assert stmt.reflex is True


def test_polyline_open_round_trips():
    from geometry_diagrams.ir.ir import PolylineOpen

    stmt = PolylineOpen(id="pl1", points=["a", "b", "c"])
    assert stmt.kind == "polyline_open"
    assert stmt.points == ["a", "b", "c"]


def test_draw_brace_defaults_direction_up_and_no_label():
    from geometry_diagrams.ir.ir import DrawBrace

    op = DrawBrace(p1=[0.0, 0.0], p2=[4.0, 0.0])
    assert op.kind == "draw_brace"
    assert op.p1 == [0.0, 0.0]
    assert op.p2 == [4.0, 0.0]
    assert op.direction == "up"
    assert op.label is None


def test_draw_brace_accepts_all_four_directions():
    from geometry_diagrams.ir.ir import DrawBrace

    for direction in ("left", "right", "up", "down"):
        op = DrawBrace(p1=[0.0, 0.0], p2=[1.0, 1.0], direction=direction, label="x")
        assert op.direction == direction
        assert op.label == "x"


def test_draw_brace_rejects_invalid_direction():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import DrawBrace

    with pytest.raises(ValidationError):
        DrawBrace(p1=[0.0, 0.0], p2=[1.0, 0.0], direction="sideways")


def test_draw_brace_is_a_valid_render_op_member():
    """DrawBrace must round-trip through DiagramIR's discriminated RenderOp
    union (not just be constructible on its own) — this is what actually
    wires it into the render pipeline."""
    from geometry_diagrams.ir.ir import DiagramIR, DrawBrace, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[DrawBrace(p1=[0.0, 0.0], p2=[2.0, 0.0])],
    )
    assert isinstance(diagram.render[0], DrawBrace)
    # Round-trip through JSON, as the discriminated union requires "kind" to
    # be present and correct for reconstruction.
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.render[0], DrawBrace)


def test_mark_segments_ticks_defaults_to_none():
    from geometry_diagrams.ir.ir import MarkSegments

    op = MarkSegments(segs=["s1"])
    assert op.ticks is None


def test_mark_segments_accepts_ticks_beyond_the_mark_symbol_palette():
    from geometry_diagrams.ir.ir import MarkSegments

    op = MarkSegments(segs=["s1"], ticks=7)
    assert op.ticks == 7


def test_mark_segments_rejects_non_positive_ticks():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import MarkSegments

    with pytest.raises(ValidationError):
        MarkSegments(segs=["s1"], ticks=0)
    with pytest.raises(ValidationError):
        MarkSegments(segs=["s1"], ticks=-1)


def test_mark_arcs_defaults_to_no_group_and_no_ticks():
    from geometry_diagrams.ir.ir import MarkArcs

    op = MarkArcs(arcs=["a1"])
    assert op.group is None
    assert op.ticks is None


def test_mark_arcs_rejects_non_positive_ticks():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import MarkArcs

    with pytest.raises(ValidationError):
        MarkArcs(arcs=["a1"], ticks=0)
    with pytest.raises(ValidationError):
        MarkArcs(arcs=["a1"], ticks=-1)


def test_mark_arcs_is_a_valid_render_op_member():
    from geometry_diagrams.ir.ir import DiagramIR, MarkArcs, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[MarkArcs(arcs=["arc1"], ticks=2)],
    )
    assert isinstance(diagram.render[0], MarkArcs)
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.render[0], MarkArcs)


def test_label_along_arc_defaults_to_outside_midpoint_auto_flip():
    from geometry_diagrams.ir.ir import LabelAlongArc

    op = LabelAlongArc(arc="arc1", text="hi")
    assert op.side == "outside"
    assert op.pos == 0.5
    assert op.flip is None


def test_label_along_arc_accepts_the_closed_unit_interval():
    from geometry_diagrams.ir.ir import LabelAlongArc

    assert LabelAlongArc(arc="arc1", text="hi", pos=0.0).pos == 0.0
    assert LabelAlongArc(arc="arc1", text="hi", pos=1.0).pos == 1.0


def test_label_along_arc_rejects_pos_outside_the_unit_interval():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import LabelAlongArc

    with pytest.raises(ValidationError):
        LabelAlongArc(arc="arc1", text="hi", pos=-0.1)
    with pytest.raises(ValidationError):
        LabelAlongArc(arc="arc1", text="hi", pos=1.1)


def test_label_along_arc_is_a_valid_render_op_member():
    from geometry_diagrams.ir.ir import DiagramIR, LabelAlongArc, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[LabelAlongArc(arc="arc1", text="major arc")],
    )
    assert isinstance(diagram.render[0], LabelAlongArc)
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.render[0], LabelAlongArc)


# ---------------------------------------------------------------------------
# EqualRadius
# ---------------------------------------------------------------------------

def test_equal_radius_defaults():
    from geometry_diagrams.ir.ir import EqualRadius

    check = EqualRadius(circles=["c1", "c2"])
    assert check.kind == "equal_radius"
    assert check.level == "must"
    assert check.tol is None
    assert check.source is None


def test_equal_radius_rejects_fewer_than_two_circles():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import EqualRadius

    with pytest.raises(ValidationError):
        EqualRadius(circles=["c1"])
    with pytest.raises(ValidationError):
        EqualRadius(circles=[])


def test_equal_radius_is_a_valid_check_union_member():
    from geometry_diagrams.ir.ir import DiagramIR, EqualRadius, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        checks=[EqualRadius(circles=["c1", "c2"], source="test")],
    )
    assert isinstance(diagram.checks[0], EqualRadius)
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.checks[0], EqualRadius)
    assert rebuilt.checks[0].circles == ["c1", "c2"]


# ---------------------------------------------------------------------------
# RadiusEquals
# ---------------------------------------------------------------------------

def test_radius_equals_defaults():
    from geometry_diagrams.ir.ir import RadiusEquals

    check = RadiusEquals(circle="c1", expected=5.0)
    assert check.kind == "radius_equals"
    assert check.level == "must"
    assert check.tol is None
    assert check.expected == 5.0


def test_radius_equals_is_a_valid_check_union_member():
    from geometry_diagrams.ir.ir import DiagramIR, RadiusEquals, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        checks=[RadiusEquals(circle="c1", expected=3.5)],
    )
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.checks[0], RadiusEquals)
    assert rebuilt.checks[0].expected == 3.5


# ---------------------------------------------------------------------------
# CongruentArcs
# ---------------------------------------------------------------------------

def test_congruent_arcs_defaults():
    from geometry_diagrams.ir.ir import CongruentArcs

    check = CongruentArcs(arcs=["a1", "a2"])
    assert check.kind == "congruent_arcs"
    assert check.level == "must"
    assert check.tol is None


def test_congruent_arcs_rejects_fewer_than_two_arcs():
    import pytest
    from pydantic import ValidationError

    from geometry_diagrams.ir.ir import CongruentArcs

    with pytest.raises(ValidationError):
        CongruentArcs(arcs=["a1"])
    with pytest.raises(ValidationError):
        CongruentArcs(arcs=[])


def test_congruent_arcs_is_a_valid_check_union_member():
    from geometry_diagrams.ir.ir import DiagramIR, CongruentArcs, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        checks=[CongruentArcs(arcs=["a1", "a2"])],
    )
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.checks[0], CongruentArcs)
    assert rebuilt.checks[0].arcs == ["a1", "a2"]


# ---------------------------------------------------------------------------
# AngleValue
# ---------------------------------------------------------------------------

def test_angle_value_defaults():
    from geometry_diagrams.ir.ir import AngleValue, AnglePoints

    check = AngleValue(angle=AnglePoints(a="A", o="B", b="C"), expected_deg=90.0)
    assert check.kind == "angle_value"
    assert check.level == "must"
    assert check.expected_deg == 90.0


def test_angle_value_is_a_valid_check_union_member():
    from geometry_diagrams.ir.ir import DiagramIR, AngleValue, AnglePoints, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        checks=[AngleValue(angle=AnglePoints(a="A", o="B", b="C"), expected_deg=45.0)],
    )
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.checks[0], AngleValue)
    assert rebuilt.checks[0].expected_deg == 45.0


# ---------------------------------------------------------------------------
# CirclesTangent
# ---------------------------------------------------------------------------

def test_circles_tangent_defaults():
    from geometry_diagrams.ir.ir import CirclesTangent

    check = CirclesTangent(c1="c1", c2="c2")
    assert check.kind == "circles_tangent"
    assert check.level == "must"


def test_circles_tangent_is_a_valid_check_union_member():
    from geometry_diagrams.ir.ir import DiagramIR, CirclesTangent, PointFixed

    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        checks=[CirclesTangent(c1="c1", c2="c2", source="test")],
    )
    dumped = diagram.model_dump()
    rebuilt = DiagramIR.model_validate(dumped)
    assert isinstance(rebuilt.checks[0], CirclesTangent)
    assert rebuilt.checks[0].c1 == "c1"
    assert rebuilt.checks[0].c2 == "c2"
