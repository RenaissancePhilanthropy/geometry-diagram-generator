"""Angle audit: a right-angle mark or an angle label is checked against the angle that is
actually drawn. Mismatches are pipeline warnings, and optionally a pipeline failure."""
from __future__ import annotations

import asyncio
import math

import pytest

from geometry_diagrams.ir.angle_audit import AnglePolicy, audit_angles, parse_angle_text
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


def test_retry_mode_raises_on_a_gross_mismatch_with_the_findings():
    with pytest.raises(PipelineError, match="drawn at") as info:
        _run(TRI + 't.angle_at(c).label("50°")', angle_policy=AnglePolicy("retry"))  # 13 degrees off
    assert any('"50°"' in w for w in info.value.warnings)


def test_retry_mode_passes_a_clean_figure():
    assert _run(TRI + 'mark_right_angle(t.angle_at(b))', angle_policy=AnglePolicy("retry")).svg


def test_retry_mode_only_warns_below_the_fail_threshold():
    """40 degrees on a 36.87 degree angle is 3.1 degrees off: above the 1 degree warning
    threshold, below the 5 degree one that fails an attempt."""
    result = _run(TRI + 't.angle_at(c).label("40°")', angle_policy=AnglePolicy("retry"))
    assert any('"40°"' in w for w in result.warnings) and result.svg


def test_warn_mode_never_fails_however_far_off():
    result = _run(TRI + 't.angle_at(c).label("80°")', angle_policy=AnglePolicy("warn"))
    assert any('"80°"' in w for w in result.warnings)


def test_off_mode_does_not_audit_at_all():
    result = _run(TRI + 't.angle_at(c).label("80°"); mark_right_angle(t.angle_at(c))', angle_policy=AnglePolicy("off"))
    assert not any("angle" in w.lower() for w in result.warnings)


def test_the_thresholds_are_configurable():
    script = TRI + 't.angle_at(c).label("40°")'  # 3.1 degrees off
    assert not any('"40°"' in w for w in _run(script, angle_policy=AnglePolicy("warn", tolerance_deg=4)).warnings)
    with pytest.raises(PipelineError):
        _run(script, angle_policy=AnglePolicy("retry", tolerance_deg=1, fail_tolerance_deg=2))


def test_arc_marks_and_their_groups_are_never_audited():
    """A group on mark_angle is a rendering tag; a figure may use it to mean something other
    than "these angles are equal", so unequal angles in one group are not a finding."""
    script = TRI + "mark_angle(t.angle_at(a), 1); mark_angle(t.angle_at(c), 1)"  # 53.13 and 36.87
    assert _audit(script) == []
    assert not any("angle" in w.lower() for w in _run(script, angle_policy=AnglePolicy("retry")).warnings)


def test_a_finding_reports_how_far_off_it_is():
    (finding,) = _audit(TRI + 't.angle_at(c).label("50°")')
    assert finding.error_deg == pytest.approx(13.13, abs=0.01)


@pytest.mark.parametrize("kwargs", [
    {"mode": "loud"}, {"tolerance_deg": 0}, {"tolerance_deg": -1}, {"tolerance_deg": float("nan")},
    {"fail_tolerance_deg": float("inf")}, {"tolerance_deg": True},
    {"tolerance_deg": 6, "fail_tolerance_deg": 5},
])
def test_a_bad_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        AnglePolicy(**kwargs)


# --- the opt-in retry, through the facade ----------------------------------------------

from unittest.mock import AsyncMock, patch  # noqa: E402

from geometry_diagrams import GeometryConfig, render_geometry_diagram  # noqa: E402
from geometry_diagrams.config import resolve_config  # noqa: E402
from geometry_diagrams.strategies.python_full import PythonFullStrategy  # noqa: E402
from geometry_diagrams.strategies.recipe import RecipeStrategy  # noqa: E402
from geometry_diagrams.strategies.structured import StructureStrategy  # noqa: E402


def test_config_fields_env_and_resolve(monkeypatch):
    for name in ("GEOMETRY_ANGLE_CHECK", "GEOMETRY_ANGLE_TOLERANCE_DEG", "GEOMETRY_ANGLE_FAIL_TOLERANCE_DEG"):
        monkeypatch.delenv(name, raising=False)
    cfg = GeometryConfig.from_env()
    assert (cfg.angle_check, cfg.angle_tolerance_deg, cfg.angle_fail_tolerance_deg) == ("warn", 1.0, 5.0)
    assert cfg.angle_policy() is None  # all defaults: strategy calls keep their shape
    monkeypatch.setenv("GEOMETRY_ANGLE_CHECK", "RETRY")
    monkeypatch.setenv("GEOMETRY_ANGLE_TOLERANCE_DEG", "2")
    monkeypatch.setenv("GEOMETRY_ANGLE_FAIL_TOLERANCE_DEG", "8.5")
    assert GeometryConfig.from_env().angle_policy() == AnglePolicy("retry", 2.0, 8.5)
    assert resolve_config(GeometryConfig(), angle_check="off").angle_policy() == AnglePolicy("off")
    assert resolve_config(GeometryConfig(angle_check="retry")).angle_policy() == AnglePolicy("retry")


