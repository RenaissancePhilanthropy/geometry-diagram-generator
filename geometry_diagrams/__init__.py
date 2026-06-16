"""geometry_diagrams — geometry diagram generation pipeline.

Public API:
  render_diagram               — LangChain @tool for use in LangGraph agents
  render_geometry_diagram      — async function for LangGraph nodes
  render_geometry_diagram_sync — sync wrapper (not usable inside a running event loop)
  edit_geometry_diagram        — async convenience wrapper for editing an existing diagram
  edit_geometry_diagram_sync   — sync wrapper for edit_geometry_diagram
  DiagramResult                — result dataclass (svg, tikz, input_tokens, output_tokens,
                                 dsl, diagram_ir, recipes)
  GeometryConfig               — configuration dataclass
"""
from .facade import (
    render_diagram,
    render_geometry_diagram,
    render_geometry_diagram_sync,
    edit_geometry_diagram,
    edit_geometry_diagram_sync,
    DiagramResult,
)
from .config import GeometryConfig

__all__ = [
    "render_diagram",
    "render_geometry_diagram",
    "render_geometry_diagram_sync",
    "edit_geometry_diagram",
    "edit_geometry_diagram_sync",
    "DiagramResult",
    "GeometryConfig",
]
