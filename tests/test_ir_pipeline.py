"""Tests for the shared StructuredRunResult dataclass."""
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.ir import DiagramIR


def _make_minimal_result(**overrides) -> StructuredRunResult:
    defaults = dict(
        diagram_ir=DiagramIR(define=[], checks=[], render=[]),
        tikz="", svg="", sym_table={}, sym_full={},
    )
    defaults.update(overrides)
    return StructuredRunResult(**defaults)


def test_python_full_metadata_defaults_to_none():
    result = _make_minimal_result()
    assert result.python_full_metadata is None
    assert result.recipe_metadata is None  # unaffected, still independently None


def test_python_full_metadata_can_be_set_independently_of_recipe_metadata():
    result = _make_minimal_result(python_full_metadata={"attempt_traces": []})
    assert result.python_full_metadata == {"attempt_traces": []}
    assert result.recipe_metadata is None
