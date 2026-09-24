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
from .strategies.base import SubstanceStrategy
from .strategies.python_full import PythonFullStrategy
from .strategies.recipe import RecipeStrategy


@dataclass
class DiagramResult:
    """Result of rendering a geometry diagram."""
    svg: str
    tikz: str        # empty string when renderer == "svg"
    input_tokens: int
    output_tokens: int
    dsl: Optional[dict] = None          # serialized RecipeDSL (dsl.model_dump()); recipe strategy only
    diagram_ir: Optional[dict] = None   # serialized DiagramIR (ir.model_dump())
    recipes: Optional[list[str]] = None # selected recipe IDs; recipe strategy only
    retry_count: int = 0 # number of generation attempts (len of attempt_traces)
    script: Optional[str] = None        # pydsl script source; python_full strategy only


def _make_renderer(cfg: GeometryConfig) -> Renderer:
    fc = FontConfig(family=cfg.font_family)
    if cfg.renderer == "svg":
        return SVGRenderer(font_config=fc, embed_fonts=cfg.embed_fonts)
    if cfg.renderer == "tikz":
        return TikZRenderer(renderer_url=cfg.renderer_url, font_config=fc)
    raise ValueError(f"Unknown renderer: {cfg.renderer!r} (expected 'tikz' or 'svg')")


def _make_strategy(cfg: GeometryConfig) -> SubstanceStrategy:
    if cfg.strategy == "python_full":
        return PythonFullStrategy(enable_cache=True)
    if cfg.strategy == "recipe":
        return RecipeStrategy(enable_cache=True, selector_model=cfg.selector_model)
    raise ValueError(f"Unknown strategy: {cfg.strategy!r} (expected 'recipe' or 'python_full')")


async def render_geometry_diagram(
    prompt: str,
    *,
    config: Optional[GeometryConfig] = None,
    renderer: Optional[str] = None,
    strategy: Optional[str] = None,
    model: Optional[str] = None,
    selector_model: Optional[str] = None,
    renderer_url: Optional[str] = None,
    font_family: Optional[str] = None,
    previous_dsl: Optional[dict] = None,
    run_config: Optional[dict] = None,
    callbacks: "Optional[Union[list, BaseCallbackManager]]" = None,
) -> DiagramResult:
    """Render a geometry diagram from a natural-language prompt.

    Uses either the recipe strategy (recipe selection → DSL generation → IR compile →
    render) or the python_full strategy (LLM-authored pydsl script → sandboxed execution
    → IR compile → render), per `strategy`/`config.strategy`. Returns a DiagramResult with
    the SVG and (if using TikZ renderer) the intermediate TikZ.

    Args:
        prompt: Natural-language description of the diagram to render.
        config: Optional base GeometryConfig. Falls back to GeometryConfig.from_env().
        renderer: Override renderer choice ("tikz" or "svg").
        strategy: Override strategy choice ("recipe" or "python_full").
        model: Override generation model id (e.g. "anthropic:claude-sonnet-4-6").
        selector_model: Override recipe selector model id (recipe strategy only).
        renderer_url: Override TikZ renderer URL (only used when renderer="tikz").
        font_family: Override font family name.
        previous_dsl: Prior DSL dict (from DiagramResult.dsl) to anchor an edit.
            Only supported by the recipe strategy — passing this with
            strategy="python_full" raises ValueError, since PythonFullStrategy has
            no stateless edit entry point (its only edit path is the stateful
            build_agent() ReAct agent, not exposed through this facade).
        run_config: LangChain RunnableConfig dict to thread into LLM calls (e.g. for
            LangFuse tracing or get_anthropic_callback cost tracking). Its "callbacks"
            list is merged with the package's env-driven handler and any `callbacks` arg.
            Only honored by the recipe strategy — PythonFullStrategy.run() takes no
            config/callbacks parameter, so both are silently ignored under
            strategy="python_full" (its own env-driven tracing handler still applies).
        callbacks: Additional LangChain callback handlers to attach to internal LLM calls.
            Same python_full caveat as run_config above.
    """
    cfg = resolve_config(
        config,
        renderer=renderer,
        strategy=strategy,
        model=model,
        selector_model=selector_model,
        renderer_url=renderer_url,
        font_family=font_family,
    )
    strategy_obj = _make_strategy(cfg)

    if cfg.strategy == "python_full":
        if previous_dsl is not None:
            raise ValueError(
                "previous_dsl is not supported with strategy='python_full' — "
                "PythonFullStrategy has no stateless edit entry point (its only "
                "edit path is the stateful build_agent() ReAct agent)."
            )
        result = await strategy_obj.run(
            prompt,
            model=cfg.model,
            renderer=_make_renderer(cfg),
            sandbox_timeout_seconds=cfg.sandbox_timeout_seconds,
        )
    else:
        result = await strategy_obj.run(
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
        script=getattr(result, "script", "") or None,
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


@tool
def query_diagram(dsl: dict, query_type: str, params: Optional[dict] = None) -> str:
    """Query geometric properties of a diagram from its DSL (no LLM call).

    Args:
        dsl: A dsl dict from a prior render_diagram/DiagramResult.dsl.
        query_type: One of "list_objects", "coordinate", "distance", "angle",
            "length", "radius", "area", "perimeter".
        params: Query arguments:
            - "list_objects": {}
            - "coordinate": {"point": "A"}
            - "distance": {"a": "A", "b": "B"}
            - "angle": {"a": "A", "vertex": "B", "b": "C"}
            - "length": {"segment": "seg_AB"}
            - "radius": {"circle": "circ"}
            - "area": {"object": "tri_ABC"}
            - "perimeter": {"object": "tri_ABC"}
            Call list_objects first to see valid IDs.
    Returns:
        JSON string with the query result, or {"error": "..."} on failure.
    """
    return query_geometry_diagram(dsl, query_type, params)


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
        Remaining kwargs: same as render_geometry_diagram. Note strategy="python_full"
        (via config or GEOMETRY_STRATEGY) always raises ValueError here, since
        previous_dsl is never None on this path and PythonFullStrategy has no
        stateless edit entry point.
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


def query_geometry_diagram(dsl: dict, query_type: str, params: Optional[dict] = None) -> str:
    """Query geometric properties of a diagram from its DSL (no LLM call, no I/O).

    Recompiles sym from dsl via the same deterministic pipeline the render path uses
    (RecipeDSL.model_validate -> lower_to_ir -> compile_defs with the default Random(42)
    seed), then dispatches through dispatch_query. Safe to call from a fresh process
    each time — recompilation is bit-identical given the same dsl.

    Args:
        dsl: A dsl dict from a prior DiagramResult.dsl.
        query_type: One of "list_objects", "coordinate", "distance", "angle",
            "length", "radius", "area", "perimeter" (same vocabulary as
            RecipeStrategy.build_agent()'s query_diagram tool).
        params: Query arguments; see dispatch_query() for the shape per query_type.

    Returns:
        JSON string with the query result, or {"error": "..."} on failure
        (e.g. malformed dsl, unresolvable definition, unknown object id).
    """
    import pydantic
    from .recipe.dsl import RecipeDSL
    from .recipe.lower import lower_to_ir, LoweringError
    from .ir.to_sympy import compile_defs
    from .ir.errors import IRCompileError
    from .strategies.structured import dispatch_query

    try:
        parsed = RecipeDSL.model_validate(dsl)
        diagram_ir = lower_to_ir(parsed)
        sym = compile_defs(diagram_ir)
    except (pydantic.ValidationError, LoweringError, IRCompileError) as e:
        return json.dumps({"error": str(e)})
    return dispatch_query(sym, query_type, params or {})
