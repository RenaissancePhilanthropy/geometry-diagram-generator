"""geometry_diagrams — geometry diagram generation pipeline.

Public API:
  render_diagram               — LangChain @tool for use in LangGraph agents
  render_geometry_diagram      — async function for LangGraph nodes
  render_geometry_diagram_sync — sync wrapper (not usable inside a running event loop)
  edit_geometry_diagram        — async convenience wrapper for editing an existing diagram
  edit_geometry_diagram_sync   — sync wrapper for edit_geometry_diagram
  query_diagram                — LangChain @tool to query a diagram from its dsl (no LLM call)
  query_geometry_diagram       — plain function backing query_diagram
  select_recipes               — async: run only the cheap recipe-selection step
  select_recipes_sync          — sync wrapper for select_recipes
  DiagramResult                — result dataclass (svg, tikz, input_tokens, output_tokens,
                                 dsl, diagram_ir, recipes)
  RecipeSelectionResult        — result dataclass for select_recipes
  GeometryConfig               — configuration dataclass
"""
from .facade import (
    render_diagram,
    render_geometry_diagram,
    render_geometry_diagram_sync,
    edit_geometry_diagram,
    edit_geometry_diagram_sync,
    query_diagram,
    query_geometry_diagram,
    DiagramResult,
)
from .config import GeometryConfig
from .strategies.recipe import RecipeSelectionResult, select_recipes, select_recipes_sync

__all__ = [
    "render_diagram",
    "render_geometry_diagram",
    "render_geometry_diagram_sync",
    "edit_geometry_diagram",
    "edit_geometry_diagram_sync",
    "query_diagram",
    "query_geometry_diagram",
    "select_recipes",
    "select_recipes_sync",
    "DiagramResult",
    "RecipeSelectionResult",
    "GeometryConfig",
]