@pytest.mark.parametrize("name,value", [
    ("GEOMETRY_ANGLE_CHECK", "loud"), ("GEOMETRY_ANGLE_TOLERANCE_DEG", "abc"),
    ("GEOMETRY_ANGLE_TOLERANCE_DEG", "0"), ("GEOMETRY_ANGLE_FAIL_TOLERANCE_DEG", "0.5"),
])
def test_a_bad_env_value_fails_where_the_environment_is_read(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        GeometryConfig.from_env()


def test_resolve_config_rejects_a_bad_value_early():
    with pytest.raises(ValueError, match="angle_check"):
        resolve_config(GeometryConfig(), angle_check="loud")


@pytest.mark.asyncio
@pytest.mark.parametrize("name,cls", [("python_full", PythonFullStrategy), ("recipe", RecipeStrategy),
                                      ("structured", StructureStrategy)])
async def test_facade_passes_the_flag_to_every_strategy_only_when_set(name, cls):
    run = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(cls, "run", run):
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram("a triangle", config=GeometryConfig(strategy=name, renderer="svg"))
        assert "angle_policy" not in run.call_args.kwargs
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram(
                "a triangle", config=GeometryConfig(strategy=name, renderer="svg", angle_check="retry"),
            )
        assert run.call_args.kwargs["angle_policy"] == AnglePolicy("retry")
        with pytest.raises(RuntimeError, match="stop"):  # the per-call kwarg overrides the config
            await render_geometry_diagram(
                "a triangle", config=GeometryConfig(strategy=name, renderer="svg", angle_check="retry"),
                angle_check="off",
            )
        assert run.call_args.kwargs["angle_policy"] == AnglePolicy("off")


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
            renderer=SVGRenderer(), angle_policy=AnglePolicy("retry"),
        )
    assert result.retries == 1 and "37°" in result.script


# --- edit turns ------------------------------------------------------------------------

from geometry_diagrams.strategies import python_full as pf  # noqa: E402

EDIT_BASE = TRI + 't.angle_at(c).label("37°")\n'
EDIT_WRONG = TRI + 't.angle_at(c).label("50°")\n'


def _edit_with(monkeypatch, mode: str, new_script: str, **flags):
    """Run a stateless python_full edit whose generator returns `new_script`."""
    async def fake_gen(prompt, model, **kw):
        if mode == "search_replace":
            return [{"old_string": EDIT_BASE, "new_string": new_script}], 1, 1, None
        raise AssertionError(mode)

    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    return asyncio.run(PythonFullStrategy().edit(
        "relabel", EDIT_BASE, model="m", renderer=SVGRenderer(), **flags))


def test_a_mismatch_introduced_by_a_single_call_edit_is_a_warning_by_default(monkeypatch):
    result = _edit_with(monkeypatch, "search_replace", EDIT_WRONG)
    assert any('"50°"' in w for w in result.warnings)


def test_the_flag_fails_a_single_call_edit_that_introduces_a_mismatch(monkeypatch):
    # Like any failure of the edited script: a RuntimeError, no retry, nothing stored.
    with pytest.raises(RuntimeError, match='contradict the drawn angles.*"50°"'):
        _edit_with(monkeypatch, "search_replace", EDIT_WRONG, angle_policy=AnglePolicy("retry"))


def test_the_flag_does_not_block_an_edit_of_a_figure_that_was_already_wrong(monkeypatch):
    """The baseline rerun of previous_script must not apply the flag, or a stored figure with a
    bad mark could never be edited; only the edited script is held to it."""
    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "50°", "new_string": "37°"}], 1, 1, None

    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    result = asyncio.run(PythonFullStrategy().edit(
        "fix the label", EDIT_WRONG, model="m", renderer=SVGRenderer(), angle_policy=AnglePolicy("retry")))
    assert "37°" in result.script and not any("angle" in w.lower() for w in result.warnings)


def test_full_rewrite_edits_pass_the_flag_to_the_loop(monkeypatch):
    seen = {}

    async def fake_run(self, prompt, **kw):
        seen.update(kw)
        raise RuntimeError("stop")

    async def baseline(script, renderer, *a, **kw):
        from tests.test_stateless_edit import _result
        return _result(script)

    monkeypatch.setattr(pf, "_run_from_script", baseline)
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(PythonFullStrategy().edit(
            "relabel", EDIT_BASE, model="m", edit_generation_mode="full_rewrite", angle_policy=AnglePolicy("retry")))
    assert seen["angle_policy"] == AnglePolicy("retry")


@pytest.mark.asyncio
async def test_facade_passes_the_flag_to_a_python_full_edit():
    edit = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(PythonFullStrategy, "edit", edit):
        for check, expected in (("warn", None), ("retry", AnglePolicy("retry")), ("off", AnglePolicy("off"))):
            with pytest.raises(RuntimeError, match="stop"):
                await render_geometry_diagram(
                    "relabel", previous_script=EDIT_BASE,
                    config=GeometryConfig(strategy="python_full", renderer="svg", angle_check=check),
                )
            assert edit.call_args.kwargs.get("angle_policy") == expected
