from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from langchain_core.tools import tool

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackManager

from .config import GeometryConfig, resolve_config
from .features import parse_features, tagged_insertions
from .ir.font import FontConfig
from .ir.renderer import Renderer, SVGRenderer, TikZRenderer
from .strategies.base import SubstanceStrategy
from .strategies.python_full import PythonFullStrategy
from .strategies.recipe import RecipeStrategy
from .strategies.structured import StructureStrategy


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
    # Each strategy's stateless edit input is the matching field of its own prior result:
    # recipe -> dsl (previous_dsl), python_full -> script (previous_script),
    # structured -> diagram_ir (previous_ir).


def _make_renderer(cfg: GeometryConfig) -> Renderer:
    fc = FontConfig(family=cfg.font_family)
    if cfg.renderer == "svg":
        return SVGRenderer(
            font_config=fc,
            embed_fonts=cfg.embed_fonts,
            debug_show_implicit=cfg.debug_show_implicit,
        )
    if cfg.renderer == "tikz":
        return TikZRenderer(renderer_url=cfg.renderer_url, font_config=fc)
    raise ValueError(f"Unknown renderer: {cfg.renderer!r} (expected 'tikz' or 'svg')")


def _make_strategy(cfg: GeometryConfig) -> SubstanceStrategy:
    if cfg.strategy == "python_full":
        return PythonFullStrategy(enable_cache=True, features=cfg.features)
    if cfg.strategy == "recipe":
        return RecipeStrategy(enable_cache=True, selector_model=cfg.selector_model, features=cfg.features)
    if cfg.strategy == "structured":
        return StructureStrategy(enable_cache=True, features=cfg.features)
    raise ValueError(
        f"Unknown strategy: {cfg.strategy!r} (expected 'recipe', 'python_full' or 'structured')"
    )


# The prior-state argument each strategy accepts for a stateless edit.
_PREVIOUS_ARG_BY_STRATEGY = {
    "recipe": "previous_dsl",
    "python_full": "previous_script",
    "structured": "previous_ir",
}


