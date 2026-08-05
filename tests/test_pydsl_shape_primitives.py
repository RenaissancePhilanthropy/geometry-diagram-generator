# tests/test_pydsl_shape_primitives.py
"""Tests for pydsl's new shape-primitive functions: ray(), ellipse(),
regular_polygon(), rectangle(), walk() — plus polygon()'s coincident-vertex
guard. ray()/ellipse() wrap existing IR DefStmt kinds; the rest compute
literal coordinates with plain arithmetic and hand them to polygon()."""
import math

import pytest

from geometry_diagrams.pydsl.api import point, ray
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
