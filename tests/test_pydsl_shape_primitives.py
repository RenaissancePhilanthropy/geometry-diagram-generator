# tests/test_pydsl_shape_primitives.py
"""Tests for pydsl's new shape-primitive functions: ray(), ellipse(),
regular_polygon(), rectangle(), walk() — plus polygon()'s coincident-vertex
guard. ray()/ellipse() wrap existing IR DefStmt kinds; the rest compute
literal coordinates with plain arithmetic and hand them to polygon()."""
import math

import pytest

from geometry_diagrams.pydsl.api import point, polygon, ray
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_ray_records_ray_def_from_a_through_b():
    with new_builder_context():
        a, b = point(0, 0), point(1, 1)
        r = ray(a, b)
        ir = get_builder().build()
    ray_defs = [d for d in ir.define if d.kind == "ray" and d.id == r.id]
    assert len(ray_defs) == 1
    assert ray_defs[0].a == a.id
    assert ray_defs[0].b == b.id


def test_polygon_rejects_coincident_consecutive_vertices():
    with new_builder_context():
        a, b, c, d = point(0, 0), point(4, 0), point(4, 4), point(4, 4)
        with pytest.raises(ValueError, match="coincident"):
            polygon(a, b, c, d)


def test_polygon_rejects_repeated_first_point_as_last():
    with new_builder_context():
        a, b, c = point(0, 0), point(4, 0), point(4, 4)
        closing_repeat = point(0, 0)
        with pytest.raises(ValueError, match="coincident"):
            polygon(a, b, c, closing_repeat)


def test_polygon_allows_unknown_coordinate_vertices_without_false_positive():
    from geometry_diagrams.ir.ir import LineThrough

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        c, d = point(4, 4), point(0, 4)
        line_id = builder._fresh_hidden_id("line")
        builder._add(LineThrough(id=line_id, p=a.id, q=d.id))
        from geometry_diagrams.pydsl.handles import Line
        from geometry_diagrams.pydsl.api import point_on

        on_line = point_on(Line(id=line_id, _builder=builder), 0.5)  # coordinates unknown until compile
        p = polygon(a, b, c, on_line)
    assert p.id is not None


def test_polygon_still_builds_valid_non_coincident_shape():
    with new_builder_context():
        pts = [point(0, 0), point(1, 0), point(1, 1), point(0, 1)]
        p = polygon(*pts)
    assert p.vertices == tuple(pts)


from geometry_diagrams.pydsl.api import regular_polygon


def test_regular_polygon_produces_hand_computed_square_vertices():
    with new_builder_context():
        center = point(0, 0)
        result = regular_polygon(center, radius=1.0, n=4, start_angle=0.0)
    assert len(result.vertices) == 4
    expected = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    for v, (ex, ey) in zip(result.vertices, expected):
        assert v.x == pytest.approx(ex, abs=1e-9)
        assert v.y == pytest.approx(ey, abs=1e-9)


def test_regular_polygon_requires_n_at_least_3():
    with new_builder_context():
        center = point(0, 0)
        with pytest.raises(ValueError, match="n >= 3"):
            regular_polygon(center, radius=1.0, n=2)


def test_regular_polygon_accepts_a_constructed_center():
    from geometry_diagrams.ir.ir import LineThrough
    from geometry_diagrams.pydsl.api import point_on
    from geometry_diagrams.pydsl.handles import Line

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        line_id = builder._fresh_hidden_id("line")
        builder._add(LineThrough(id=line_id, p=a.id, q=b.id))
        center = point_on(Line(id=line_id, _builder=builder), 0.5)
        result = regular_polygon(center, radius=1.0, n=4)
    assert len(result.vertices) == 4
    for v in result.vertices:
        assert v.x == pytest.approx(v.x)  # resolves without raising


from geometry_diagrams.pydsl.api import rectangle


def test_rectangle_pivot_corner_hand_computed_90_degree_rotation():
    with new_builder_context():
        corner = point(0, 0)
        result = rectangle(corner, width=2.0, height=1.0, rotation=math.pi / 2, pivot="corner")
    expected = [(0.0, 0.0), (0.0, 2.0), (-1.0, 2.0), (-1.0, 0.0)]
    for v, (ex, ey) in zip(result.vertices, expected):
        assert v.x == pytest.approx(ex, abs=1e-9)
        assert v.y == pytest.approx(ey, abs=1e-9)


def test_rectangle_pivot_center_hand_computed_90_degree_rotation():
    with new_builder_context():
        corner = point(0, 0)
        result = rectangle(corner, width=2.0, height=1.0, rotation=math.pi / 2, pivot="center")
    expected = [(1.5, -0.5), (1.5, 1.5), (0.5, 1.5), (0.5, -0.5)]
    for v, (ex, ey) in zip(result.vertices, expected):
        assert v.x == pytest.approx(ex, abs=1e-9)
        assert v.y == pytest.approx(ey, abs=1e-9)


