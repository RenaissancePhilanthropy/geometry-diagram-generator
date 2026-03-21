"""Renderer abstraction for the IR pipeline.

Defines the Renderer ABC and RenderResult dataclass. TikZRenderer is the
default implementation that wraps ir_to_tikz() + render_tikz().

Future implementations (direct SVG, JSXGraph) implement the Renderer ABC
and are injected at the call site (evals, eval_viewer, main.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ir.ir import DiagramIR
from ir.to_sympy import SymTable


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


class TikZRenderer(Renderer):
    """Renders DiagramIR → TikZ code → SVG via the LaTeX Docker container."""

    def __init__(self, renderer_url: str | None = None) -> None:
        """
        Args:
            renderer_url: Base URL of the renderer container. Defaults to
                          TIKZ_RENDERER_URL env var or http://localhost:8001.
        """
        self._url = renderer_url

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
        from ir.to_tikz import ir_to_tikz
        from util.tikz_renderer import render_tikz

        tikz = ir_to_tikz(diagram, sym, warnings=warnings)
        svg = render_tikz(tikz, renderer_url=self._url)
        return RenderResult(output=svg, format="svg", intermediate=tikz)

    def check_health(self) -> bool:
        """Return True if the renderer container is reachable."""
        from util.tikz_renderer import check_renderer_health
        return check_renderer_health(self._url)
