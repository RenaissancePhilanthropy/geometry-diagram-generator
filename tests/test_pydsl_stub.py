"""Tests for the pydsl stub generator."""
from geometry_diagrams.pydsl.stub import generate_stub


def test_stub_includes_every_public_function():
    stub = generate_stub()
    for name in ("point", "line_through", "triangle", "polygon", "circumcircle",
                 "incircle", "altitude", "median", "mark_angle"):
        assert f"def {name}(" in stub, f"missing {name} in stub"


def test_stub_includes_handle_accessor_methods():
    stub = generate_stub()
    assert "def side(" in stub  # from Triangle/Polygon
    assert "def angle_at(" in stub


def test_stub_includes_handle_dataclass_fields_not_just_methods():
    # The whole point of the handle design (see the design doc) is that the
    # model learns `circ.center` / `alt.foot` / `med.midpoint` exist WITHOUT
    # ever assigning them an id itself. A stub generator that only emits
    # methods (side(), angle_at()) and skips dataclass fields would silently
    # fail to teach the model these accessors exist at all.
    stub = generate_stub()
    assert "center" in stub  # Circle.center
    assert "radius" in stub  # Circle.radius
    assert "foot" in stub    # Altitude.foot
    assert "midpoint" in stub  # Median.midpoint
    assert "vertices" in stub  # Triangle.vertices / Polygon.vertices


def test_stub_does_not_include_private_helpers():
    stub = generate_stub()
    assert "_fresh_hidden_id" not in stub
    assert "_get_or_create_segment" not in stub
    # Triangle/Polygon carry an internal _builder reference (see Task 2's
    # note on why) — it must never leak into the model-facing stub.
    assert "_builder" not in stub
