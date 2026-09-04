# tests/test_pydsl_draw_brace.py
"""Tests for the draw_brace() pydsl primitive — wraps the IR DrawBrace
RenderOp (see ir.py, to_svg.py, to_tikz.py). Follows the same conventions
as test_pydsl_labels.py's label_text() tests, since DrawBrace mirrors
LabelFreeText: literal [x, y] coordinates, no dependency on any defined
geometric object."""
import pytest

from geometry_diagrams.pydsl.api import draw_brace, point
from geometry_diagrams.pydsl.builder import new_builder_context
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.ir.ir import DrawBrace


def test_draw_brace_records_draw_brace_op_with_defaults():
    with new_builder_context() as builder:
        draw_brace((0.0, 0.0), (4.0, 0.0))
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, DrawBrace)]
    assert len(matches) == 1
    assert matches[0].p1 == [0.0, 0.0]
    assert matches[0].p2 == [4.0, 0.0]
    assert matches[0].direction == "up"
    assert matches[0].label is None


def test_draw_brace_accepts_direction_and_label():
    with new_builder_context() as builder:
        draw_brace((0.0, 0.0), (4.0, 0.0), direction="down", label="4 items")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, DrawBrace)]
    assert matches[0].direction == "down"
    assert matches[0].label == "4 items"


def test_draw_brace_rejects_invalid_direction():
    with new_builder_context():
        with pytest.raises(ValueError):
            draw_brace((0.0, 0.0), (4.0, 0.0), direction="sideways")


def test_draw_brace_autofixes_python_escaped_latex_command_in_label():
    # Same corruption mechanism as label_text()/Point.label() — a script
    # author writing "\alpha" in a normal string literal gets it consumed by
    # Python's own escape handling before this code ever sees it.
    with new_builder_context() as builder:
        draw_brace((0.0, 0.0), (4.0, 0.0), label="\alpha")
        ir = builder.build()
    matches = [r for r in ir.render if isinstance(r, DrawBrace)]
    assert matches[0].label == "α"


def test_draw_brace_requires_a_builder():
    with pytest.raises(RuntimeError):
        draw_brace((0.0, 0.0), (4.0, 0.0))


def test_draw_brace_is_exported_ungated_in_pydsl_all():
    import geometry_diagrams.pydsl as pydsl_module

    assert "draw_brace" in pydsl_module.__all__
    assert pydsl_module.draw_brace is draw_brace


def test_draw_brace_appears_in_generated_stub_with_no_flag_required():
    from geometry_diagrams.pydsl.stub import generate_stub

    stub = generate_stub()
    assert "def draw_brace(" in stub


def test_draw_brace_works_through_the_real_sandbox():
    script = (
        "draw_brace((0.0, 0.0), (4.0, 0.0), direction='down', label='4 items')\n"
    )
    result = run_script(script, timeout_seconds=10.0)
    assert result.error is None, result.error
    assert result.diagram_ir is not None
    braces = [r for r in result.diagram_ir.render if isinstance(r, DrawBrace)]
    assert len(braces) == 1
    assert braces[0].label == "4 items"
