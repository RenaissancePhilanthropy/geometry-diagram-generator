"""Incremental builder vs whole-diagram compile agree on derived vertices."""
import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def _agree(defs, derived_id):
    with new_builder_context():
        b = get_builder()
        for d in defs:
            b._add(d)
        mid_script = b._resolve_point(derived_id)  # incremental path
        diagram = b.build()
    p = compile_defs(diagram)[derived_id]
    assert mid_script == pytest.approx((float(p.x), float(p.y)))


def test_polygon_exterior_derived_vertex_agrees():
    _agree([
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="R", x=2, y=3),
        ir.PolygonExterior(id="sq", a="A", b="B", ref="R", sides=4),
    ], "sq_v2")


def test_polygon_on_edge_derived_vertex_agrees():
    _agree([
        ir.PointFixed(id="A", x=0, y=0),
        ir.PointFixed(id="B", x=4, y=0),
        ir.PointFixed(id="R", x=2, y=-3),
        ir.PolygonOnEdge(
            id="poly", a="A", b="B", ref="R",
            vertex_names=["A", "B", "C", "D"],
            side_lengths=[3, 4, 3], angles=[90, 90, 90, 90],
        ),
    ], "C")
