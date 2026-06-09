from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from langchain_core.tools import tool

from geometry_diagrams.config import GeometryConfig, resolve_config
from geometry_diagrams.ir.font import FontConfig
from geometry_diagrams.ir.renderer import Renderer, SVGRenderer, TikZRenderer
from geometry_diagrams.strategies.recipe import RecipeStrategy


@dataclass
class DiagramResult:
    """Result of rendering a geometry diagram."""
    svg: str
    tikz: str        # empty string when renderer == "svg"
    input_tokens: int
    output_tokens: int


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
    result = await strategy.run(prompt, model=cfg.model, renderer=_make_renderer(cfg))
    return DiagramResult(
        svg=result.svg,
        tikz=result.tikz,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
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

    Returns a JSON string with keys "svg" and "tikz" on success,
    or {"error": "..."} on failure. Configuration (renderer, model, etc.)
    is read from environment variables via GeometryConfig.from_env().
    """
    try:
        result = await render_geometry_diagram(prompt)
        return json.dumps({"svg": result.svg, "tikz": result.tikz})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
