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

Resolved lazily (PEP 562 module __getattr__), not imported eagerly here:
`.facade` and `.strategies.recipe` transitively pull in LangGraph/LangChain
(and everything module-level `from geometry_diagrams import X` used to force
on ANY import of anything under this package). That's irrelevant, unwanted
weight for the sandbox's spawned child process (`python -m
geometry_diagrams.pydsl._sandbox_child`, see sandbox.py), which never uses
LangGraph/LangChain at all but was still forced to import the entire
chain just because Python always imports a submodule's parent package
first, before any of that child module's own code (including its own
try/except-wrapped imports) ever runs. Confirmed empirically (2026-08-13):
eagerly importing this package pulls in ~1475
modules (langgraph: 90, langsmith: 26, sympy: 419, pydantic: 71) at ~0.7s
warm on a local dev machine — on a cold, resource-constrained container,
this plausibly dominates or even hangs. Existing callers are unaffected:
`from geometry_diagrams import render_diagram` still works identically,
just resolved on first access instead of at package-import time.
"""
_LAZY_EXPORTS = {
    "render_diagram": ".facade",
    "render_geometry_diagram": ".facade",
    "render_geometry_diagram_sync": ".facade",
    "edit_geometry_diagram": ".facade",
    "edit_geometry_diagram_sync": ".facade",
    "query_diagram": ".facade",
    "query_geometry_diagram": ".facade",
    "DiagramResult": ".facade",
    "GeometryConfig": ".config",
    "RecipeSelectionResult": ".strategies.recipe",
    "select_recipes": ".strategies.recipe",
    "select_recipes_sync": ".strategies.recipe",
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str):
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(module_path, __name__)
    return getattr(module, name)


def __dir__():
    return sorted(list(globals()) + list(_LAZY_EXPORTS))
