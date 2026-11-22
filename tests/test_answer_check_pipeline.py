"""answer_check wiring: pipeline modes, config, every strategy, python_full edits, verify."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from geometry_diagrams import GeometryConfig, render_geometry_diagram, verify_geometry_diagram
from geometry_diagrams.config import resolve_config
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import run_script
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies.ir_pipeline import PipelineError, run_ir_pipeline
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from geometry_diagrams.strategies.structured import StructureStrategy

TRI = """
canvas((-2, 12), (-2, 10))
a = point(0, 6); b = point(0, 0); c = point(8, 0)
t = triangle(a, b, c); draw(t)
a.label("A"); b.label("B"); c.label("C")
t.side(a, b).label("6"); t.side(b, c).label("8")
"""
LEAK = TRI + 't.side(a, c).label("AC = 10")\n'
CLEAN = TRI + 't.side(a, c).label("?")\n'
REQUEST = "In right triangle ABC, AB = 6 and BC = 8. Find the hypotenuse AC."


def _ir(script: str):
    result = run_script(script, timeout_seconds=60)
    assert result.error is None, result.error
    return result.diagram_ir


def _run(script: str, **kwargs):
    return asyncio.run(run_ir_pipeline(_ir(script), SVGRenderer(), **kwargs))


# --- the pipeline -------------------------------------------------------------------------

def test_warn_is_the_default_and_reaches_the_warnings():
    result = _run(LEAK, request_text=REQUEST)
    assert any('"AC = 10"' in w for w in result.warnings) and "<svg" in result.svg


def test_a_clean_figure_has_no_answer_warning():
    assert not any("request does not state" in w for w in _run(CLEAN, request_text=REQUEST).warnings)


def test_without_a_request_the_audit_does_not_run():
    assert not any("request does not state" in w for w in _run(LEAK).warnings)


def test_off_skips_the_audit():
    result = _run(LEAK, request_text=REQUEST, answer_check="off")
    assert not any("request does not state" in w for w in result.warnings)


def test_retry_fails_the_attempt_with_the_finding():
    with pytest.raises(PipelineError, match="request does not state") as info:
        _run(LEAK, request_text=REQUEST, answer_check="retry")
    assert any('"AC = 10"' in w for w in info.value.warnings)


def test_retry_passes_a_clean_figure():
    assert _run(CLEAN, request_text=REQUEST, answer_check="retry").svg


# --- config -------------------------------------------------------------------------------

def test_config_field_env_and_resolve(monkeypatch):
    monkeypatch.delenv("GEOMETRY_ANSWER_CHECK", raising=False)
    assert GeometryConfig.from_env().answer_check == "warn"
    monkeypatch.setenv("GEOMETRY_ANSWER_CHECK", "RETRY")
    assert GeometryConfig.from_env().answer_check == "retry"
    assert resolve_config(GeometryConfig(), answer_check="off").answer_check == "off"
    assert resolve_config(GeometryConfig(answer_check="retry")).answer_check == "retry"


def test_a_bad_mode_is_rejected_where_it_is_read(monkeypatch):
    monkeypatch.setenv("GEOMETRY_ANSWER_CHECK", "loud")
    with pytest.raises(ValueError, match="answer_check"):
        GeometryConfig.from_env()
    with pytest.raises(ValueError, match="answer_check"):
        resolve_config(GeometryConfig(), answer_check="loud")


@pytest.mark.asyncio
@pytest.mark.parametrize("name,cls", [("python_full", PythonFullStrategy), ("recipe", RecipeStrategy),
                                      ("structured", StructureStrategy)])
async def test_facade_passes_a_non_default_mode_to_every_strategy(name, cls):
    run = AsyncMock(side_effect=RuntimeError("stop"))
    with patch.object(cls, "run", run):
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram("a triangle", config=GeometryConfig(strategy=name, renderer="svg"))
        assert "answer_check" not in run.call_args.kwargs  # the default keeps the call shape
        with pytest.raises(RuntimeError, match="stop"):
            await render_geometry_diagram(
                "a triangle", config=GeometryConfig(strategy=name, renderer="svg"), answer_check="retry")
        assert run.call_args.kwargs["answer_check"] == "retry"


# --- python_full: retry and edits ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_python_full_retries_a_leaked_answer_with_the_finding_in_the_next_prompt():
    from geometry_diagrams.strategies.python_full import PydslScriptOutput
    from tests.test_strategy_robustness import _structured_llm

    llm = _structured_llm([PydslScriptOutput(script=LEAK), PydslScriptOutput(script=CLEAN)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm):
        result = await PythonFullStrategy().run(
            REQUEST, model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(), answer_check="retry")
    assert result.retries == 1 and '"?"' in result.script
    second_prompt = llm.with_structured_output.return_value.ainvoke.call_args_list[1].args[0][1].content
    assert "request does not state" in second_prompt


def test_the_request_is_the_original_not_the_advisory_extended_prompt():
    """Numbers an advisory step adds to the prompt are not numbers the request states."""
    from geometry_diagrams.strategies.python_full import PydslScriptOutput
    from tests.test_strategy_robustness import _structured_llm

    llm = _structured_llm([PydslScriptOutput(script=LEAK)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=llm):
        result = asyncio.run(PythonFullStrategy().run(
            REQUEST, model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer(),
            precomputed_advisory_context="the hypotenuse is 10"))
    assert any('"AC = 10"' in w for w in result.warnings)


def test_an_edit_counts_the_numbers_already_in_the_stored_script_as_stated(monkeypatch):
    stored = LEAK  # the stored figure already shows "AC = 10"

    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "AC = 10", "new_string": "AC = 10 cm"}], 1, 1, None

    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    result = asyncio.run(PythonFullStrategy().edit(
        "add the unit", stored, model="m", renderer=SVGRenderer(), answer_check="retry"))
    assert "10 cm" in result.script


def test_an_edit_that_adds_a_new_unstated_number_is_held_to_retry(monkeypatch):
    async def fake_gen(prompt, model, **kw):
        return [{"old_string": 't.side(a, c).label("?")', "new_string": 't.side(a, c).label("AC = 10")'}], 1, 1, None

    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    with pytest.raises(RuntimeError, match="request does not state"):
        asyncio.run(PythonFullStrategy().edit(
            "show the answer", CLEAN, model="m", renderer=SVGRenderer(), answer_check="retry"))


# --- verify -------------------------------------------------------------------------------------------

def test_verify_reports_answer_findings_only_with_a_request():
    ir_dict = asyncio.run(run_ir_pipeline(_ir(LEAK), SVGRenderer())).diagram_ir.model_dump()
    assert verify_geometry_diagram(ir_dict)["answer_findings"] == []
    report = verify_geometry_diagram(ir_dict, request=REQUEST)
    (finding,) = report["answer_findings"]
    assert finding["text"] == "AC = 10" and 10.0 in finding["numbers"]
    assert report["ok"] is True  # a heuristic: it does not decide ok
    assert any('"AC = 10"' in w for w in report["warnings"])
