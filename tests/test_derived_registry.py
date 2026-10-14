"""Derived-entity registry: dependents tracking and registration rules."""
import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import DerivedConstruction, DerivedRegistry
from geometry_diagrams.ir.refs import compute_dependents, downstream_of
from geometry_diagrams.ir.to_sympy import compile_defs


def test_edit_to_tangent_circle_inputs_reaches_derived_center_and_its_dependents():
    diagram = ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=0, y=0),
            ir.PointFixed(id="P", x=2, y=0),
            ir.CircleCenterPoint(id="c1", center="O", through="P"),
            ir.CircleTangentAt(id="c2", circle="c1", point="P", radius=1),
            ir.PointFixed(id="Q", x=5, y=5),
            ir.Segment(id="join", a=ir.tangent_circle_center_id("c2"), b="Q"),
        ],
        render=[],
    )
    compile_defs(diagram)  # sanity: the diagram compiles
    downstream = downstream_of(compute_dependents(diagram), {"c1"})
    assert {"c2", "c2_center", "join"} <= downstream


def test_edit_to_polygon_on_edge_inputs_reaches_derived_vertices_and_dependents():
    diagram = ir.DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0),
            ir.PointFixed(id="B", x=4, y=0),
            ir.PointFixed(id="R", x=2, y=-3),
            ir.PolygonOnEdge(
                id="poly", a="A", b="B", ref="R",
                vertex_names=["A", "B", "C", "D"],
                side_lengths=[3, 4, 3], angles=[90, 90, 90, 90],
            ),
            ir.Segment(id="diag", a="A", b="C"),
        ],
        render=[],
    )
    compile_defs(diagram)
    downstream = downstream_of(compute_dependents(diagram), {"B"})
    assert {"poly", "C", "D", "diag"} <= downstream


def test_derived_name_that_is_a_real_definition_is_not_attributed_to_owner():
    diagram = ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=0, y=0),
            ir.PointFixed(id="P", x=2, y=0),
            ir.CircleCenterPoint(id="c1", center="O", through="P"),
            ir.PointFixed(id="c2_center", x=9, y=9),
            ir.CircleTangentAt(id="c2", circle="c1", point="P", radius=1),
        ],
        render=[],
    )
    sym = compile_defs(diagram)
    assert sym["c2_center"].x == 9  # real definition wins, no new error
    assert "c2_center" not in compute_dependents(diagram)["c1"]


def _noop(*_):
    return []


def _construction(kind, forms):
    return DerivedConstruction(kind, tuple(forms), _noop, _noop)


def test_two_kinds_claiming_the_same_derived_id_form_are_rejected():
    reg = DerivedRegistry()
    reg.register(_construction("kind_a", ["{id}_x"]))
    with pytest.raises(ValueError, match="claimed by both"):
        reg.register(_construction("kind_b", ["{id}_x"]))


def test_registering_the_same_kind_twice_is_rejected():
    reg = DerivedRegistry()
    reg.register(_construction("kind_a", ["{id}_x"]))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_construction("kind_a", ["{id}_y"]))
