"""Tests for the python_full strategy's prompt-assembly."""
from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions
from geometry_diagrams.pydsl.stub import generate_stub


def test_build_python_full_instructions_embeds_live_stub_text():
    """The API reference in the prompt must come from generate_stub() at call
    time, not a stale hand-copied string — a signature/docstring change to
    any pydsl op should update this prompt automatically."""
    instructions = build_python_full_instructions()
    assert generate_stub() in instructions


def test_build_python_full_instructions_states_the_mandatory_draw_rule():
    instructions = build_python_full_instructions()
    assert "draw(obj)" in instructions
    assert "draw_points" in instructions


def test_build_python_full_instructions_states_the_sandbox_constraint():
    instructions = build_python_full_instructions()
    assert "no imports" in instructions


def test_python_full_instructions_document_new_shape_primitives():
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    text = build_python_full_instructions()
    for name in ("ray(", "ellipse(", "regular_polygon(", "rectangle(", "walk("):
        assert name in text, f"instructions missing mention of {name}"
    assert "polygon() closes the shape automatically" in text


def test_python_full_instructions_document_styling():
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    text = build_python_full_instructions()
    for name in ("color", "thick", "dashed", "arrow_start", "fill("):
        assert name in text, f"instructions missing mention of {name}"


def test_python_full_instructions_warn_against_shadowing_api_names():
    """A model writing `incircle = incircle(tri)` is a confirmed, reproducible
    sandbox hard-error ("Cannot assign to name ... would erase the existing
    tool!") — the instructions must warn against reusing any API function
    name as a variable name, not just this one example."""
    text = build_python_full_instructions()
    assert "incircle" in text.lower()
    assert "erase the existing tool" in text


def test_python_full_instructions_document_marks_and_fill_holes():
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    text = build_python_full_instructions()
    for name in ("mark_equal(", "mark_parallel(", "mark_right_angle(", "holes="):
        assert name in text, f"instructions missing mention of {name}"
