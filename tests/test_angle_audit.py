"""Angle audit: a right-angle mark or an angle label is checked against the angle that is
actually drawn. Mismatches are pipeline warnings, and optionally a pipeline failure."""
from __future__ import annotations

import asyncio
import math

import pytest

from geometry_diagrams.ir.angle_audit import audit_angles, parse_angle_text
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies.ir_pipeline import PipelineError, run_ir_pipeline


# --- the text parser -------------------------------------------------------------

@pytest.mark.parametrize("text,degrees", [
    ("35°", 35), ("35.5°", 35.5), (" 90° ", 90), ("35 deg", 35), ("35 degrees", 35),
    ("∠B = 60°", 60), ("x = 35°", 35), ("θ = 120°", 120), ("m∠ABC = 72°", 72), ("angle ABC = 40°", 40),
    ("π/3", 60), ("2π/3", 120), ("π", 180), ("0.5π", 90), ("π/6 rad", 30), ("θ = π/4", 45),
    ("1.0472 rad", 1.0472 * 180 / math.pi), ("α = 3π/4 rad", 135),
])
def test_parses_a_stated_angle(text, degrees):
    assert parse_angle_text(text) == pytest.approx(degrees)


@pytest.mark.parametrize("text", [
    "x", "?", "A", "35", "35 cm", "6", "Area = ?", "∠A = 180° − 40° − 40° = 100°",
    "65° + θ = 180°", "Co-interior angles sum to 180°:", "45° and 60°", "", "π/0", "θ°",
])
def test_ignores_everything_else(text):
    assert parse_angle_text(text) is None


# --- the audit on real figures -----------------------------------------------------

# Right angle at B (6, 8 legs); A is at the top, C to the right.
TRI = """
canvas((-2, 12), (-2, 10))
a = point(0, 6); b = point(0, 0); c = point(8, 0)
t = triangle(a, b, c); draw(t)
a.label("A"); b.label("B"); c.label("C")
"""


def _audit(script: str):
    result = run_script(script, timeout_seconds=60)
    assert result.error is None, result.error
    return audit_angles(result.diagram_ir, compile_defs(result.diagram_ir))


def test_a_correct_figure_has_no_findings():
    assert _audit(TRI + 'mark_right_angle(t.angle_at(b)); t.angle_at(b).label("90°")'
                  '; t.angle_at(c).label("36.87°"); t.angle_at(a).label("∠A = 53.13°")') == []


def test_a_right_angle_mark_on_an_oblique_angle_is_found():
    (finding,) = _audit(TRI + "mark_right_angle(t.angle_at(c))")
    assert finding.kind == "right_angle_mark"
    assert finding.drawn_deg == pytest.approx(36.87, abs=0.01) and finding.stated_deg == 90
    assert "∠" in finding.message and "A" in finding.message and "36.9" in finding.message


def test_a_wrong_angle_label_is_found():
    (finding,) = _audit(TRI + 't.angle_at(c).label("50°")')
    assert finding.kind == "angle_label" and finding.stated_deg == 50
    assert finding.drawn_deg == pytest.approx(36.87, abs=0.01)
    assert '"50°"' in finding.message


def test_name_equals_and_radian_labels_are_checked_too():
    assert _audit(TRI + 't.angle_at(c).label("∠C = 50°")')
    assert not _audit(TRI + 't.angle_at(b).label("π/2")')
    assert _audit(TRI + 't.angle_at(b).label("π/3")')


def test_labels_that_are_not_a_single_angle_value_are_left_alone():
    assert _audit(TRI + 't.angle_at(c).label("x"); t.angle_at(b).label("65° + θ = 180°")') == []


def test_a_rounded_label_inside_the_tolerance_passes():
    assert _audit(TRI + 't.angle_at(c).label("37°")') == []


# --- the pipeline ----------------------------------------------------------------------

def _run(script: str, **kwargs):
    result = run_script(script, timeout_seconds=60)
    assert result.error is None, result.error
    return asyncio.run(run_ir_pipeline(result.diagram_ir, SVGRenderer(), **kwargs))


def test_a_mismatch_is_a_warning_by_default():
    result = _run(TRI + "mark_right_angle(t.angle_at(c))")
    assert any("right-angle mark" in w.lower() for w in result.warnings)
    assert "<svg" in result.svg


def test_a_clean_figure_adds_no_angle_warning():
    result = _run(TRI + 'mark_right_angle(t.angle_at(b)); t.angle_at(c).label("37°")')
    assert not any("angle" in w.lower() for w in result.warnings)


def test_fail_on_angle_mismatch_raises_with_the_findings():
    with pytest.raises(PipelineError, match="drawn at") as info:
        _run(TRI + 't.angle_at(c).label("50°")', fail_on_angle_mismatch=True)
    assert any('"50°"' in w for w in info.value.warnings)


def test_fail_on_angle_mismatch_passes_a_clean_figure():
    assert _run(TRI + 'mark_right_angle(t.angle_at(b))', fail_on_angle_mismatch=True).svg


# --- the opt-in retry, through the facade ----------------------------------------------

from unittest.mock import AsyncMock, patch  # noqa: E402

from geometry_diagrams import GeometryConfig, render_geometry_diagram  # noqa: E402
from geometry_diagrams.config import resolve_config  # noqa: E402
from geometry_diagrams.strategies.python_full import PythonFullStrategy  # noqa: E402
from geometry_diagrams.strategies.recipe import RecipeStrategy  # noqa: E402
from geometry_diagrams.strategies.structured import StructureStrategy  # noqa: E402


def test_config_field_env_and_resolve(monkeypatch):
    assert GeometryConfig.from_env().retry_on_angle_mismatch is False
    monkeypatch.setenv("GEOMETRY_RETRY_ON_ANGLE_MISMATCH", "true")
    assert GeometryConfig.from_env().retry_on_angle_mismatch is True
    assert resolve_config(GeometryConfig(), retry_on_angle_mismatch=True).retry_on_angle_mismatch is True
    assert resolve_config(GeometryConfig(retry_on_angle_mismatch=True)).retry_on_angle_mismatch is True


@pytest.mark.asyncio
@pytest.mark.parametrize("name,cls", [("python_full", PythonFullStrategy), ("recipe", RecipeStrategy),
                                      ("structured", StructureStrategy)])
async def test_facade_passes_the_flag_to_every_strategy_only_when_set(name, cls):
    run = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(cls, "run", run):
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram("a triangle", config=GeometryConfig(strategy=name, renderer="svg"))
        assert "retry_on_angle_mismatch" not in run.call_args.kwargs
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram(
                "a triangle", config=GeometryConfig(strategy=name, renderer="svg", retry_on_angle_mismatch=True),
            )
        assert run.call_args.kwargs["retry_on_angle_mismatch"] is True


@pytest.mark.asyncio
async def test_python_full_retries_with_the_finding_in_the_next_prompt():
    """First script labels the 36.87° angle "50°"; with the flag on that fails the attempt and
    the corrected script is requested with the finding in the prompt."""
    from tests.test_strategy_robustness import _structured_llm
    from geometry_diagrams.strategies.python_full import PydslScriptOutput

    bad = TRI + 't.angle_at(c).label("50°")'
    good = TRI + 't.angle_at(c).label("37°")'
    llm = _structured_llm([PydslScriptOutput(script=bad), PydslScriptOutput(script=good)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm):
        result = await PythonFullStrategy().run(
            "a right triangle with its acute angle labeled", model="anthropic:claude-sonnet-4-6",
            renderer=SVGRenderer(), retry_on_angle_mismatch=True,
        )
    assert result.retries == 1 and "37°" in result.script
