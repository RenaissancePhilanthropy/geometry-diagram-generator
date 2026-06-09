"""geometry_diagrams — geometry diagram generation pipeline.

Public API:
  render_diagram          — LangChain @tool for use in LangGraph agents
  render_geometry_diagram — async function for LangGraph nodes
  render_geometry_diagram_sync — sync wrapper (not usable inside a running event loop)
  DiagramResult           — result dataclass (svg, tikz, input_tokens, output_tokens)
  GeometryConfig          — configuration dataclass
"""
from geometry_diagrams.facade import (
    render_diagram,
    render_geometry_diagram,
    render_geometry_diagram_sync,
    DiagramResult,
)
from geometry_diagrams.config import GeometryConfig

__all__ = [
    "render_diagram",
    "render_geometry_diagram",
    "render_geometry_diagram_sync",
    "DiagramResult",
    "GeometryConfig",
]
