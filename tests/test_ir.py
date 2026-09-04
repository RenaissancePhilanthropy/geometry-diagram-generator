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
