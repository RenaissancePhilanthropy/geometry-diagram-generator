"""Tests for query_geometry_diagram / query_diagram — the stateless,
DSL-in query entry points for callers that can't hold server-side sym state.
"""
from __future__ import annotations

import json
import pytest

from geometry_diagrams.ir.ir import DiagramIR, PointFree
from geometry_diagrams.ir.to_sympy import compile_defs


class TestCompileDefsDeterminism:
    """Locks in the assumption query_geometry_diagram depends on: recompiling
    the same DiagramIR with the default (unspecified) rng gives identical
    results across independent calls, even when the IR contains a
    randomly-placed point. This is what makes DSL round-tripping safe for a
    stateless caller — see the "Determinism" section of the design spec.
    """

    def test_point_free_with_no_hint_is_deterministic_across_calls(self):
        diagram = DiagramIR(define=[PointFree(id="P")])
        sym1 = compile_defs(diagram)
        sym2 = compile_defs(diagram)
        assert sym1["P"].x == sym2["P"].x
        assert sym1["P"].y == sym2["P"].y


from geometry_diagrams.facade import query_geometry_diagram


def _triangle_dsl() -> dict:
    """A minimal valid RecipeDSL dict: right triangle A(0,0) B(3,0) C(3,4)."""
    from geometry_diagrams.recipe.dsl import RecipeDSL, PointOp, SegmentOp

    dsl = RecipeDSL(construction=[
        PointOp(id="A", coords=[0.0, 0.0]),
        PointOp(id="B", coords=[3.0, 0.0]),
        PointOp(id="C", coords=[3.0, 4.0]),
        SegmentOp(id="seg_AB", endpoints=["A", "B"]),
    ])
    return dsl.model_dump()


def _two_far_circles_dsl() -> dict:
    """A DSL that lowers fine but fails compile: two non-intersecting circles."""
    from geometry_diagrams.recipe.dsl import RecipeDSL, PointOp, CircleOp, IntersectionOp

    dsl = RecipeDSL(construction=[
        PointOp(id="O1", coords=[0.0, 0.0]),
        PointOp(id="O2", coords=[100.0, 0.0]),
        CircleOp(id="c1", center="O1", radius=1.0),
        CircleOp(id="c2", center="O2", radius=1.0),
        IntersectionOp(id="X", of=["c1", "c2"]),
    ])
    return dsl.model_dump()


class TestQueryGeometryDiagram:
    def test_coordinate_query(self):
        result = json.loads(query_geometry_diagram(_triangle_dsl(), "coordinate", {"point": "A"}))
        assert result == {"x": 0.0, "y": 0.0}

    def test_distance_query(self):
        result = json.loads(query_geometry_diagram(_triangle_dsl(), "distance", {"a": "A", "b": "B"}))
        assert result["distance"] == pytest.approx(3.0)

    def test_length_query(self):
        result = json.loads(query_geometry_diagram(_triangle_dsl(), "length", {"segment": "seg_AB"}))
        assert result["length"] == pytest.approx(3.0)

    def test_malformed_dsl_returns_error(self):
        result = json.loads(query_geometry_diagram({"construction": "not-a-list"}, "coordinate", {"point": "A"}))
        assert "error" in result

    def test_dsl_that_fails_compile_returns_error(self):
        result = json.loads(query_geometry_diagram(_two_far_circles_dsl(), "coordinate", {"point": "X"}))
        assert "error" in result

    def test_deterministic_across_independent_calls(self):
        dsl = _triangle_dsl()
        result1 = query_geometry_diagram(dsl, "coordinate", {"point": "C"})
        result2 = query_geometry_diagram(dsl, "coordinate", {"point": "C"})
        assert result1 == result2


from geometry_diagrams.facade import query_diagram


class TestQueryDiagramTool:
    def test_tool_matches_plain_function_output(self):
        dsl = _triangle_dsl()
        direct = query_geometry_diagram(dsl, "coordinate", {"point": "B"})
        via_tool = query_diagram.invoke({"dsl": dsl, "query_type": "coordinate", "params": {"point": "B"}})
        assert via_tool == direct