def _check_previous_state(strategy: str, **previous: object) -> None:
    """Reject prior state the chosen strategy cannot edit from, or more than one."""
    given = [name for name, value in previous.items() if value is not None]
    if len(given) > 1:
        raise ValueError(f"pass at most one of {', '.join(previous)} (got {', '.join(given)})")
    expected = _PREVIOUS_ARG_BY_STRATEGY[strategy]
    for name in given:
        if name != expected:
            owner = next(k for k, v in _PREVIOUS_ARG_BY_STRATEGY.items() if v == name)
            raise ValueError(
                f"{name} is only supported by the {owner} strategy; "
                f"strategy={strategy!r} edits from {expected}"
            )


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
    previous_script: Optional[str] = None,
    previous_ir: Optional[dict] = None,
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
        strategy: Override strategy choice ("recipe", "python_full" or "structured").
        model: Override generation model id (e.g. "anthropic:claude-sonnet-4-6").
        selector_model: Override recipe selector model id (recipe strategy only).
        renderer_url: Override TikZ renderer URL (only used when renderer="tikz").
        font_family: Override font family name.
        previous_dsl: Prior DSL dict (from DiagramResult.dsl) to anchor an edit.
            Recipe strategy only.
        previous_script: Prior pydsl script (from DiagramResult.script) to edit.
            python_full strategy only. The script is rerun first (no LLM call) to
            rebuild its entity manifest, then edited in config.edit_generation_mode
            (default search_replace).
        previous_ir: Prior DiagramIR dict (from DiagramResult.diagram_ir) to edit.
            structured strategy only; the model regenerates the whole IR anchored
            on it (no targeted-patch mode).
        At most one previous_* may be given, and it must match the strategy;
        otherwise ValueError.
        run_config: LangChain RunnableConfig dict to thread into LLM calls (e.g. for
            LangFuse tracing or get_anthropic_callback cost tracking). Its "callbacks"
            list is merged with the package's env-driven handler and any `callbacks` arg.
            Only honored by the recipe strategy — the python_full and structured
            strategies take no config/callbacks parameter, so both are silently
            ignored there (their own env-driven tracing handler still applies).
        callbacks: Additional LangChain callback handlers to attach to internal LLM calls.
            Same python_full/structured caveat as run_config above.
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

    _check_previous_state(
        cfg.strategy,
        previous_dsl=previous_dsl, previous_script=previous_script, previous_ir=previous_ir,
    )

    if cfg.strategy == "python_full":
        if previous_script is not None:
            result = await strategy_obj.edit(
                prompt,
                previous_script,
                model=cfg.model,
                renderer=_make_renderer(cfg),
                edit_generation_mode=cfg.edit_generation_mode,
                hash_algorithm=cfg.hash_algorithm,
                sandbox_timeout_seconds=cfg.sandbox_timeout_seconds,
            )
        else:
            result = await strategy_obj.run(
                prompt,
                model=cfg.model,
                renderer=_make_renderer(cfg),
                sandbox_timeout_seconds=cfg.sandbox_timeout_seconds,
            )
    elif cfg.strategy == "structured":
        result = await strategy_obj.run(
            prompt,
            model=cfg.model,
            renderer=_make_renderer(cfg),
            previous_ir=previous_ir,
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


# The prism lines of the description are advertised only with the solids
# feature group enabled; with it off the description is unchanged. Queries
# answer either way.
_QUERY_DIAGRAM_DOC: str = query_diagram.__doc__ or ""
_QUERY_DIAGRAM_SOLIDS_INSERTIONS: tuple[tuple[str, str], ...] = (
    (
        '- "length": {"segment": "seg_AB"}',
        '              -> drawn (2D) length; a segment joining two corners of a prism\n'
        '              (edge, face diagonal or space diagonal) also returns\n'
        '              "true_length", the true 3D length',
    ),
    (
        '- "perimeter": {"object": "tri_ABC"}',
        '            - "prism": {"prism": "P"} -> dimensions (length, width, height),\n'
        '              volume, base area, surface area and corner ids\n'
        '            - "stack": {"stack": "S"} -> block stack cube_count, volume, length,\n'
        '              width, height and is_height_map',
    ),
)


def query_diagram_description(features: "frozenset[str] | set[str]") -> str:
    """The ``query_diagram`` tool's docstring for an enabled feature set."""
    return tagged_insertions("solids", _QUERY_DIAGRAM_DOC, _QUERY_DIAGRAM_SOLIDS_INSERTIONS, features)


def _import_time_features() -> frozenset[str]:
    try:
        return parse_features(os.environ.get("GEOMETRY_FEATURES", ""))
    except ValueError:  # reported where the config is resolved, not at import
        return frozenset()


# LIMITATION: this is a module-level tool, so its description is fixed at
# import from the environment (GEOMETRY_FEATURES). A per-call feature override
# (resolve_config(features=...)) cannot change it; callers that enable solids
# per call and want the prism lines advertised should build their own tool
# with query_diagram_description(features).
query_diagram.__doc__ = query_diagram_description(_import_time_features())
query_diagram = tool(query_diagram)


async def edit_geometry_diagram(
    prompt: str,
    previous_dsl: Optional[dict] = None,
    *,
    previous_script: Optional[str] = None,
    previous_ir: Optional[dict] = None,
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

    Convenience wrapper around render_geometry_diagram that requires exactly one
    prior-state argument, matching the strategy (config / GEOMETRY_STRATEGY):
    previous_dsl (recipe; DiagramResult.dsl), previous_script (python_full;
    DiagramResult.script) or previous_ir (structured; DiagramResult.diagram_ir).
    The prior state anchors the edit — only the properties you describe in prompt
    should change. Passing the wrong one for the strategy raises ValueError.

    Remaining kwargs: same as render_geometry_diagram.
    """
    if sum(x is not None for x in (previous_dsl, previous_script, previous_ir)) != 1:
        raise ValueError(
            "edit_geometry_diagram needs exactly one of previous_dsl, previous_script, previous_ir"
        )
    return await render_geometry_diagram(
        prompt,
        previous_dsl=previous_dsl,
        previous_script=previous_script,
        previous_ir=previous_ir,
        config=config,
        renderer=renderer,
        model=model,
        selector_model=selector_model,
        renderer_url=renderer_url,
        font_family=font_family,
        run_config=run_config,
        callbacks=callbacks,
    )


def edit_geometry_diagram_sync(prompt: str, previous_dsl: Optional[dict] = None, **kwargs) -> DiagramResult:
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
