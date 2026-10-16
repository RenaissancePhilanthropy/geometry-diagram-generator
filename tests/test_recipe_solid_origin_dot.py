"""A prism/stack origin that nothing else uses is an anchor, not a point of the
figure: the recipe lowerer gives it no auto dot or label."""
from __future__ import annotations

from geometry_diagrams.ir import ir
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.recipe.lower import lower_to_ir

PRISM = {"op": "prism", "id": "P", "origin": "O", "length": 4, "width": 3, "height": 2}
STACK = {"op": "stack", "id": "S", "origin": "O", "heights": [[1, 2], [2, 1]]}
O = {"op": "point", "id": "O", "coords": [0, 0]}


def _lower(construction, annotations=None):
    return lower_to_ir(RecipeDSL.model_validate(
        {"mode": "grid", "construction": construction, "annotations": annotations or {}}))


def _marked(d):
    dots = {p for r in d.render if isinstance(r, ir.DrawPoints) for p in r.points}
    labels = {r.p for r in d.render if isinstance(r, ir.LabelPoint)}
    return dots, labels


def test_implicit_origin_gets_no_dot_or_label():
    assert _marked(_lower([PRISM])) == (set(), set())


def test_explicit_origin_gets_no_dot_or_label_for_prism_and_stack():
    assert _marked(_lower([O, PRISM])) == (set(), set())
    assert _marked(_lower([O, STACK])) == (set(), set())


def test_origin_used_by_another_op_keeps_dot_and_label():
    seg = {"op": "point", "id": "A", "coords": [6, 0]}
    line = {"op": "segment", "id": "OA", "endpoints": ["O", "A"]}
    d = _lower([O, seg, line, PRISM])
    dots, labels = _marked(d)
    assert "O" in dots and "O" in labels


def test_explicit_label_point_still_labels_an_anchor_origin():
    d = _lower([O, PRISM], {"labels": [{"kind": "label_point", "point": "O", "text": "O"}]})
    assert "O" in {getattr(r, "p", None) for r in d.render if isinstance(r, ir.LabelPoint)}


def test_non_solid_points_are_unaffected():
    a = {"op": "point", "id": "A", "coords": [6, 0]}
    dots, labels = _marked(_lower([O, a, PRISM]))
    assert dots == {"A"} and labels == {"A"}
