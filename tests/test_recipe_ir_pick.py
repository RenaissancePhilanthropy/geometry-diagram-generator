# tests/test_recipe_ir_pick.py
import pytest
from pydantic import ValidationError
from geometry_diagrams.ir.ir import (
    PickBetween, PickBeyond, PickInterior, PickExterior,
    PickOppositeSide, PickUpperOfLine, PickLowerOfLine, PickChain,
    PickRule,
)

def test_pick_between_roundtrip():
    p = PickBetween(a="A", b="B")
    assert p.kind == "between"
    assert p.a == "A"
    data = p.model_dump()
    assert PickBetween.model_validate(data).a == "A"

def test_pick_beyond_roundtrip():
    p = PickBeyond(from_point="O", past_point="A")
    assert p.kind == "beyond"

def test_pick_interior_roundtrip():
    p = PickInterior(polygon="poly1")
    assert p.kind == "interior"

def test_pick_exterior_roundtrip():
    p = PickExterior(polygon="poly1")
    assert p.kind == "exterior"

def test_pick_opposite_side_roundtrip():
    p = PickOppositeSide(line_through=["A", "B"], ref_point="C")
    assert p.kind == "opposite_side"

def test_pick_upper_of_line_roundtrip():
    p = PickUpperOfLine(a="A", b="B")
    assert p.kind == "upper_of_line"

def test_pick_lower_of_line_roundtrip():
    p = PickLowerOfLine(a="A", b="B")
    assert p.kind == "lower_of_line"

def test_pick_chain_roundtrip():
    chain = PickChain(rules=[
        PickBetween(a="A", b="B"),
        PickUpperOfLine(a="A", b="B"),
    ])
    assert chain.kind == "chain"
    assert len(chain.rules) == 2

def test_pick_chain_nested():
    """PickChain can nest inside PickRule (it IS a PickRule variant)."""
    inner = PickChain(rules=[PickBetween(a="X", b="Y")])
    outer = PickChain(rules=[inner, PickLowerOfLine(a="A", b="B")])
    assert len(outer.rules) == 2

def test_pick_rule_discriminator_all_variants():
    """All new variants are accepted by the PickRule discriminated union."""
    variants = [
        {"kind": "between", "a": "A", "b": "B"},
        {"kind": "beyond", "from_point": "O", "past_point": "A"},
        {"kind": "interior", "polygon": "p1"},
        {"kind": "exterior", "polygon": "p1"},
        {"kind": "opposite_side", "line_through": ["A", "B"], "ref_point": "C"},
        {"kind": "upper_of_line", "a": "A", "b": "B"},
        {"kind": "lower_of_line", "a": "A", "b": "B"},
        {"kind": "chain", "rules": [{"kind": "between", "a": "A", "b": "B"}]},
    ]
    from pydantic import TypeAdapter
    ta = TypeAdapter(PickRule)
    for v in variants:
        result = ta.validate_python(v)
        assert result.kind == v["kind"]

def test_reserved_kind_unknown_rejected():
    from pydantic import TypeAdapter, ValidationError
    ta = TypeAdapter(PickRule)
    with pytest.raises(ValidationError):
        ta.validate_python({"kind": "nonexistent"})
