"""Tests for LabelPoint, LabelAngle, and LabelFreeText DSL ops lowering to DiagramIR."""
import pytest
from geometry_diagrams.recipe.dsl import (
    RecipeDSL, DSLAnnotations, TriangleOp,
    LabelSegment, LabelPoint as DSLLabelPoint, LabelAngle as DSLLabelAngle,
    LabelFreeText as DSLLabelFreeText,
)
from geometry_diagrams.recipe.lower import lower_to_ir
from geometry_diagrams.ir.ir import (
    LabelPoint as IRLabelPoint,
    LabelAngle as IRLabelAngle,
    LabelSegment as IRLabelSegment,
    LabelFreeText as IRLabelFreeText,
)


def _triangle_dsl(labels=None, auto_label_points=False):
    ann = DSLAnnotations(
        auto_draw_all=False,
        auto_label_points=auto_label_points,
        labels=labels or [],
    )
    return RecipeDSL(
        mode="abstract",
        construction=[
            TriangleOp(
                id="T",
                vertices=["A", "B", "C"],
                spec={"angle_A": 60, "angle_B": 60, "side_AB": 3},
            )
        ],
        annotations=ann,
    )


# ---------------------------------------------------------------------------
# LabelPoint
# ---------------------------------------------------------------------------

def test_label_point_lowers_to_ir_label_point():
    dsl = _triangle_dsl(labels=[
        DSLLabelPoint(point="A", text="A_1", pos="above"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render
               if isinstance(r, IRLabelPoint) and r.p == "A"]
    assert len(matches) == 1
    assert matches[0].text == "A_1"
    assert matches[0].pos == "above"


def test_label_point_with_none_text_keeps_id_as_label():
    dsl = _triangle_dsl(labels=[
        DSLLabelPoint(point="B", pos="below"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render
               if isinstance(r, IRLabelPoint) and r.p == "B"]
    assert len(matches) == 1
    assert matches[0].text is None
    assert matches[0].pos == "below"


def test_label_point_override_replaces_auto_label():
    """With auto_label_points=True, an explicit label_point for A should
    replace (not duplicate) the auto-generated LabelPoint for A."""
    dsl = _triangle_dsl(
        labels=[DSLLabelPoint(point="A", text="A'", pos="above left")],
        auto_label_points=True,
    )
    ir = lower_to_ir(dsl)
    a_labels = [r for r in ir.render
                if isinstance(r, IRLabelPoint) and r.p == "A"]
    assert len(a_labels) == 1
    assert a_labels[0].text == "A'"
    assert a_labels[0].pos == "above left"

    # B and C should still be auto-labeled
    other_ps = {r.p for r in ir.render
                if isinstance(r, IRLabelPoint) and r.p != "A"}
    assert other_ps == {"B", "C"}


# ---------------------------------------------------------------------------
# LabelAngle
# ---------------------------------------------------------------------------

def test_label_angle_explicit_form_lowers_to_ir_label_angle():
    dsl = _triangle_dsl(labels=[
        DSLLabelAngle(a="B", vertex="A", b="C", text="α"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render if isinstance(r, IRLabelAngle)]
    assert len(matches) == 1
    assert matches[0].text == "α"
    assert matches[0].angle.o == "A"
    assert {matches[0].angle.a, matches[0].angle.b} == {"B", "C"}


def test_label_angle_shorthand_form_lowers():
    dsl = _triangle_dsl(labels=[
        DSLLabelAngle(at="A", of="T", text="60°"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render if isinstance(r, IRLabelAngle)]
    assert len(matches) == 1
    assert matches[0].text == "60°"
    assert matches[0].angle.o == "A"
    assert {matches[0].angle.a, matches[0].angle.b} == {"B", "C"}


# ---------------------------------------------------------------------------
# LabelSegment (regression guard)
# ---------------------------------------------------------------------------

def test_label_segment_still_lowers():
    dsl = _triangle_dsl(labels=[
        LabelSegment(endpoints=["A", "B"], text="c"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render if isinstance(r, IRLabelSegment)]
    assert len(matches) == 1
    assert matches[0].text == "c"


# ---------------------------------------------------------------------------
# Mixed
# ---------------------------------------------------------------------------

def test_mixed_label_kinds_all_lower():
    dsl = _triangle_dsl(labels=[
        LabelSegment(endpoints=["A", "B"], text="c"),
        DSLLabelPoint(point="C", text="C'", pos="above"),
        DSLLabelAngle(a="B", vertex="A", b="C", text="α"),
    ])
    ir = lower_to_ir(dsl)
    assert sum(isinstance(r, IRLabelSegment) for r in ir.render) == 1
    assert sum(isinstance(r, IRLabelPoint) for r in ir.render) == 1
    assert sum(isinstance(r, IRLabelAngle) for r in ir.render) == 1


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_label_angle_rejects_missing_form():
    import pytest
    with pytest.raises(Exception):
        DSLLabelAngle(text="α")  # neither explicit nor shorthand


def test_label_angle_rejects_both_forms():
    with pytest.raises(Exception):
        DSLLabelAngle(a="B", vertex="A", b="C", at="A", of="T", text="α")


# ---------------------------------------------------------------------------
# LabelFreeText
# ---------------------------------------------------------------------------

def test_label_free_text_at_lowers_to_ir():
    dsl = _triangle_dsl(labels=[
        DSLLabelFreeText(text="s^{2} = r^{2} + h^{2}", at=[3.0, 1.5]),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render if isinstance(r, IRLabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "s^{2} = r^{2} + h^{2}"
    assert matches[0].at == [3.0, 1.5]
    assert matches[0].centroid_of is None


def test_label_free_text_centroid_of_lowers_to_ir():
    dsl = _triangle_dsl(labels=[
        DSLLabelFreeText(text="I", centroid_of="T"),
    ])
    ir = lower_to_ir(dsl)
    matches = [r for r in ir.render if isinstance(r, IRLabelFreeText)]
    assert len(matches) == 1
    assert matches[0].text == "I"
    assert matches[0].centroid_of == "T"
    assert matches[0].at is None


def test_label_free_text_rejects_neither():
    with pytest.raises(Exception):
        DSLLabelFreeText(text="x")  # neither at nor centroid_of


def test_label_free_text_rejects_both():
    with pytest.raises(Exception):
        DSLLabelFreeText(text="x", at=[1.0, 2.0], centroid_of="T")
