# tests/test_stateless_edit.py
"""Stateless edit entry points: StructureStrategy.run(previous_ir=...),
PythonFullStrategy.edit(...), and the facade routing of previous_dsl /
previous_script / previous_ir to the strategy that owns each.

No LLM calls or renderer container required — all external calls are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from geometry_diagrams.config import GeometryConfig
from geometry_diagrams.facade import (
    DiagramResult,
    _make_strategy,
    edit_geometry_diagram,
    render_geometry_diagram,
)
from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies import structured as st
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.strategies.python_full import PythonFullStrategy
from geometry_diagrams.strategies.recipe import RecipeStrategy
from geometry_diagrams.strategies.structured import StructureStrategy


@pytest.fixture(autouse=True)
def reset_tracing(monkeypatch):
    # Other modules in the suite can load real LANGFUSE_* settings into the
    # process env; without this the env handler would land in every config.
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    from geometry_diagrams.util import tracing
    tracing._reset()
    yield
    tracing._reset()


def _ir() -> DiagramIR:
    return DiagramIR(define=[], render=[])


def _result(script: str = "", svg: str = "<svg/>") -> StructuredRunResult:
    return StructuredRunResult(
        diagram_ir=_ir(), tikz="", svg=svg, sym_table={}, sym_full={}, script=script,
        entity_manifest={"named": [], "anonymous": []},
    )


# ---------------------------------------------------------------------------
# StructureStrategy.run(previous_ir=...)
# ---------------------------------------------------------------------------

class _FakeGraph:
    def __init__(self, result):
        self.result = result
        self.state = None
        self.config = None

    async def ainvoke(self, state, config=None):
        self.state = state
        self.config = config
        return {"result": self.result, "input_tokens": 1, "output_tokens": 2, "cost_usd": 0.0}


@pytest.mark.asyncio
async def test_structured_run_without_previous_ir_sends_bare_prompt(monkeypatch):
    graph = _FakeGraph(_result())
    monkeypatch.setattr(st, "_build_structured_graph", lambda: graph)
    await StructureStrategy().run("draw a triangle")
    assert graph.state["prompt"] == "draw a triangle"


@pytest.mark.asyncio
@pytest.mark.parametrize("as_dict", [True, False])
async def test_structured_run_previous_ir_is_embedded_in_prompt(monkeypatch, as_dict):
    graph = _FakeGraph(_result())
    monkeypatch.setattr(st, "_build_structured_graph", lambda: graph)
    prior = _ir()
    await StructureStrategy().run(
        "make it bigger", previous_ir=prior.model_dump() if as_dict else prior,
    )
    prompt = graph.state["prompt"]
    assert prompt.startswith("make it bigger")
    assert prior.model_dump_json(indent=2) in prompt


@pytest.mark.asyncio
async def test_structured_run_invalid_previous_ir_raises_value_error(monkeypatch):
    monkeypatch.setattr(st, "_build_structured_graph", lambda: _FakeGraph(_result()))
    with pytest.raises(ValueError, match="previous_ir is not a valid DiagramIR"):
        await StructureStrategy().run("edit", previous_ir={"define": "nope"})


# ---------------------------------------------------------------------------
# PythonFullStrategy.edit(...)
# ---------------------------------------------------------------------------

PREV = "a = point(0, 0)\ndraw_points(a)\n"


@pytest.mark.asyncio
async def test_python_full_edit_full_rewrite_prompt_carries_script_and_manifest(monkeypatch):
    rebuilt = _result(PREV)
    rebuilt.entity_manifest = {"named": [{"name": "a", "type": "point_fixed"}], "anonymous": []}
    baseline_calls = []

    async def fake_from_script(script, renderer, *a, **kw):
        baseline_calls.append(script)
        return rebuilt

    prompts = []

    async def fake_run(self, prompt, model="m", renderer=None, sandbox_timeout_seconds=2.5, **kw):
        prompts.append(prompt)
        return _result("a = point(0, 1)\n")

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)

    out = await PythonFullStrategy().edit(
        "move a up", PREV, model="m", edit_generation_mode="full_rewrite",
    )
    assert baseline_calls == [PREV]  # previous script re-run to rebuild the manifest
    assert out.script == "a = point(0, 1)\n"
    assert "move a up" in prompts[0] and PREV in prompts[0]
    assert '"point_fixed"' in prompts[0]


@pytest.mark.asyncio
async def test_python_full_edit_search_replace_applies_blocks_to_previous_script(monkeypatch):
    seen_scripts = []

    async def fake_from_script(script, renderer, *a, **kw):
        seen_scripts.append(script)
        return _result(script)

    async def fake_gen(prompt, model):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 11, 7, 0.01

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)

    await PythonFullStrategy().edit("move a up", PREV, model="m")  # default mode
    assert seen_scripts == [PREV, "a = point(0, 5)\ndraw_points(a)\n"]


@pytest.mark.asyncio
async def test_python_full_edit_previous_script_that_fails_raises_value_error(monkeypatch):
    async def boom(script, renderer, *a, **kw):
        raise RuntimeError("patch-mode script failed: NameError")

    monkeypatch.setattr(pf, "_run_from_script", boom)
    with pytest.raises(ValueError, match="previous_script did not run"):
        await PythonFullStrategy().edit("x", "garbage(", model="m")


@pytest.mark.asyncio
async def test_python_full_edit_error_message_drops_internal_patch_mode_prefix(monkeypatch):
    async def boom(script, renderer, *a, **kw):
        raise RuntimeError("patch-mode script failed: NameError: zz")

    monkeypatch.setattr(pf, "_run_from_script", boom)
    with pytest.raises(ValueError) as exc:
        await PythonFullStrategy().edit("x", "zz", model="m")
    assert str(exc.value) == "previous_script did not run: NameError: zz"


@pytest.mark.asyncio
async def test_python_full_edit_baseline_uses_svg_renderer_edit_uses_callers(monkeypatch):
    from geometry_diagrams.ir.renderer import SVGRenderer

    renderers = []

    async def fake_from_script(script, renderer, *a, **kw):
        renderers.append(renderer)
        return _result(script)

    async def fake_gen(prompt, model):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)

    caller_renderer = MagicMock(name="tikz_like")
    await PythonFullStrategy().edit("up", PREV, model="m", renderer=caller_renderer)
    assert isinstance(renderers[0], SVGRenderer)  # baseline: never the caller's (TikZ) renderer
    assert renderers[1] is caller_renderer        # the edit itself renders with it


@pytest.mark.asyncio
async def test_python_full_edit_rejects_blank_previous_script():
    with pytest.raises(ValueError, match="previous_script"):
        await PythonFullStrategy().edit("x", "   \n", model="m")


# ---------------------------------------------------------------------------
# Facade routing
# ---------------------------------------------------------------------------

def test_make_strategy_structured():
    assert isinstance(_make_strategy(GeometryConfig(strategy="structured")), StructureStrategy)


@pytest.mark.asyncio
async def test_facade_python_full_previous_script_calls_edit_with_config(monkeypatch):
    captured = {}

    async def fake_edit(self, request, previous_script, **kw):
        captured.update(request=request, previous_script=previous_script, **kw)
        return _result("new script")

    async def no_run(*a, **kw):
        raise AssertionError("run() must not be called on an edit")

    monkeypatch.setattr(PythonFullStrategy, "edit", fake_edit)
    monkeypatch.setattr(PythonFullStrategy, "run", no_run)

    cfg = GeometryConfig(
        strategy="python_full", renderer="svg", edit_generation_mode="hashline",
        hash_algorithm="xxhash", sandbox_timeout_seconds=4.0,
    )
    res = await render_geometry_diagram("move it", config=cfg, previous_script=PREV)
    assert captured["request"] == "move it"
    assert captured["previous_script"] == PREV
    assert captured["edit_generation_mode"] == "hashline"
    assert captured["hash_algorithm"] == "xxhash"
    assert captured["sandbox_timeout_seconds"] == 4.0
    assert res.script == "new script"


@pytest.mark.asyncio
async def test_facade_structured_generates_and_edits(monkeypatch):
    captured = {}

    async def fake_run(self, prompt, model=None, renderer=None, previous_ir=None, **kw):
        captured["previous_ir"] = previous_ir
        return _result()

    monkeypatch.setattr(StructureStrategy, "run", fake_run)
    cfg = GeometryConfig(strategy="structured", renderer="svg")

    res = await render_geometry_diagram("a triangle", config=cfg)
    assert captured["previous_ir"] is None
    assert isinstance(res, DiagramResult)
    assert res.diagram_ir == _ir().model_dump()
    assert res.dsl is None and res.recipes is None and res.script is None

    prior = res.diagram_ir
    await edit_geometry_diagram("bigger", config=cfg, previous_ir=prior)
    assert captured["previous_ir"] == prior


@pytest.mark.asyncio
async def test_facade_edit_geometry_diagram_python_full_previous_script(monkeypatch):
    captured = {}

    async def fake_edit(self, request, previous_script, **kw):
        captured["previous_script"] = previous_script
        return _result("s")

    monkeypatch.setattr(PythonFullStrategy, "edit", fake_edit)
    await edit_geometry_diagram(
        "x", config=GeometryConfig(strategy="python_full", renderer="svg"), previous_script=PREV,
    )
    assert captured["previous_script"] == PREV


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy, kwargs, match",
    [
        ("recipe", {"previous_script": "x"}, "previous_script is only supported"),
        ("recipe", {"previous_ir": {}}, "previous_ir is only supported"),
        ("python_full", {"previous_dsl": {}}, "previous_dsl is only supported"),
        ("python_full", {"previous_ir": {}}, "previous_ir is only supported"),
        ("structured", {"previous_dsl": {}}, "previous_dsl is only supported"),
        ("structured", {"previous_script": "x"}, "previous_script is only supported"),
        ("recipe", {"previous_dsl": {}, "previous_script": "x"}, "at most one"),
    ],
)
async def test_facade_rejects_previous_state_for_the_wrong_strategy(strategy, kwargs, match):
    with pytest.raises(ValueError, match=match):
        await render_geometry_diagram("edit", strategy=strategy, renderer="svg", **kwargs)


@pytest.mark.asyncio
async def test_facade_edit_requires_exactly_one_previous():
    with pytest.raises(ValueError, match="exactly one"):
        await edit_geometry_diagram("x", config=GeometryConfig(renderer="svg"))
    with pytest.raises(ValueError, match="exactly one"):
        await edit_geometry_diagram(
            "x", {}, config=GeometryConfig(renderer="svg"), previous_script="s",
        )


@pytest.mark.asyncio
async def test_facade_recipe_edit_still_passes_previous_dsl(monkeypatch):
    captured = {}

    async def fake_run(self, prompt, model=None, renderer=None, previous_dsl=None, **kw):
        captured["previous_dsl"] = previous_dsl
        return _result()

    monkeypatch.setattr(RecipeStrategy, "run", fake_run)
    await edit_geometry_diagram("x", {"mode": "abstract"}, config=GeometryConfig(renderer="svg"))
    assert captured["previous_dsl"] == {"mode": "abstract"}


# ---------------------------------------------------------------------------
# run_config / callbacks reach python_full and structured
# ---------------------------------------------------------------------------

class _Handler:
    """Stands in for a LangChain callback handler (compared by identity)."""


def _cbs(config):
    return list((config or {}).get("callbacks") or [])


@pytest.mark.asyncio
async def test_structured_run_threads_config_and_callbacks_to_the_graph(monkeypatch):
    graph = _FakeGraph(_result())
    monkeypatch.setattr(st, "_build_structured_graph", lambda: graph)
    cb = _Handler()
    await StructureStrategy().run("x", config={"tags": ["t"]}, callbacks=[cb])
    assert graph.config["tags"] == ["t"]
    assert cb in _cbs(graph.config)


@pytest.mark.asyncio
async def test_python_full_run_threads_config_and_callbacks_to_the_graph(monkeypatch):
    graph = _FakeGraph(_result("s"))
    monkeypatch.setattr(pf, "_build_python_full_graph", lambda **kw: graph)
    cb = _Handler()
    await PythonFullStrategy().run("x", config={"tags": ["t"]}, callbacks=[cb])
    assert graph.config["tags"] == ["t"]
    assert cb in _cbs(graph.config)


@pytest.mark.asyncio
async def test_python_full_edit_threads_config_to_the_edit_generation_call(monkeypatch):
    async def fake_from_script(script, renderer, *a, **kw):
        return _result(script)

    seen = {}

    async def fake_gen(prompt, model, config=None, **kw):
        seen["config"] = config
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    cb = _Handler()
    await PythonFullStrategy().edit("up", PREV, model="m", config={"tags": ["t"]}, callbacks=[cb])
    assert seen["config"]["tags"] == ["t"]
    assert cb in _cbs(seen["config"])


@pytest.mark.asyncio
async def test_python_full_edit_full_rewrite_threads_config_to_run(monkeypatch):
    async def fake_from_script(script, renderer, *a, **kw):
        return _result(script)

    seen = {}

    async def fake_run(self, prompt, model="m", renderer=None, sandbox_timeout_seconds=2.5,
                       config=None, callbacks=None, **kw):
        seen.update(config=config, callbacks=callbacks)
        return _result("s")

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    cb = _Handler()
    await PythonFullStrategy().edit(
        "up", PREV, model="m", edit_generation_mode="full_rewrite", callbacks=[cb],
    )
    assert cb in _cbs(seen["config"])


class _FakeLLM:
    def __init__(self):
        self.configs = []

    async def ainvoke(self, messages, config=None, **kw):
        self.configs.append(config)
        return MagicMock(content="<<<<<<< SEARCH\na\n=======\nb\n>>>>>>> REPLACE")


@pytest.mark.asyncio
async def test_search_replace_generation_passes_config_to_the_llm(monkeypatch):
    llm = _FakeLLM()
    monkeypatch.setattr(pf, "get_chat_model", lambda *a, **kw: llm)
    monkeypatch.setattr(pf, "extract_usage", lambda r: (0, 0))
    monkeypatch.setattr(pf, "extract_cost", lambda r: None)
    monkeypatch.setattr(pf, "extract_text", lambda c: c)
    cfg = {"tags": ["t"]}
    await pf.generate_search_replace("p", "m", config=cfg)
    assert llm.configs == [cfg]


@pytest.mark.asyncio
@pytest.mark.parametrize("fn_name, parsed", [
    ("_generate_patch", MagicMock(patch="p")),
    ("_generate_hashline_ops", MagicMock(ops=[])),
    ("_generate_line_number_ops", MagicMock(ops=[])),
])
async def test_structured_edit_generators_pass_config_to_the_llm(monkeypatch, fn_name, parsed):
    seen = []

    class _Structured:
        async def ainvoke(self, messages, config=None, **kw):
            seen.append(config)
            return {"raw": None, "parsed": parsed, "parsing_error": None}

    monkeypatch.setattr(pf, "get_chat_model", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(pf, "bind_structured_output_for_model", lambda *a, **kw: _Structured())
    cfg = {"tags": ["t"]}
    await getattr(pf, fn_name)("p", "m", config=cfg)
    assert seen == [cfg]


@pytest.mark.asyncio
async def test_facade_forwards_run_config_and_callbacks_to_every_strategy(monkeypatch):
    seen = {}

    def rec(name):
        async def fake(self, *args, **kw):
            seen[name] = (kw.get("config"), kw.get("callbacks"))
            return _result("s")
        return fake

    monkeypatch.setattr(StructureStrategy, "run", rec("structured"))
    monkeypatch.setattr(PythonFullStrategy, "run", rec("python_full"))
    monkeypatch.setattr(PythonFullStrategy, "edit", rec("python_full_edit"))
    monkeypatch.setattr(RecipeStrategy, "run", rec("recipe"))
    rc, cbs = {"tags": ["t"]}, [_Handler()]
    for strategy, extra in (
        ("structured", {}), ("python_full", {}), ("recipe", {}),
        ("python_full", {"previous_script": PREV}),
    ):
        await render_geometry_diagram(
            "x", strategy=strategy, renderer="svg", run_config=rc, callbacks=cbs, **extra,
        )
    assert seen["structured"] == (rc, cbs)
    assert seen["python_full"] == (rc, cbs)
    assert seen["python_full_edit"] == (rc, cbs)
    assert seen["recipe"] == (rc, cbs)


# ---------------------------------------------------------------------------
# cost and warnings on DiagramResult
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("strategy, extra", [
    ("structured", {}), ("python_full", {}), ("python_full", {"previous_script": PREV}), ("recipe", {}),
])
async def test_diagram_result_carries_cost_and_warnings(monkeypatch, strategy, extra):
    res = _result("s")
    res.cost_usd = 0.0123
    res.warnings = ["prism label 4 ft does not match its true length"]

    async def fake(self, *a, **kw):
        return res

    for cls, name in ((StructureStrategy, "run"), (PythonFullStrategy, "run"),
                      (PythonFullStrategy, "edit"), (RecipeStrategy, "run")):
        monkeypatch.setattr(cls, name, fake)
    out = await render_geometry_diagram("x", strategy=strategy, renderer="svg", **extra)
    assert out.cost_usd == 0.0123
    assert out.warnings == ["prism label 4 ft does not match its true length"]


@pytest.mark.asyncio
async def test_diagram_result_cost_is_none_when_unreported_and_warnings_default_empty(monkeypatch):
    async def fake(self, *a, **kw):
        return _result("s")  # cost_usd defaults to None

    monkeypatch.setattr(StructureStrategy, "run", fake)
    out = await render_geometry_diagram("x", strategy="structured", renderer="svg")
    assert out.cost_usd is None  # unknown, not free
    assert out.warnings == []


# ---------------------------------------------------------------------------
# Edit contract: persisted script round-trips; gated features
# ---------------------------------------------------------------------------

SOLIDS = frozenset({"solids"})
SOLIDS_SCRIPT = "o = point(0, 0)\nb = prism(o, 4, 3, 2)\ndraw(b)\n"


@pytest.mark.asyncio
async def test_solids_script_round_trips_through_previous_script(monkeypatch):
    """The `script` a result persists is enough to edit a solids diagram later,
    in a fresh strategy, with the real sandbox and SVG renderer."""
    from geometry_diagrams.ir.renderer import SVGRenderer

    first = await pf._run_from_script(
        SOLIDS_SCRIPT, SVGRenderer(), features=SOLIDS, sandbox_timeout_seconds=30,
    )

    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "prism(o, 4, 3, 2)", "new_string": "prism(o, 4, 3, 5)"}], 11, 7, 0.01

    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    edited = await PythonFullStrategy(features=SOLIDS).edit(
        "make it taller", first.script, model="m", renderer=SVGRenderer(),
        sandbox_timeout_seconds=30,
    )
    assert "prism(o, 4, 3, 5)" in edited.script
    assert edited.svg != first.svg
    # the real _run_from_script stamps the edit-generation call's usage on the result
    assert (edited.input_tokens, edited.output_tokens, edited.cost_usd) == (11, 7, 0.01)


@pytest.mark.asyncio
async def test_editing_a_solids_script_without_the_feature_explains_why():
    from geometry_diagrams.ir.renderer import SVGRenderer

    with pytest.raises(ValueError) as exc:
        await PythonFullStrategy().edit(
            "x", SOLIDS_SCRIPT, model="m", renderer=SVGRenderer(), sandbox_timeout_seconds=30,
        )
    msg = str(exc.value)
    assert "previous_script did not run" in msg
    assert "solids" in msg and "GEOMETRY_FEATURES" in msg
    assert "prism" in msg


@pytest.mark.asyncio
async def test_a_failing_script_with_no_gated_names_gets_no_feature_hint():
    from geometry_diagrams.ir.renderer import SVGRenderer

    with pytest.raises(ValueError) as exc:
        await PythonFullStrategy().edit(
            "x", "a = undefined_name(1)\n", model="m", renderer=SVGRenderer(),
            sandbox_timeout_seconds=30,
        )
    assert "GEOMETRY_FEATURES" not in str(exc.value)


@pytest.mark.asyncio
async def test_a_stray_gated_word_in_a_comment_gets_no_feature_hint():
    from geometry_diagrams.ir.renderer import SVGRenderer

    with pytest.raises(ValueError) as exc:
        await PythonFullStrategy().edit(
            "x", "# stack the labels neatly\na = undefined_name(1)\n", model="m",
            renderer=SVGRenderer(), sandbox_timeout_seconds=30,
        )
    assert "GEOMETRY_FEATURES" not in str(exc.value)


@pytest.mark.asyncio
async def test_a_generated_edit_that_fails_to_run_is_not_a_previous_script_error(monkeypatch):
    """Pins the error-type contract: only bad INPUT is 'previous_script did not run'."""
    calls = []

    async def fake_from_script(script, renderer, *a, **kw):
        calls.append(script)
        if len(calls) == 1:
            return _result(script)  # baseline ok
        raise RuntimeError("patch-mode script failed: NameError: zz")

    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "point(0, 0)", "new_string": "zz(0, 0)"}], 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    with pytest.raises(RuntimeError, match="NameError: zz") as exc:
        await PythonFullStrategy().edit("x", PREV, model="m")
    assert "previous_script did not run" not in str(exc.value)


@pytest.mark.asyncio
async def test_python_full_edit_passes_the_sandbox_timeout_to_the_baseline(monkeypatch):
    seen = []

    async def fake_from_script(script, renderer, *a, **kw):
        seen.append(kw.get("sandbox_timeout_seconds", a[3] if len(a) > 3 else None))
        return _result(script)

    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    await PythonFullStrategy().edit("x", PREV, model="m", sandbox_timeout_seconds=7.5)
    assert seen[0] == 7.5  # baseline rerun
    assert seen[1] == 7.5  # the edit's own run


@pytest.mark.asyncio
@pytest.mark.parametrize("mode, gen_name, apply_name", [
    ("patch", "_generate_patch", "apply_script_patch"),
    ("hashline", "_generate_hashline_ops", "apply_hashline_ops"),
    ("line_number", "_generate_line_number_ops", "apply_line_number_ops"),
    ("search_replace", "generate_search_replace", "apply_search_replace"),
])
async def test_every_edit_mode_threads_config_through_apply_edit(monkeypatch, mode, gen_name, apply_name):
    async def fake_from_script(script, renderer, *a, **kw):
        return _result(script)

    seen = {}

    async def fake_gen(prompt, model, config=None, **kw):
        seen["config"] = config
        return ("patch-text" if mode == "patch" else []), 0, 0, None

    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, gen_name, fake_gen)
    monkeypatch.setattr(pf, apply_name, lambda script, *a, **kw: script)
    cb = _Handler()
    await PythonFullStrategy().edit("x", PREV, model="m", edit_generation_mode=mode, callbacks=[cb])
    assert cb in _cbs(seen["config"])


# --- usage accounting across a locality retry ---

def test_add_usage_sums_tokens_and_cost_and_keeps_unknown_cost_none():
    a, b = _result("a"), _result("b")
    a.input_tokens, a.output_tokens, a.cost_usd = 10, 5, 0.01
    b.input_tokens, b.output_tokens, b.cost_usd = 20, 6, 0.02
    out = pf._add_usage(a, b)
    assert (out.input_tokens, out.output_tokens) == (30, 11)
    assert out.cost_usd == pytest.approx(0.03)

    c, d = _result("c"), _result("d")
    assert pf._add_usage(c, d).cost_usd is None  # neither reported: unknown, not free
    e, f = _result("e"), _result("f")
    f.cost_usd = 0.5
    assert pf._add_usage(e, f).cost_usd == 0.5


@pytest.mark.asyncio
async def test_locality_retry_bills_both_generation_calls(monkeypatch):
    gens = iter([(11, 1, 0.01), (22, 2, 0.02)])

    async def fake_gen(prompt, model, **kw):
        return [{"old_string": "point(0, 0)", "new_string": "point(0, 5)"}], *next(gens)

    async def fake_from_script(script, renderer, in_tok=0, out_tok=0, cost=None, *a, **kw):
        r = _result(script)
        r.input_tokens, r.output_tokens, r.cost_usd = in_tok, out_tok, cost
        return r

    verdicts = iter([
        MagicMock(unmatched_old_names={"a"}, violations=[]),  # first edit: flagged
        MagicMock(unmatched_old_names=set(), violations=[]),   # retry: clean
    ])
    monkeypatch.setattr(pf, "_run_from_script", fake_from_script)
    monkeypatch.setattr(pf, "generate_search_replace", fake_gen)
    monkeypatch.setattr(pf, "check_edit_locality", lambda *a, **kw: next(verdicts, MagicMock(
        unmatched_old_names=set(), violations=[])))

    # baseline is built with in_tok=0; skip it by feeding two generations to the two edit runs
    out = await PythonFullStrategy().edit(
        "x", PREV, model="m", retry_on_locality_violation=True,
    )
    assert out.input_tokens == 33 and out.output_tokens == 3
    assert out.cost_usd == pytest.approx(0.03)
