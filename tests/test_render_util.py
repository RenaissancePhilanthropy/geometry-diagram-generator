"""Tests for geometry_diagrams/ir/render_util.py."""
from geometry_diagrams.ir.render_util import tick_values


def test_tick_values_excludes_zero():
    assert 0 not in tick_values(-4, 4, 1)


def test_tick_values_excludes_endpoints_when_on_step():
    # Canvas boundary 0..7000 at step 1000: 7000 is the axis arrowhead's own
    # endpoint — a tick there overlaps the arrowhead and must be excluded.
    values = tick_values(0, 7000, 1000)
    assert 7000 not in values
    assert 0 not in values
    assert values == [1000, 2000, 3000, 4000, 5000, 6000]


def test_tick_values_excludes_negative_endpoint():
    values = tick_values(-3000, 3000, 1000)
    assert -3000 not in values
    assert 3000 not in values
    assert values == [-2000, -1000, 1000, 2000]


def test_tick_values_keeps_interior_values_when_endpoints_not_on_step():
    # Endpoints not exact multiples of step -> nothing to exclude beyond 0.
    values = tick_values(-3.5, 3.5, 1)
    assert values == [-3, -2, -1, 1, 2, 3]
