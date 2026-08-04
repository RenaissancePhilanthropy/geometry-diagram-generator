"""Tests for the draw() and draw_points() pydsl ops."""
import pytest

from geometry_diagrams.pydsl.api import draw, draw_points, point, triangle
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.ir.ir import Draw, DrawPoints


def test_draw_appends_draw_op_referencing_the_object_id():
    with new_builder_context() as builder:
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        draw(t)
        ir = builder.build()
    draw_ops = [r for r in ir.render if isinstance(r, Draw)]
    assert len(draw_ops) == 1
    assert draw_ops[0].obj == t.id


def test_draw_points_appends_draw_points_op_with_all_ids():
    with new_builder_context() as builder:
        a, b = point(0, 0), point(1, 0)
        draw_points(a, b)
        ir = builder.build()
    draw_points_ops = [r for r in ir.render if isinstance(r, DrawPoints)]
    assert len(draw_points_ops) == 1
    assert draw_points_ops[0].points == [a.id, b.id]


def test_draw_rejects_a_point_handle():
    with new_builder_context():
        a = point(0, 0)
        with pytest.raises(ValueError, match="draw_points"):
            draw(a)


def test_draw_rejects_an_angle_ref():
    with new_builder_context():
        a, b, c = point(0, 0), point(1, 0), point(0, 1)
        t = triangle(a, b, c)
        ref = t.angle_at(b)
        with pytest.raises(ValueError, match="mark_angle"):
            draw(ref)
