from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Optional

# Matches the default in geometry_diagrams/strategies/base.py and recipe.py
_DEFAULT_MODEL = "anthropic:claude-sonnet-4-6"
_DEFAULT_SELECTOR_MODEL = "anthropic:claude-haiku-4-5-20251001"


@dataclass
class GeometryConfig:
    """Configuration for the geometry diagram pipeline.

    All fields fall back to environment variables, then to hardcoded defaults.
    API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY) are NOT managed
    here — they are read by the LangChain SDKs directly from the environment.
    """

    renderer: Literal["tikz", "svg"] = "tikz"
    model: str = _DEFAULT_MODEL
    selector_model: str = _DEFAULT_SELECTOR_MODEL
    renderer_url: Optional[str] = None  # None → TikZRenderer reads TIKZ_RENDERER_URL / localhost:8001
    font_family: str = "NunitoSans"
    embed_fonts: bool = False

    @classmethod
    def from_env(cls) -> "GeometryConfig":
        """Build config from environment variables with hardcoded fallbacks."""
        return cls(
            renderer=os.environ.get("GEOMETRY_RENDERER", os.environ.get("RENDERER", "tikz")),  # type: ignore[arg-type]
            model=os.environ.get("GEOMETRY_MODEL", os.environ.get("MODEL", _DEFAULT_MODEL)),
            selector_model=os.environ.get("GEOMETRY_SELECTOR_MODEL", _DEFAULT_SELECTOR_MODEL),
            renderer_url=os.environ.get("TIKZ_RENDERER_URL") or None,
            font_family=os.environ.get("DIAGRAM_FONT_FAMILY", "NunitoSans"),
            embed_fonts=os.environ.get("DIAGRAM_EMBED_FONTS", "0") in ("1", "true", "True"),
        )


def resolve_config(
    base: Optional[GeometryConfig] = None,
    *,
    renderer: Optional[str] = None,
    model: Optional[str] = None,
    selector_model: Optional[str] = None,
    renderer_url: Optional[str] = None,
    font_family: Optional[str] = None,
) -> GeometryConfig:
    """Merge explicit kwargs on top of a base config (or env defaults)."""
    cfg = base if base is not None else GeometryConfig.from_env()
    return GeometryConfig(
        renderer=renderer or cfg.renderer,  # type: ignore[arg-type]
        model=model or cfg.model,
        selector_model=selector_model or cfg.selector_model,
        renderer_url=renderer_url if renderer_url is not None else cfg.renderer_url,
        font_family=font_family or cfg.font_family,
        embed_fonts=cfg.embed_fonts,
    )
