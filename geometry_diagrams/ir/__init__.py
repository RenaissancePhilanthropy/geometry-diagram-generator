"""Intermediate representation and its compile/check/render stages.

`ir.py` holds the Pydantic `DiagramIR` schema (definitions, checks, render
ops). `to_sympy.py` compiles definitions into SymPy objects (with `refs.py`,
`derived.py`, `prism.py`, `stack.py` and `conic_kernel.py` supporting it),
`checks.py` and `auto_checks.py` validate the result, `queries.py` extracts
facts, and `to_tikz.py` / `to_svg.py` (via `render_util.py`) draw it.
`renderer.py` dispatches to the TikZ container or the in-process SVG path.
The package is intentionally empty of re-exports: import from its modules.
"""
