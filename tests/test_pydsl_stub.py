"""Tests for the pydsl stub generator."""
import inspect

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


def test_stub_auto_discovers_all_30_assert_predicates_with_no_stub_code_change():
    """stub.py's generate_stub() iterates pydsl.__all__ generically — it has
    no special-casing for assert_* at all. This test proves the 30-function
    assert_* surface added across tickets 01-04, pydsl-authoring-quality's
    ticket 01 (assert_labels_in_canvas) and curve-family-parity's five
    curved-family predicates is picked up automatically (signature +
    docstring first line), with zero change to stub.py itself."""
    from geometry_diagrams.pydsl import asserts as asserts_module
    import geometry_diagrams.pydsl as pydsl_module

    assert len(asserts_module.__all__) == 30
    stub = generate_stub()
    for name in asserts_module.__all__:
        assert name in pydsl_module.__all__, f"{name} missing from pydsl.__all__"
        assert f"def {name}(" in stub, f"missing {name} in stub"
        fn = getattr(pydsl_module, name)
        doc = inspect.getdoc(fn) or ""
        first_line = doc.splitlines()[0] if doc else ""
        assert first_line, f"{name} is missing a docstring"
        assert first_line in stub, f"missing docstring first line for {name}"


def test_stub_documents_a_class_block_for_every_handle_in_pydsl_all():
    """Every handle class re-exported from pydsl.__all__ must get its own
    `class Foo:` block — Polyline was silently missing from stub.py's
    _HANDLE_CLASS_NAMES, so Polyline.label() was invisible to any model
    reading the stub even though the polyline() constructor was listed."""
    import geometry_diagrams.pydsl as pydsl_module

    stub = generate_stub()
    handle_names = [
        name for name in pydsl_module.__all__
        if inspect.isclass(getattr(pydsl_module, name))
    ]
    assert "Polyline" in handle_names
    for name in handle_names:
        assert f"class {name}:" in stub, f"missing 'class {name}:' block in stub"


def test_stub_documents_polyline_label_method():
    stub = generate_stub()
    block = stub.split("class Polyline:")[1]
    # Everything up to the next top-level construct is Polyline's own block.
    body = block.split("\nclass ")[0].split("\ndef ")[0]
    assert "def label(" in body
    assert "polyline's own centroid" in body
