"""LLM generation strategies that turn a request into a rendered diagram.

Each strategy subclasses `SubstanceStrategy` (`base.py`). The raw strategies
(`raw_code`, `raw_svg` and their revise variants) emit TikZ or SVG directly;
`structured`, `recipe` and `python_full` produce a `DiagramIR` (as JSON,
recipe DSL or a sandboxed pydsl script) and hand it to the shared
`ir_pipeline.py` (compile, check, render). `llm.py` is the model factory and
the `instructions_*` modules hold the prompts. This `__init__` re-exports the
four main strategy classes; `PythonFullStrategy` is imported from `python_full`.
"""
from .base import SubstanceStrategy
from .raw_code import RawCodeStrategy
from .raw_code_with_revise import RawCodeWithReviseStrategy
from .structured import StructureStrategy
from .recipe import RecipeStrategy

__all__ = [
    "SubstanceStrategy",
    "RawCodeStrategy",
    "RawCodeWithReviseStrategy",
    "StructureStrategy",
    "RecipeStrategy",
]
