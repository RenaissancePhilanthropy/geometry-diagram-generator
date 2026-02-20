"""
Tests for using Roger to generate SVGs from substances, and to validate substances without rendering.
"""

import pytest
from ir.models import Diagram, GeoObject, Constructor
from ir.substance import to_substance
from util.roger import render_svg


def test_render_valid_substance():
    substance = """
    Point A
    AutoLabel A
    """
    svg = render_svg(substance, "valid substance")
    assert "<svg" in svg and "</svg>" in svg
    assert "<circle" in svg  # point renders as a circle element


def test_unknown_type_raises_error():
    with pytest.raises(RuntimeError):
        render_svg("Foo X\nAutoLabel X")


def test_undeclared_object_raises_error():
    with pytest.raises(RuntimeError):
        render_svg("Parallel(L1, L2)")


def test_error_message_includes_substance_name():
    with pytest.raises(RuntimeError, match="my-diagram"):
        render_svg("Foo X", "my-diagram")


def test_render_segment():
    substance = "Point A, B\nSegment AB := Segment(A, B)\nAutoLabel A, B"
    svg = render_svg(substance)
    assert "<svg" in svg and "</svg>" in svg
    assert "<line" in svg    # segment renders as a line element
    assert "<circle" in svg  # point icons


def test_render_triangle():
    substance = "Point A, B, C\nTriangle T := Triangle(A, B, C)\nAutoLabel A, B, C"
    svg = render_svg(substance)
    assert "<svg" in svg and "</svg>" in svg
    assert "<line" in svg    # triangle sides (PQ, QR, RP) render as line elements
    assert "<circle" in svg  # point icons
    assert "<path" in svg    # triangle icon rendered as a closed path


def test_ir_pipeline():
    diagram = Diagram(
        objects=[
            GeoObject(type="Point", name="A"),
            GeoObject(type="Point", name="B"),
            GeoObject(type="Segment", name="AB", constructor=Constructor(name="Segment", args=["A", "B"])),
        ],
        auto_label=["A", "B"],
    )
    substance = to_substance(diagram)
    svg = render_svg(substance, "ir-pipeline")
    assert "<svg" in svg and "</svg>" in svg
    assert "<line" in svg    # segment renders as a line element
    assert "<circle" in svg  # point icons