# tests/test_pydsl_arcs_sectors.py
"""Tests for pydsl's arc/sector primitives and the circle() constructor.
circle() wraps the existing CircleCenterRadius IR def (same class
incircle()'s literal-radius branch already uses); arc()/sector() wrap
ArcCenterStartEnd/SectorCenterStartEnd, both already fully supported by
to_sympy.py/to_tikz.py/to_svg.py — this file is pure pydsl-layer exposure,
plus a validation guard against a real off-circle-point rendering bug
found during spec review, and a rounding fix for a float-precision bug in
regular_sectors() at n=2 (see the design spec's "Two real footguns"
section for the full analysis of both)."""
import math

import pytest

from geometry_diagrams.pydsl.api import circle, point
from geometry_diagrams.pydsl.builder import get_builder, new_builder_context


def test_circle_records_circle_center_radius_with_correct_fields():
    from geometry_diagrams.ir.ir import CircleCenterRadius

    with new_builder_context() as builder:
        c = point(2.0, 3.0)
        result = circle(c, 5.0)
        ir = builder.build()
    defs = [d for d in ir.define if isinstance(d, CircleCenterRadius) and d.id == result.id]
    assert len(defs) == 1
    assert defs[0].center == c.id
    assert defs[0].radius == 5.0
    assert result.center.id == c.id
    assert result.radius == 5.0


def test_circle_rejects_non_positive_radius():
    with new_builder_context():
        c = point(0.0, 0.0)
        with pytest.raises(ValueError, match="positive"):
            circle(c, 0.0)
        with pytest.raises(ValueError, match="positive"):
            circle(c, -3.0)
