"""Recipe DSL: the high-level, declarative way to specify a construction.

`dsl.py` defines the `RecipeDSL` schema an LLM generates, `catalog.py` the
named recipes (YAML under `recipes/`) and the DSL docs shown to the model,
and `lower.py` compiles a DSL program to a `DiagramIR` (using `solve.py` and
`expressions.py`) with no SymPy dependency. It feeds the shared IR pipeline
through `strategies/recipe.py`.
"""
