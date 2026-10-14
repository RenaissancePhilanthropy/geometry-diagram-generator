"""Tests for the shared StructuredRunResult dataclass."""
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.ir import DiagramIR


def _make_minimal_result(**overrides) -> StructuredRunResult:
    defaults = dict(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="", sym_table={}, sym_full={},
    )
    defaults.update(overrides)
    return StructuredRunResult(**defaults)


def test_python_full_metadata_defaults_to_none():
    result = _make_minimal_result()
    assert result.python_full_metadata is None
    assert result.recipe_metadata is None  # unaffected, still independently None


def test_python_full_metadata_can_be_set_independently_of_recipe_metadata():
    result = _make_minimal_result(python_full_metadata={"attempt_traces": []})
    assert result.python_full_metadata == {"attempt_traces": []}
    assert result.recipe_metadata is None


# ---------------------------------------------------------------------------
# Warnings list on the pipeline result (solids ticket 04)
# ---------------------------------------------------------------------------
import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.ir_pipeline import (
    PipelineError, format_warnings_for_retry, run_ir_pipeline,
)


def _triangle_ir(render=None, checks=None) -> DiagramIR:
    return DiagramIR(
        define=[
            ir.PointFixed(id="A", x=0, y=0),
            ir.PointFixed(id="B", x=4, y=0),
            ir.PointFixed(id="C", x=0, y=3),
        ],
        checks=checks or [],
        render=render if render is not None else [ir.Draw(obj="A")],
    )


@pytest.mark.asyncio
async def test_clean_diagram_has_empty_warnings_and_identical_svg():
    diagram = _triangle_ir()
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert result.warnings == []
    direct = SVGRenderer().render(diagram, result.sym_full)
    assert result.svg == direct.output


@pytest.mark.asyncio
async def test_draw_of_undefined_id_produces_renderer_warning_without_failing():
    diagram = _triangle_ir(render=[ir.Draw(obj="A"), ir.Draw(obj="NOPE")])
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert any("NOPE" in w for w in result.warnings)
    assert result.svg


@pytest.mark.asyncio
async def test_failed_prefer_check_becomes_warning_not_failure():
    # A, B, C are not collinear; level "prefer" must warn only.
    diagram = _triangle_ir(checks=[ir.Collinear(points=["A", "B", "C"], level="prefer")])
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert result.warnings == [
        "Preferred check not satisfied: Points 'A', 'B', 'C' are not collinear"
    ]


@pytest.mark.asyncio
async def test_must_failure_raises_pipeline_error_carrying_warnings():
    diagram = _triangle_ir(checks=[
        ir.Collinear(points=["A", "B", "C"], level="prefer"),
        ir.Collinear(points=["A", "B", "C"], level="must"),
    ])
    with pytest.raises(PipelineError) as exc:
        await run_ir_pipeline(diagram, SVGRenderer())
    assert isinstance(exc.value, RuntimeError)
    assert "Geometric checks failed" in str(exc.value)
    assert len(exc.value.warnings) == 1


def test_format_warnings_for_retry():
    assert format_warnings_for_retry([]) == ""
    text = format_warnings_for_retry(["w one", "w two"])
    assert "w one" in text and "w two" in text
