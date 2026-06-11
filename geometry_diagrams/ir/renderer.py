"""Renderer abstraction for the IR pipeline.

Defines the Renderer ABC and RenderResult dataclass. TikZRenderer is the
default implementation that wraps ir_to_tikz() + render_tikz().

Future implementations (direct SVG, JSXGraph) implement the Renderer ABC
and are injected at the call site (evals, eval_viewer, main.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .font import FontConfig, default_font_config
from .ir import DiagramIR
from .to_sympy import SymTable


@dataclass
class RenderResult:
    """Output from a Renderer.render() call."""
    output: str       # Final artifact: SVG string, JS code, HTML, etc.
    format: str       # "svg", "js", "html" — discriminator for callers
    intermediate: str = ""  # Backend-specific code (e.g. TikZ), for diagnostics/logging


class Renderer(ABC):
    """Abstract renderer: compiles a DiagramIR+SymTable to a final output artifact."""

    @abstractmethod
    def render(
        self,
        diagram: DiagramIR,
        sym: SymTable,
        warnings: list[str] | None = None,
    ) -> RenderResult:
        """Render a compiled diagram to its final output format.

        Args:
            diagram: The full DiagramIR (render ops, canvas, styles).
            sym: The compiled SymPy symbol table from compile_defs().
            warnings: If provided, non-fatal issues are appended here.

        Returns:
            RenderResult with output, format, and optional intermediate code.
        """
        ...


class SVGRenderer(Renderer):
    """Renders DiagramIR → SVG directly from SymPy geometry, no LaTeX needed."""

    def __init__(
        self,
        font_config: FontConfig | None = None,
        embed_fonts: bool = False,
    ) -> None:
        self._font_config = font_config if font_config is not None else default_font_config()
        self._embed_fonts = embed_fonts

    def render(
        self,
        diagram: DiagramIR,
        sym: SymTable,
        warnings: list[str] | None = None,
    ) -> RenderResult:
        """Generate SVG directly from the SymPy symbol table.

        Returns:
            RenderResult(output=svg, format="svg", intermediate="")
        """
        from .to_svg import ir_to_svg
        svg = ir_to_svg(
            diagram, sym,
            warnings=warnings,
            font_config=self._font_config,
            embed_fonts=self._embed_fonts,
        )
        return RenderResult(output=svg, format="svg", intermediate="")


class TikZRenderer(Renderer):
    """Renders DiagramIR → TikZ code → SVG via the LaTeX Docker container."""

    def __init__(
        self,
        renderer_url: str | None = None,
        font_config: FontConfig | None = None,
    ) -> None:
        """
        Args:
            renderer_url: Base URL of the renderer container. Defaults to
                          TIKZ_RENDERER_URL env var or http://localhost:8001.
            font_config: Font configuration to use. Defaults to NunitoSans.
        """
        self._url = renderer_url
        self._font_config = font_config if font_config is not None else default_font_config()

    def render(
        self,
        diagram: DiagramIR,
        sym: SymTable,
        warnings: list[str] | None = None,
    ) -> RenderResult:
        """Generate TikZ from IR, then compile to SVG.

        Returns:
            RenderResult(output=svg, format="svg", intermediate=tikz_code)

        Raises:
            RuntimeError: If TikZ generation or SVG rendering fails.
        """
        # Import here to avoid circular import at module load time
        from .to_tikz import ir_to_tikz
        from ..util.tikz_renderer import render_tikz

        tikz = ir_to_tikz(diagram, sym, warnings=warnings)
        svg = render_tikz(tikz, renderer_url=self._url, font_family=self._font_config.family)
        return RenderResult(output=svg, format="svg", intermediate=tikz)

    def check_health(self) -> bool:
        """Return True if the renderer container is reachable."""
        from ..util.tikz_renderer import check_renderer_health
        return check_renderer_health(self._url)
