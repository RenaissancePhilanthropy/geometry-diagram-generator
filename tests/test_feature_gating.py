"""Feature-group gating (solids ticket 13): the enabled set on the config,
the registry's feature attribute, tagged prompt fragments, the sandbox
namespace by group, and the one post-parse check `require_features` wired into
the structured, recipe and Python scripting strategies. Compile and render
never gate. Group-specific names/fragments are TEST-ONLY fakes here."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams.config import GeometryConfig, resolve_config
from geometry_diagrams.features import (
    FEATURE_GROUPS, FeatureNotEnabledError, parse_features, require_features, tagged_fragment,
)
from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult, run_ir_pipeline
from geometry_diagrams.strategies.structured import MAX_RETRIES, StructureStrategy


def _prism_diagram() -> ir.DiagramIR:
    return ir.DiagramIR(
        define=[
            ir.PointFixed(id="O", x=0, y=0),
            ir.RectangularPrism(id="P", origin="O", length=4, width=3, height=2),
        ],
        render=[ir.Draw(obj="P")],
    )


def _plain_diagram() -> ir.DiagramIR:
    return ir.DiagramIR(define=[ir.PointFixed(id="A", x=0, y=0)], render=[ir.Draw(obj="A")])


# --- configuration -----------------------------------------------------------

def test_solids_is_registered_and_off_by_default(monkeypatch):
    monkeypatch.delenv("GEOMETRY_FEATURES", raising=False)
    assert "solids" in FEATURE_GROUPS
    assert GeometryConfig().features == frozenset()
    assert GeometryConfig.from_env().features == frozenset()


def test_from_env_reads_comma_separated_features(monkeypatch):
    monkeypatch.setenv("GEOMETRY_FEATURES", " solids , ")
    assert GeometryConfig.from_env().features == frozenset({"solids"})


def test_from_env_rejects_unknown_group(monkeypatch):
    monkeypatch.setenv("GEOMETRY_FEATURES", "bogus")
    with pytest.raises(ValueError, match="bogus"):
        GeometryConfig.from_env()


def test_resolve_config_override_and_inherit():
    base = GeometryConfig(features=frozenset({"solids"}))
    assert resolve_config(base).features == frozenset({"solids"})
    assert resolve_config(base, features=frozenset()).features == frozenset()
    assert resolve_config(GeometryConfig(), features="solids").features == frozenset({"solids"})


def test_parse_features_empty():
    assert parse_features("") == frozenset()
    assert parse_features(None) == frozenset()


def test_facade_passes_features_to_each_strategy():
    from geometry_diagrams.facade import _make_strategy

    cfg = GeometryConfig(strategy="recipe", features=frozenset({"solids"}))
    assert _make_strategy(cfg).features == frozenset({"solids"})
    cfg = GeometryConfig(strategy="python_full", features=frozenset({"solids"}))
    assert _make_strategy(cfg).features == frozenset({"solids"})
    assert _make_strategy(GeometryConfig(strategy="recipe")).features == frozenset()


# --- registry attribute ------------------------------------------------------

def test_registry_feature_attribute():
    prism = REGISTRY.get(ir.RectangularPrism(id="P", origin="O", length=1, width=1, height=1))
    assert prism.feature == "solids"
    for kind in ("polygon_exterior", "polygon_on_edge", "circle_tangent_at"):
        assert REGISTRY._by_kind[kind].feature is None


# --- require_features --------------------------------------------------------

def test_require_features_rejects_disabled_prism_with_actionable_message():
    with pytest.raises(FeatureNotEnabledError) as exc:
        require_features(_prism_diagram(), frozenset())
    msg = str(exc.value)
    assert "rectangular_prism" in msg and "solids" in msg and "GEOMETRY_FEATURES" in msg
    assert "'P'" in msg
    assert isinstance(exc.value, RuntimeError)  # existing retry paths catch it


def test_require_features_accepts_enabled_group_and_ungated_kinds():
    require_features(_prism_diagram(), frozenset({"solids"}))
    require_features(_plain_diagram(), frozenset())


# --- compile and render never gate ------------------------------------------

def test_prism_compiles_and_renders_with_solids_off():
    diagram = _prism_diagram()
    sym = compile_defs(diagram)
    assert "P_v000" in sym
    result = SVGRenderer().render(diagram, sym)
    assert "<svg" in result.output


@pytest.mark.asyncio
async def test_shared_pipeline_seam_gate_then_pipeline():
    diagram = _prism_diagram()
    with pytest.raises(FeatureNotEnabledError):
        require_features(diagram, frozenset())
    require_features(diagram, frozenset({"solids"}))
    result = await run_ir_pipeline(diagram, SVGRenderer())
    assert "<svg" in result.svg
    # the pipeline itself never consults the enabled set: it renders the same
    # diagram with no features anywhere in sight
    assert "P_v111" in result.sym_table


# --- prompt fragment tagging (test-only fragment) ----------------------------

def test_tagged_fragment_omitted_when_off_included_when_on():
    assert tagged_fragment("g", "TEXT", frozenset()) == ""
    assert tagged_fragment("g", "TEXT", frozenset({"other"})) == ""
    assert tagged_fragment("g", "TEXT", frozenset({"g"})) == "TEXT"


def test_python_full_instructions_include_tagged_fragment_only_when_enabled(monkeypatch):
    from geometry_diagrams.strategies import instructions_python_full as ipf

    monkeypatch.setitem(ipf.GROUPED_FRAGMENTS, "solids", "TEST-ONLY-SOLIDS-FRAGMENT")
    assert "TEST-ONLY-SOLIDS-FRAGMENT" not in ipf.build_python_full_instructions()
    assert "TEST-ONLY-SOLIDS-FRAGMENT" not in ipf.build_python_full_instructions(features=frozenset())
    assert "TEST-ONLY-SOLIDS-FRAGMENT" in ipf.build_python_full_instructions(features=frozenset({"solids"}))


def test_default_instructions_unchanged_by_features_machinery():
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    assert build_python_full_instructions(features=frozenset({"solids"})) == build_python_full_instructions()


# --- sandbox: namespace by group, payload ------------------------------------

def test_build_tool_names_adds_grouped_names_only_when_group_enabled():
    from geometry_diagrams.pydsl._sandbox_child import _build_tool_names

    fake = SimpleNamespace(__all__=["point"], COOKBOOK_NAMES=[], GROUPED_NAMES={"g": ["gated_fn"]})
    assert _build_tool_names(fake, False) == ["point"]
    assert _build_tool_names(fake, False, frozenset()) == ["point"]
    assert _build_tool_names(fake, False, frozenset({"other"})) == ["point"]
    assert _build_tool_names(fake, False, frozenset({"g"})) == ["point", "gated_fn"]


def test_real_pydsl_module_registers_solids_group():
    import geometry_diagrams.pydsl as pydsl

    assert "solids" in pydsl.GROUPED_NAMES
    for names in pydsl.GROUPED_NAMES.values():
        for n in names:
            assert hasattr(pydsl, n)


def test_run_script_sends_enabled_set_to_child():
    from geometry_diagrams.pydsl.sandbox import run_script

    child = (
        "import sys, json\n"
        "req = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'kind': 'ready', 'payload': None}), flush=True)\n"
        "print(json.dumps({'kind': 'error', 'payload': ['FEATURES=' + json.dumps(req['features']),"
        " 'runtime', 'FEATURES=' + json.dumps(req['features'])]}), flush=True)\n"
    )
    result = run_script("x", timeout_seconds=5.0, _child_argv=[sys.executable, "-c", child],
                        features=frozenset({"solids", "g"}))
    assert result.error == 'FEATURES=["g", "solids"]'
    result = run_script("x", timeout_seconds=5.0, _child_argv=[sys.executable, "-c", child])
    assert result.error == "FEATURES=[]"


# --- strategies --------------------------------------------------------------

def _raw_response(diagram: ir.DiagramIR) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 1, "output_tokens": 1}}
    return {"raw": raw, "parsed": diagram, "parsing_error": None}


def _mock_llm(responses: list):
    structured = MagicMock()
    structured.ainvoke = AsyncMock(side_effect=responses)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    return llm, structured


@pytest.mark.asyncio
async def test_structured_rejects_disabled_prism_then_retries_with_feedback():
    llm, structured = _mock_llm([_raw_response(_prism_diagram()), _raw_response(_plain_diagram())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        result = await StructureStrategy().run("a box", model="anthropic:claude-sonnet-4-6",
                                               renderer=SVGRenderer())
    assert "P_v000" not in result.sym_table  # the accepted attempt is the plain one
    assert result.retries == 1
    second_prompt = structured.ainvoke.call_args_list[1].args[0][1].content
    assert "rectangular_prism" in second_prompt and "solids" in second_prompt


@pytest.mark.asyncio
async def test_structured_exhausts_retries_when_prism_never_allowed():
    llm, _ = _mock_llm([_raw_response(_prism_diagram())] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        with pytest.raises(RuntimeError, match="solids"):
            await StructureStrategy().run("a box", renderer=SVGRenderer())


@pytest.mark.asyncio
async def test_structured_accepts_prism_when_solids_enabled():
    llm, _ = _mock_llm([_raw_response(_prism_diagram())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        result = await StructureStrategy(features=frozenset({"solids"})).run(
            "a box", renderer=SVGRenderer())
    assert result.retries == 0 and "P_v111" in result.sym_table


@pytest.mark.asyncio
async def test_structured_run_features_kwarg_overrides_strategy_default():
    llm, _ = _mock_llm([_raw_response(_prism_diagram())])
    with patch("geometry_diagrams.strategies.structured.get_chat_model", return_value=llm):
        result = await StructureStrategy().run("a box", renderer=SVGRenderer(),
                                               features=frozenset({"solids"}))
    assert "P_v111" in result.sym_table


@pytest.mark.asyncio
async def test_recipe_node_rejects_disabled_prism_and_accepts_enabled():
    from geometry_diagrams.strategies.recipe import _run_recipe_pipeline_node
    from geometry_diagrams.strategies.recipe import RecipeMetadata

    def state(features):
        return {"dsl": MagicMock(), "renderer": SVGRenderer(), "recipe_metadata": RecipeMetadata(),
                "attempt": 1, "features": features}

    with patch("geometry_diagrams.strategies.recipe.lower_to_ir", return_value=_prism_diagram()):
        off = await _run_recipe_pipeline_node(state(frozenset()))
        on = await _run_recipe_pipeline_node(state(frozenset({"solids"})))
    assert off["result"] is None and off["dsl"] is None
    assert "rectangular_prism" in off["last_error"] and "solids" in off["last_error"]
    assert on["result"] is not None


@pytest.mark.asyncio
async def test_recipe_strategy_threads_features_into_state():
    from geometry_diagrams.strategies.recipe import RecipeStrategy

    seen = {}

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            seen.update(state)
            return {"result": None, "last_error": "x"}

    with patch("geometry_diagrams.strategies.recipe._build_recipe_graph", return_value=FakeGraph()):
        with pytest.raises(RuntimeError):
            await RecipeStrategy(features=frozenset({"solids"})).run("x")
    assert seen["features"] == frozenset({"solids"})


@pytest.mark.asyncio
async def test_python_full_node_rejects_disabled_prism_and_forwards_features_to_sandbox():
    from geometry_diagrams.pydsl.sandbox import ScriptResult
    from geometry_diagrams.strategies.python_full import (
        PythonFullAttemptTrace, PythonFullMetadata, _run_script_node,
    )

    def state(features):
        return {"script": "x", "renderer": SVGRenderer(), "attempt": 0, "features": features,
                "metadata": PythonFullMetadata(attempt_traces=[
                    PythonFullAttemptTrace(attempt=0, script="x", error=None, stage="generation")])}

    fake = ScriptResult(diagram_ir=_prism_diagram(), error=None, error_type=None)
    with patch("geometry_diagrams.strategies.python_full.run_script", return_value=fake) as rs:
        off = await _run_script_node(state(frozenset()))
        on = await _run_script_node(state(frozenset({"solids"})))
    assert off["result"] is None
    assert "rectangular_prism" in off["last_error"] and "solids" in off["last_error"]
    assert on["result"] is not None
    assert [c.kwargs["features"] for c in rs.call_args_list] == [frozenset(), frozenset({"solids"})]


@pytest.mark.asyncio
async def test_python_full_prompt_gets_features_from_state(monkeypatch):
    from geometry_diagrams.strategies import instructions_python_full as ipf
    from geometry_diagrams.strategies import python_full as pf

    monkeypatch.setitem(ipf.GROUPED_FRAGMENTS, "solids", "TEST-ONLY-SOLIDS-FRAGMENT")
    prompts = []
    llm = MagicMock()
    llm.with_structured_output = MagicMock(side_effect=RuntimeError("stop"))
    real = pf.make_system_message
    with patch.object(pf, "get_chat_model", return_value=llm), \
         patch.object(pf, "make_system_message", side_effect=lambda t, **k: prompts.append(t) or real(t, **k)):
        for feats in (frozenset(), frozenset({"solids"})):
            await pf._generate_script_node({
                "prompt": "p", "model_id": "anthropic:claude-sonnet-4-6", "attempt": 0, "last_error": "",
                "metadata": pf.PythonFullMetadata(), "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "features": feats,
            })
    assert "TEST-ONLY-SOLIDS-FRAGMENT" not in prompts[0]
    assert "TEST-ONLY-SOLIDS-FRAGMENT" in prompts[1]
