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
