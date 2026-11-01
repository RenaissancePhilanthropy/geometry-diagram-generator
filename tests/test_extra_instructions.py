"""extra_instructions: appended to every strategy's generation system prompt (render
and edit), never to the user message or the recipe selector; None/empty changes
nothing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from geometry_diagrams import GeometryConfig, edit_geometry_diagram, render_geometry_diagram
from geometry_diagrams.config import resolve_config
from geometry_diagrams.ir.ir import DiagramIR
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.strategies import python_full as pf
from geometry_diagrams.strategies import recipe as recipe_mod
from geometry_diagrams.strategies import structured as structured_mod
from geometry_diagrams.strategies.base import EXTRA_INSTRUCTIONS_HEADING, append_extra_instructions
from geometry_diagrams.strategies.instructions import RECIPE_GENERATION_SYSTEM, build_structured_instructions
from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions
from geometry_diagrams.strategies.llm import extract_text
from geometry_diagrams.strategies.python_full import PydslScriptOutput
from tests.test_strategy_robustness import VALID_SCRIPT, _fake_result, _structured_llm

EXTRA = "Always use the letter Q for the first point."
MODEL = "anthropic:claude-sonnet-4-6"


@pytest.fixture(autouse=True)
def no_env_tracing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    from geometry_diagrams.util import tracing

    tracing._reset()
    yield
    tracing._reset()


def _cfg(strategy: str, **kw) -> GeometryConfig:
    return GeometryConfig(strategy=strategy, renderer="svg", model=MODEL, **kw)


def _structured_messages(llm: MagicMock) -> list:
    return llm.with_structured_output.return_value.ainvoke.call_args.args[0]


def _system_text(messages: list) -> str:
    return extract_text(messages[0].content)


# --- helper ------------------------------------------------------------------


@pytest.mark.parametrize("extra", [None, "", "   \n"])
def test_helper_is_identity_without_extra(extra):
    assert append_extra_instructions("base\n", extra) == "base\n"


def test_helper_appends_a_delimited_trailing_section():
    out = append_extra_instructions("base\n", f"  {EXTRA}  ")
    assert out.startswith("base\n\n" + EXTRA_INSTRUCTIONS_HEADING + "\n")
    assert out.endswith(EXTRA + "\n")


# --- config precedence --------------------------------------------------------


def test_call_arg_overrides_config_and_none_falls_back():
    base = GeometryConfig(extra_instructions="from config")
    assert resolve_config(base).extra_instructions == "from config"
    assert resolve_config(base, extra_instructions="from call").extra_instructions == "from call"
    assert resolve_config(base, extra_instructions="").extra_instructions == ""
    assert GeometryConfig().extra_instructions is None


# --- structured ----------------------------------------------------------------


async def _structured_render(extra_kwargs: dict, config: GeometryConfig):
    llm = _structured_llm([DiagramIR(define=[], checks=[], render=[])])
    with (
        patch.object(structured_mod, "get_chat_model", return_value=llm),
        patch.object(structured_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        await render_geometry_diagram("a triangle", config=config, **extra_kwargs)
    return _structured_messages(llm)


@pytest.mark.asyncio
async def test_structured_system_prompt_gets_extra_and_user_message_does_not():
    messages = await _structured_render({"extra_instructions": EXTRA}, _cfg("structured"))
    system = _system_text(messages)
    assert system.startswith(build_structured_instructions(frozenset()).rstrip("\n"))
    assert system.rstrip().endswith(EXTRA)
    assert EXTRA_INSTRUCTIONS_HEADING in system
    assert messages[-1].content == "a triangle"


@pytest.mark.asyncio
async def test_structured_prompt_unchanged_without_extra():
    for kwargs, config in (({}, _cfg("structured")), ({"extra_instructions": ""}, _cfg("structured"))):
        messages = await _structured_render(kwargs, config)
        assert _system_text(messages) == build_structured_instructions(frozenset())


@pytest.mark.asyncio
async def test_config_extra_instructions_reach_the_prompt():
    messages = await _structured_render({}, _cfg("structured", extra_instructions=EXTRA))
    assert EXTRA in _system_text(messages)


@pytest.mark.asyncio
async def test_structured_edit_gets_extra():
    llm = _structured_llm([DiagramIR(define=[], checks=[], render=[])])
    with (
        patch.object(structured_mod, "get_chat_model", return_value=llm),
        patch.object(structured_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ):
        await edit_geometry_diagram(
            "bigger", previous_ir=DiagramIR(define=[], checks=[], render=[]).model_dump(),
            config=_cfg("structured"), extra_instructions=EXTRA,
        )
    assert EXTRA in _system_text(_structured_messages(llm))


# --- recipe --------------------------------------------------------------------


def _recipe_patches(llm):
    return [
        patch.object(recipe_mod, "get_chat_model", return_value=llm),
        patch.object(recipe_mod, "load_catalog", return_value=[]),
        patch.object(recipe_mod, "lower_to_ir", return_value=MagicMock()),
        patch.object(recipe_mod, "require_features"),
        patch.object(recipe_mod, "_run_ir_pipeline", new=AsyncMock(return_value=_fake_result())),
    ]


async def _recipe_run(**kwargs):
    llm = _structured_llm([RecipeDSL(construction=[])])
    patches = _recipe_patches(llm)
    for p in patches:
        p.start()
    try:
        await render_geometry_diagram("a triangle", config=_cfg("recipe"), **kwargs)
    finally:
        for p in patches:
            p.stop()
    return llm


@pytest.mark.asyncio
async def test_recipe_generation_system_gets_extra_but_selector_does_not():
    llm = await _recipe_run(extra_instructions=EXTRA)
    assert EXTRA in _system_text(_structured_messages(llm))
    selector_messages = llm.ainvoke.call_args.args[0]
    assert all(EXTRA not in str(m.content) for m in selector_messages)


@pytest.mark.asyncio
async def test_recipe_prompt_unchanged_without_extra():
    llm = await _recipe_run()
    assert _system_text(_structured_messages(llm)) == RECIPE_GENERATION_SYSTEM


@pytest.mark.asyncio
async def test_recipe_prompt_cache_block_still_used_with_extra():
    llm = await _recipe_run(extra_instructions=EXTRA)
    human = _structured_messages(llm)[-1].content
    assert isinstance(human, list) and human[0]["cache_control"] == {"type": "ephemeral"}
    assert all(EXTRA not in block["text"] for block in human)


@pytest.mark.asyncio
async def test_recipe_edit_gets_extra():
    llm = _structured_llm([RecipeDSL(construction=[])])
    patches = _recipe_patches(llm)
    for p in patches:
        p.start()
    try:
        await edit_geometry_diagram(
            "bigger", previous_dsl=RecipeDSL(construction=[]).model_dump(),
            config=_cfg("recipe"), extra_instructions=EXTRA,
        )
    finally:
        for p in patches:
            p.stop()
    assert EXTRA in _system_text(_structured_messages(llm))


# --- python_full ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_python_full_system_gets_extra_and_default_prompt_is_unchanged():
    llm = _structured_llm([PydslScriptOutput(script=VALID_SCRIPT)] * 2)
    with patch.object(pf, "get_chat_model", return_value=llm):
        await render_geometry_diagram(
            "a triangle", config=_cfg("python_full"), extra_instructions=EXTRA,
        )
        with_extra = _system_text(_structured_messages(llm))
        await render_geometry_diagram("a triangle", config=_cfg("python_full"))
        without = _system_text(_structured_messages(llm))
    assert EXTRA in with_extra and EXTRA_INSTRUCTIONS_HEADING in with_extra
    assert without == build_python_full_instructions(include_cookbook=False, features=frozenset())


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["search_replace", "patch", "hashline", "line_number"])
async def test_python_full_edit_handlers_send_extra_in_the_system_prompt(mode):
    seen: list[str] = []

    async def fake_generate(prompt, model, **kwargs):
        seen.append(kwargs.get("extra_instructions"))
        raise RuntimeError("stop after generation")

    name = {
        "search_replace": "generate_search_replace", "patch": "_generate_patch",
        "hashline": "_generate_hashline_ops", "line_number": "_generate_line_number_ops",
    }[mode]
    with patch.object(pf, name, new=fake_generate):
        with pytest.raises(RuntimeError, match="stop after generation"):
            await edit_geometry_diagram(
                "move c", previous_script=VALID_SCRIPT,
                config=_cfg("python_full", edit_generation_mode=mode), extra_instructions=EXTRA,
            )
    assert seen == [EXTRA]


@pytest.mark.asyncio
async def test_python_full_edit_prompt_text_carries_extra():
    response = MagicMock()
    response.content = "<<<<<<< SEARCH\nc = point(0, 3)\n=======\nc = point(0, 5)\n>>>>>>> REPLACE"
    response.usage_metadata = {"input_tokens": 1, "output_tokens": 1}
    response.response_metadata = {}
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response)
    with patch.object(pf, "get_chat_model", return_value=llm):
        await edit_geometry_diagram(
            "move c", previous_script=VALID_SCRIPT, config=_cfg("python_full"),
            extra_instructions=EXTRA,
        )
    messages = llm.ainvoke.call_args.args[0]
    assert EXTRA in _system_text(messages)
    assert EXTRA not in str(messages[-1].content)
