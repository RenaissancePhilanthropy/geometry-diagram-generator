from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from langchain_core.tools import tool

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackManager

from .config import GeometryConfig, resolve_config
from .ir.font import FontConfig
from .ir.renderer import Renderer, SVGRenderer, TikZRenderer
from .strategies.recipe import RecipeStrategy


@dataclass
class DiagramResult:
    """Result of rendering a geometry diagram."""
    svg: str
    tikz: str        # empty string when renderer == "svg"
    input_tokens: int
    output_tokens: int
    dsl: Optional[dict] = None          # serialized RecipeDSL (dsl.model_dump())
    diagram_ir: Optional[dict] = None   # serialized DiagramIR (ir.model_dump())
    recipes: Optional[list[str]] = None # selected recipe IDs
    retry_count: int = 0 # number of DSL-generation attempts (len of attempt_traces)


def _make_renderer(cfg: GeometryConfig) -> Renderer:
    fc = FontConfig(family=cfg.font_family)
    if cfg.renderer == "svg":
        return SVGRenderer(font_config=fc, embed_fonts=cfg.embed_fonts)
    if cfg.renderer == "tikz":
        return TikZRenderer(renderer_url=cfg.renderer_url, font_config=fc)
    raise ValueError(f"Unknown renderer: {cfg.renderer!r} (expected 'tikz' or 'svg')")


def _make_strategy(cfg: GeometryConfig) -> RecipeStrategy:
    return RecipeStrategy(enable_cache=True, selector_model=cfg.selector_model)


async def render_geometry_diagram(
    prompt: str,
    *,
    config: Optional[GeometryConfig] = None,
    renderer: Optional[str] = None,
    model: Optional[str] = None,
    selector_model: Optional[str] = None,
    renderer_url: Optional[str] = None,
    font_family: Optional[str] = None,
    previous_dsl: Optional[dict] = None,
    run_config: Optional[dict] = None,
    callbacks: "Optional[Union[list, BaseCallbackManager]]" = None,
) -> DiagramResult:
    """Render a geometry diagram from a natural-language prompt.

    Uses the recipe strategy (recipe selection → DSL generation → IR compile → render).
    Returns a DiagramResult with the SVG and (if using TikZ renderer) the intermediate TikZ.

    Args:
        prompt: Natural-language description of the diagram to render.
        config: Optional base GeometryConfig. Falls back to GeometryConfig.from_env().
        renderer: Override renderer choice ("tikz" or "svg").
        model: Override generation model id (e.g. "anthropic:claude-sonnet-4-6").
        selector_model: Override recipe selector model id.
        renderer_url: Override TikZ renderer URL (only used when renderer="tikz").
        font_family: Override font family name.
        previous_dsl: Prior DSL dict (from DiagramResult.dsl) to anchor an edit.
        run_config: LangChain RunnableConfig dict to thread into LLM calls (e.g. for
            LangFuse tracing or get_anthropic_callback cost tracking). Its "callbacks"
            list is merged with the package's env-driven handler and any `callbacks` arg.
        callbacks: Additional LangChain callback handlers to attach to internal LLM calls.
    """
    cfg = resolve_config(
        config,
        renderer=renderer,
        model=model,
        selector_model=selector_model,
        renderer_url=renderer_url,
        font_family=font_family,
    )
    strategy = _make_strategy(cfg)
    result = await strategy.run(
        prompt,
        model=cfg.model,
        renderer=_make_renderer(cfg),
        previous_dsl=previous_dsl,
        config=run_config,
        callbacks=callbacks,
    )
    # Extract structured artifacts if available
    _recipes = None
    _dsl = None
    _diagram_ir = None
    traces = []
    if result.recipe_metadata is not None:
        _recipes = result.recipe_metadata.selected_recipes or None
        traces = result.recipe_metadata.attempt_traces or []
        for trace in reversed(traces):
            if trace.stage == "success" and trace.dsl_json:
                _dsl = trace.dsl_json  # already a plain dict
                break
    _diagram_ir = result.diagram_ir.model_dump()
    return DiagramResult(
        svg=result.svg,
        tikz=result.tikz,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        dsl=_dsl,
        diagram_ir=_diagram_ir,
        recipes=_recipes,
        retry_count=len(traces),
    )


def render_geometry_diagram_sync(prompt: str, **kwargs) -> DiagramResult:
    """Synchronous wrapper around render_geometry_diagram.

    Note: Will raise RuntimeError if called from within a running event loop.
    Async callers should use render_geometry_diagram directly.
    """
    return asyncio.run(render_geometry_diagram(prompt, **kwargs))


@tool
async def render_diagram(prompt: str) -> str:
    """Render a geometry diagram from a natural-language description.

    Returns a JSON string with keys "svg", "tikz", "dsl", "input_tokens",
    and "output_tokens" on success, or {"error": "..."} on failure.
    Configuration (renderer, model, etc.) is read from environment variables
    via GeometryConfig.from_env().
    """
    try:
        result = await render_geometry_diagram(prompt)
        return json.dumps({
            "svg": result.svg,
            "tikz": result.tikz,
            "dsl": result.dsl,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            # diagram_ir and recipes intentionally omitted (size/utility tradeoff for agent context)
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def edit_geometry_diagram(
    prompt: str,
    previous_dsl: dict,
    *,
    config: Optional[GeometryConfig] = None,
    renderer: Optional[str] = None,
    model: Optional[str] = None,
    selector_model: Optional[str] = None,
    renderer_url: Optional[str] = None,
    font_family: Optional[str] = None,
    run_config: Optional[dict] = None,
    callbacks: "Optional[Union[list, BaseCallbackManager]]" = None,
) -> DiagramResult:
    """Edit an existing geometry diagram by applying the described changes.

    Convenience wrapper around render_geometry_diagram with previous_dsl pre-filled.
    The prior DSL (from DiagramResult.dsl) anchors the edit — only the properties
    you describe in prompt will be changed.

    Args:
        prompt: Natural-language description of the change to apply.
        previous_dsl: The dsl dict from a prior DiagramResult.
        Remaining kwargs: same as render_geometry_diagram.
    """
    return await render_geometry_diagram(
        prompt,
        previous_dsl=previous_dsl,
        config=config,
        renderer=renderer,
        model=model,
        selector_model=selector_model,
        renderer_url=renderer_url,
        font_family=font_family,
        run_config=run_config,
        callbacks=callbacks,
    )


def edit_geometry_diagram_sync(prompt: str, previous_dsl: dict, **kwargs) -> DiagramResult:
    """Synchronous wrapper around edit_geometry_diagram.

    Note: Will raise RuntimeError if called from within a running event loop.
    """
    return asyncio.run(edit_geometry_diagram(prompt, previous_dsl, **kwargs))