def test_rectangle_no_rotation_is_axis_aligned():
    with new_builder_context():
        corner = point(1.0, 1.0)
        result = rectangle(corner, width=3.0, height=2.0)
    expected = [(1.0, 1.0), (4.0, 1.0), (4.0, 3.0), (1.0, 3.0)]
    for v, (ex, ey) in zip(result.vertices, expected):
        assert v.x == pytest.approx(ex, abs=1e-9)
        assert v.y == pytest.approx(ey, abs=1e-9)


def test_rectangle_rejects_invalid_pivot():
    with new_builder_context():
        corner = point(0, 0)
        with pytest.raises(ValueError, match="pivot"):
            rectangle(corner, width=1.0, height=1.0, pivot="edge")


from geometry_diagrams.pydsl.api import draw, draw_points, walk


def test_walk_builds_closed_square_matching_hand_computed_vertices():
    """The documented usage pattern: track heading in a loop, collect points,
    hand them to polygon() without ever re-adding the start point."""
    with new_builder_context():
        start = point(0.0, 0.0)
        pts = [start]
        heading = 0.0
        for _ in range(3):  # 3 more sides close a 4-sided square
            pts.append(walk(pts[-1], heading, 1.0))
            heading += math.pi / 2
        square = polygon(*pts)
    expected = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for v, (ex, ey) in zip(square.vertices, expected):
        assert v.x == pytest.approx(ex, abs=1e-9)
        assert v.y == pytest.approx(ey, abs=1e-9)


def test_walk_accepts_a_constructed_from_point():
    from geometry_diagrams.ir.ir import LineThrough
    from geometry_diagrams.pydsl.api import point_on
    from geometry_diagrams.pydsl.handles import Line

    with new_builder_context() as builder:
        a, b = point(0, 0), point(4, 0)
        line_id = builder._fresh_hidden_id("line")
        builder._add(LineThrough(id=line_id, p=a.id, q=b.id))
        start = point_on(Line(id=line_id, _builder=builder), 0.5)  # (2, 0)
        result = walk(start, 0.0, 1.0)
    assert (result.x, result.y) == pytest.approx((3.0, 0.0))


def test_walk_works_through_the_real_sandbox():
    from geometry_diagrams.pydsl.sandbox import run_script

    script = (
        "import math\n"
        "start = point(0.0, 0.0)\n"
        "p1 = walk(start, 0.0, 1.0)\n"
        "p2 = walk(p1, math.pi / 2, 1.0)\n"
        "p3 = walk(p2, math.pi, 1.0)\n"
        "square = polygon(start, p1, p2, p3)\n"
        "draw(square)\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    poly_defs = [d for d in result.diagram_ir.define if d.kind == "polygon"]
    assert len(poly_defs) == 1
    assert len(poly_defs[0].points) == 4


from geometry_diagrams.pydsl.api import ellipse


def test_ellipse_center_axes_form_records_ellipse_center_axes():
    from geometry_diagrams.ir.ir import EllipseCenterAxes

    with new_builder_context() as builder:
        c = point(1.0, 1.0)
        result = ellipse(center=c, hradius=3.0, vradius=2.0)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, EllipseCenterAxes) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].center == c.id
    assert defs[0].hradius == 3.0
    assert defs[0].vradius == 2.0
    assert result.center.id == c.id
    assert result.hradius == 3.0
    assert result.vradius == 2.0


def test_ellipse_center_axes_form_rejects_non_positive_radii():
    with new_builder_context():
        c = point(0.0, 0.0)
        with pytest.raises(ValueError, match="positive"):
            ellipse(center=c, hradius=0.0, vradius=2.0)
        with pytest.raises(ValueError, match="positive"):
            ellipse(center=c, hradius=3.0, vradius=-1.0)


def test_ellipse_bbox_form_records_ellipse_bbox_and_derives_center_and_radii():
    from geometry_diagrams.ir.ir import EllipseBBox
    from geometry_diagrams.ir.to_sympy import compile_defs

    with new_builder_context() as builder:
        p1, p2 = point(0.0, 0.0), point(4.0, 2.0)
        result = ellipse(corner1=p1, corner2=p2)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, EllipseBBox) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].corner1 == p1.id
    assert defs[0].corner2 == p2.id
    assert result.hradius == pytest.approx(2.0)
    assert result.vradius == pytest.approx(1.0)
    sym = compile_defs(ir)
    center_pt = sym[result.center.id]
    assert float(center_pt.x.evalf()) == pytest.approx(2.0)
    assert float(center_pt.y.evalf()) == pytest.approx(1.0)


def test_ellipse_requires_exactly_one_complete_group():
    with new_builder_context():
        c = point(0.0, 0.0)
        p1, p2 = point(0.0, 0.0), point(4.0, 2.0)
        with pytest.raises(ValueError, match="not both"):
            ellipse(center=c, hradius=1.0, vradius=1.0, corner1=p1, corner2=p2)
        with pytest.raises(ValueError, match="together"):
            ellipse(center=c, hradius=1.0)
        with pytest.raises(ValueError, match="together"):
            ellipse(corner1=p1)
        with pytest.raises(ValueError, match="requires either"):
            ellipse()
