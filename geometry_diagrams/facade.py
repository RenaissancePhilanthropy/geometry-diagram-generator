from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union

from langchain_core.tools import tool

if TYPE_CHECKING:
    from langchain_core.callbacks import BaseCallbackManager

from .config import GeometryConfig, resolve_config
from .features import parse_features, tagged_insertions
from .ir.font import FontConfig
from .ir.renderer import Renderer, SVGRenderer, TikZRenderer
from .strategies.base import SubstanceStrategy, run_sync
from .strategies.llm import model_options_context
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
    retry_count: int = 0 # number of generation attempts (successful one included)
    script: Optional[str] = None        # pydsl script source; python_full strategy only
    # Provider-reported USD cost of this call's LLM usage, summed over attempts (and, for a
    # python_full edit, the edit-generation call; a retry_on_apply_failure redo does not count
    # the failed first call). Includes the recipe selector and the pre-assert step calls.
    # None = not reported (some providers): unknown, not free.
    cost_usd: Optional[float] = None
    # Non-fatal pipeline notes from the final successful run (renderer warnings, failed
    # `prefer` checks, solid projection/label/overlap warnings, ...). Never fails a run.
    warnings: list[str] = field(default_factory=list)
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
    extra_instructions: Optional[str] = None,
    use_pre_assert_step: Optional[bool] = None,
    verify_labels_in_canvas: Optional[bool] = None,
    model_options: Optional[dict] = None,
    max_attempts: Optional[int] = None,
    retry_on_angle_mismatch: Optional[bool] = None,
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
            (default search_replace). The rerun costs one sandbox start plus an
            in-process render, no LLM call. Feature groups the script uses (e.g.
            solids for prism()/stack()) must be enabled in config.features, or the
            edit raises ValueError naming the group.
        previous_ir: Prior DiagramIR dict (from DiagramResult.diagram_ir) to edit.
            structured strategy only; the model regenerates the whole IR anchored
            on it (no targeted-patch mode).
        At most one previous_* may be given, and it must match the strategy;
        otherwise ValueError.
        run_config: LangChain RunnableConfig dict to thread into LLM calls (e.g. for
            LangFuse tracing or get_anthropic_callback cost tracking). Its "callbacks"
            list is merged with the package's env-driven handler and any `callbacks` arg.
            Honored by every strategy, including the edit-generation LLM call of a
            python_full previous_script edit.
        callbacks: Additional LangChain callback handlers to attach to internal LLM calls.
            Same scope as run_config above.
        extra_instructions: Application-specific text appended, as a delimited
            "Additional instructions from the application" section, to the system
            prompt of the generation call(s) of every strategy (not to the user's
            prompt, and not to the recipe selector). Overrides
            config.extra_instructions; None falls back to it, and None or empty
            leaves the prompts unchanged.
        use_pre_assert_step: python_full only. Run one extra LLM call before generation
            that proposes geometric invariants, filtered into advisory context for the
            script writer. Costs tokens; overrides config.use_pre_assert_step.
        verify_labels_in_canvas: python_full only. Retry the generation when a rendered
            label extends past the SVG viewBox. A no-op under renderer="tikz". Overrides
            config.verify_labels_in_canvas.
        model_options: Chat-model constructor kwargs (temperature, timeout, max_tokens, ...)
            applied to every model this call builds, including the recipe selector. Overrides
            config.model_options as a whole. An option a model class does not accept raises
            when the model is built.
        max_attempts: Generation attempts before GenerationFailedError, replacing the
            strategy default of 3 (None keeps it). For a python_full edit only the
            full_rewrite mode loops; the other modes are one generation call.
        retry_on_angle_mismatch: Every strategy. A right-angle mark or angle label that
            contradicts the angle actually drawn is always reported in DiagramResult.warnings;
            with this True it instead fails the attempt, so the strategy retries with the
            finding in its prompt. Overrides config.retry_on_angle_mismatch. An edit turn
            is held to it for the edited script only (a full_rewrite edit retries; the
            single-call modes fail the edit), never for the stored script it starts from.
        Neither option applies to an edit (previous_script) turn, which ignores them, and
        either one set True for the recipe or structured strategy raises ValueError.
    """
    cfg = resolve_config(
        config,
        renderer=renderer,
        strategy=strategy,
        model=model,
        selector_model=selector_model,
        renderer_url=renderer_url,
        font_family=font_family,
        extra_instructions=extra_instructions,
        use_pre_assert_step=use_pre_assert_step,
        verify_labels_in_canvas=verify_labels_in_canvas,
        model_options=model_options,
        max_attempts=max_attempts,
        retry_on_angle_mismatch=retry_on_angle_mismatch,
    )
    if cfg.strategy != "python_full":
        for name in ("use_pre_assert_step", "verify_labels_in_canvas"):
            if getattr(cfg, name):
                raise ValueError(f"{name} applies to the python_full strategy only, not {cfg.strategy!r}")
    strategy_obj = _make_strategy(cfg)
    # Passed on only when set, so strategy calls keep their shape without it.
    extra = {"extra_instructions": cfg.extra_instructions} if cfg.extra_instructions else {}
    if cfg.max_attempts:
        extra["max_attempts"] = cfg.max_attempts
    run_only = {"retry_on_angle_mismatch": True} if cfg.retry_on_angle_mismatch else {}

    _check_previous_state(
        cfg.strategy,
        previous_dsl=previous_dsl, previous_script=previous_script, previous_ir=previous_ir,
    )

    with model_options_context(cfg.model_options):
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
                    config=run_config,
                    callbacks=callbacks,
                    **extra,
                    **run_only,
                )
            else:
                # Passed on only when set, so the call shape is unchanged without them.
                quality = {
                    name: True for name in ("use_pre_assert_step", "verify_labels_in_canvas") if getattr(cfg, name)
                }
                result = await strategy_obj.run(
                    prompt,
                    model=cfg.model,
                    renderer=_make_renderer(cfg),
                    sandbox_timeout_seconds=cfg.sandbox_timeout_seconds,
                    config=run_config,
                    callbacks=callbacks,
                    **extra,
                    **quality,
                    **run_only,
                )
        elif cfg.strategy == "structured":
            result = await strategy_obj.run(
                prompt,
                model=cfg.model,
                renderer=_make_renderer(cfg),
                previous_ir=previous_ir,
                config=run_config,
                callbacks=callbacks,
                **extra,
                **run_only,
            )
        else:
            result = await strategy_obj.run(
                prompt,
                model=cfg.model,
                renderer=_make_renderer(cfg),
                previous_dsl=previous_dsl,
                config=run_config,
                callbacks=callbacks,
                **extra,
                **run_only,
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
    retry_count = len(traces)
    if result.recipe_metadata is None and cfg.strategy != "recipe":
        # structured / python_full carry no attempt traces on the result; `retries` is
        # the number of failed attempts before the successful one.
        retries = getattr(result, "retries", 0)
        retry_count = (retries if isinstance(retries, int) else 0) + 1
    return DiagramResult(
        svg=result.svg,
        tikz=result.tikz,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        dsl=_dsl,
        diagram_ir=_diagram_ir,
        recipes=_recipes,
        retry_count=retry_count,
        script=getattr(result, "script", "") or None,
        cost_usd=getattr(result, "cost_usd", None),
        warnings=list(getattr(result, "warnings", None) or []),
    )


def render_geometry_diagram_sync(prompt: str, **kwargs) -> DiagramResult:
    """Synchronous wrapper around render_geometry_diagram.

    Also works when called from inside a running event loop (the call then runs
    on a worker thread and blocks the caller until it finishes); async callers
    should still prefer render_geometry_diagram.
    """
    return run_sync(render_geometry_diagram(prompt, **kwargs))


@tool
async def render_diagram(prompt: str) -> str:
    """Render a geometry diagram from a natural-language description.

    Returns a JSON string with keys "svg", "tikz", "dsl", "input_tokens",
    "output_tokens", "script", "warnings" and "cost_usd" on success, or
    {"error": "..."} on failure. "dsl" is set by the recipe strategy and
    "script" (the pydsl source, the edit handle) by python_full; the other is
    null. "cost_usd" is null when the strategy does not report a cost.
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
            "script": result.script,
            "warnings": result.warnings,
            "cost_usd": result.cost_usd,
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
            "length" also takes an arc/sector (its curved edge; a full circle or
            ellipse has a perimeter, not a length). "radius" takes a circle, arc or
            sector (an ellipse or elliptical arc/sector returns hradius and vradius).
            "area" takes a polygon, circle, ellipse or sector (an open arc has none).
            "perimeter" takes a polygon, circle, ellipse or sector (two radii plus
            the arc).
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
    extra_instructions: Optional[str] = None,
) -> DiagramResult:
    """Edit an existing geometry diagram by applying the described changes.

    Convenience wrapper around render_geometry_diagram that requires exactly one
    prior-state argument, matching the strategy (config / GEOMETRY_STRATEGY):
    previous_dsl (recipe; DiagramResult.dsl), previous_script (python_full;
    DiagramResult.script) or previous_ir (structured; DiagramResult.diagram_ir).
    The prior state anchors the edit — only the properties you describe in prompt
    should change. Passing the wrong one for the strategy raises ValueError.
    There is no `strategy` argument: the strategy comes from `config` / GEOMETRY_STRATEGY.

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
        extra_instructions=extra_instructions,
    )


def edit_geometry_diagram_sync(prompt: str, previous_dsl: Optional[dict] = None, **kwargs) -> DiagramResult:
    """Synchronous wrapper around edit_geometry_diagram.

    Also works inside a running event loop, like render_geometry_diagram_sync.
    """
    return run_sync(edit_geometry_diagram(prompt, previous_dsl, **kwargs))


def query_geometry_diagram(
    dsl: Optional[dict],
    query_type: str,
    params: Optional[dict] = None,
    *,
    diagram_ir: Optional[dict] = None,
) -> str:
    """Query geometric properties of a diagram (no LLM call, no I/O).

    Give exactly one source. `dsl` is a recipe DSL: sym is recompiled from it via the same
    deterministic pipeline the render path uses (RecipeDSL.model_validate -> lower_to_ir ->
    compile_defs with the default Random(42) seed). `diagram_ir` is a serialized DiagramIR,
    i.e. DiagramResult.diagram_ir, from any strategy (python_full and structured results
    have no dsl): it is validated and compiled directly, with no model call and no sandbox
    rerun. Either way sym goes through dispatch_query, and a fresh process gets bit-identical
    answers for the same input.

    Args:
        dsl: A dsl dict from a prior DiagramResult.dsl, or None when diagram_ir is given.
        query_type: One of "list_objects", "coordinate", "distance", "angle",
            "length", "radius", "area", "perimeter" (same vocabulary as
            RecipeStrategy.build_agent()'s query_diagram tool).
        params: Query arguments; see dispatch_query() for the shape per query_type.
        diagram_ir: A DiagramResult.diagram_ir dict, or None when dsl is given. Object ids
            are IR ids, which for python_full are opaque (`__pydsl_pt_3`). On this path
            list_objects includes those ids, and a point can be named by its label text
            instead ("A", "C") when the text labels exactly one point; a text that labels
            several points is an error naming them.

    Returns:
        JSON string with the query result, or {"error": "..."} on failure
        (e.g. malformed input, unresolvable definition, unknown object id).

    Raises:
        ValueError: if not exactly one of dsl and diagram_ir is given.
    """
    if (dsl is None) == (diagram_ir is None):
        raise ValueError("query_geometry_diagram needs exactly one of dsl and diagram_ir")
    import pydantic
    from .ir.errors import IRCompileError
    from .ir.ir import DiagramIR
    from .ir.to_sympy import compile_defs
    from .recipe.dsl import RecipeDSL
    from .recipe.lower import lower_to_ir, LoweringError
    from .strategies.structured import dispatch_query

    try:
        if diagram_ir is not None:
            diagram = DiagramIR.model_validate(diagram_ir)
            sym = compile_defs(diagram)
        else:
            sym = compile_defs(lower_to_ir(RecipeDSL.model_validate(dsl)))
    except (pydantic.ValidationError, LoweringError, IRCompileError) as e:
        return json.dumps({"error": str(e)})
    if diagram_ir is None:
        return dispatch_query(sym, query_type, params or {})
    # A python_full figure has only opaque `__pydsl_*` ids, so on this path list_objects
    # includes them and a point may be named by the text of its label.
    if query_type == "list_objects":
        return json.dumps({
            obj_id: type(obj).__name__.removesuffix("2D") for obj_id, obj in sym.items()
            if not obj_id.startswith("__") or obj_id.startswith("__pydsl_")
        })
    try:
        resolved = _resolve_point_labels(diagram, sym, params or {})
    except ValueError as e:
        return json.dumps({"error": str(e)})
    return dispatch_query(sym, query_type, resolved)


def _resolve_point_labels(diagram: "DiagramIR", sym: dict, params: dict) -> dict:
    """`params` with every string that is not an object id but is the text of exactly one
    point label replaced by that point's id. ValueError when a text labels several points."""
    from .ir.ir import LabelPoint

    labeled: dict[str, set[str]] = {}
    for op in diagram.render:
        if isinstance(op, LabelPoint) and op.text:
            labeled.setdefault(op.text, set()).add(op.p)
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value not in sym and value in labeled:
            ids = sorted(labeled[value])
            if len(ids) > 1:
                raise ValueError(f"label {value!r} is on several points ({', '.join(ids)}); use one of those ids")
            value = ids[0]
        resolved[key] = value
    return resolved


def verify_geometry_diagram(diagram_ir: dict) -> dict:
    """Audit a finished diagram's geometry (no LLM call, no I/O): the same checks and warnings
    a render run applies, reported instead of acted on.

    Args:
        diagram_ir: DiagramResult.diagram_ir, from any strategy.

    Returns:
        A JSON-serializable dict:
        - "ok": True when no `must` check failed, no angle triple is invalid and no angle
          mark or label contradicts the drawn angle. Failed `prefer` checks and other
          warnings do not make it False.
        - "checks": one {"kind", "level", "passed", "message"} per check the diagram
          carries (message is empty on a pass): for python_full, its passing assert_* calls,
          which the builder keeps in the IR; for structured and recipe, the authored checks.
        - "angle_findings": each right-angle mark or angle label that disagrees with the
          drawn angle, as {"kind", "angle" [a, vertex, b point ids], "stated_deg",
          "drawn_deg", "message"} (see ir/angle_audit.py for which labels are read).
        - "invalid_angle_triples": angle marks whose arms are not on lines through the vertex.
        - "warnings": every pipeline warning the diagram produces without rendering it.
        On input that does not validate or compile: {"ok": False, "error": "..."}.
    """
    import pydantic
    from .ir.angle_pairs import resolve_angle_pairs
    from .ir.checks import check_render_angles
    from .ir.errors import IRCompileError
    from .ir.ir import DiagramIR
    from .ir.to_sympy import compile_defs
    from .strategies.ir_pipeline import collect_diagnostics

    try:
        diagram = DiagramIR.model_validate(diagram_ir)
        sym = compile_defs(diagram)
        diagram = resolve_angle_pairs(diagram, sym)
    except (pydantic.ValidationError, IRCompileError) as e:
        return {"ok": False, "error": str(e)}
    diagnostics = collect_diagnostics(diagram, sym)
    invalid_triples = check_render_angles(diagram, sym)
    checks = [
        {"kind": r.check.kind, "level": r.check.level, "passed": r.passed, "message": r.message}
        for r in diagnostics.check_results
    ]
    findings = [
        {"kind": f.kind, "angle": list(f.angle), "stated_deg": f.stated_deg, "drawn_deg": f.drawn_deg,
         "message": f.message}
        for f in diagnostics.angle_findings
    ]
    ok = (
        all(c["passed"] or c["level"] != "must" for c in checks)
        and not invalid_triples and not findings
    )
    return {
        "ok": ok, "checks": checks, "angle_findings": findings,
        "invalid_angle_triples": [str(t) for t in invalid_triples], "warnings": diagnostics.warnings,
    }
