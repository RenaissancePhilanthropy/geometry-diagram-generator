"""Answer-label audit: a label that shows a number the request does not state is, in practice,
a computed result. Heuristic, so the cases it must leave alone matter as much as the ones it
catches."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir.answer_audit import audit_answer_labels
from geometry_diagrams.pydsl.sandbox import run_script

TRI = """
canvas((-2, 12), (-2, 10))
a = point(0, 6); b = point(0, 0); c = point(8, 0)
t = triangle(a, b, c); draw(t)
a.label("A"); b.label("B"); c.label("C")
"""
HYP = "In right triangle ABC with the right angle at B, AB = 6 and BC = 8. Find the hypotenuse AC."


def _findings(script: str, request: str = HYP):
    result = run_script(TRI + script, timeout_seconds=60)
    assert result.error is None, result.error
    return audit_answer_labels(result.diagram_ir, request)


# --- what it catches -------------------------------------------------------------------

@pytest.mark.parametrize("label", ["10", "AC = 10", "AC = √(6² + 8²) = 10", "10 cm", "10.0"])
def test_the_solved_value_is_found_however_it_is_written(label):
    (finding,) = _findings(f't.side(a, c).label("{label}")')
    assert 10.0 in finding.numbers and finding.kind == "label_segment" and label in finding.message


def test_free_text_and_angle_labels_are_read_too():
    request = "In triangle ABC, angle A = 50 degrees and angle B = 60 degrees. Find angle C."
    assert _findings('t.angle_at(c).label("70°")', request)
    assert _findings('label_text("C = 180° - 50° - 60° = 70°", at=(4, 8))', request)


def test_a_multiple_of_pi_is_found_when_the_request_has_no_pi():
    request = "A circle with center O and diameter AB = 14 cm. Find the circumference."
    assert _findings('label_text("C = 14π cm", at=(4, 8))', request)


# --- what it leaves alone ----------------------------------------------------------------

@pytest.mark.parametrize("label", ["6", "8", "AB = 6", "6 cm", "x", "?", "AC = ?", "Area = ?", "x°"])
def test_givens_and_the_unknown_are_not_flagged(label):
    assert _findings(f't.side(a, b).label("{label}")') == []


def test_point_names_with_digits_are_never_read():
    result = run_script(TRI + 'p = point(3, 3); p.label("P2"); q = point(4, 4); q.label("A1")', timeout_seconds=60)
    assert audit_answer_labels(result.diagram_ir, HYP) == []


def test_a_formula_without_a_number_is_not_flagged():
    request = "A circle with center O and diameter AB = 14 cm. Find the circumference."
    assert _findings('label_text("Circumference = πd", at=(4, 8))', request) == []


def test_pi_in_the_request_makes_a_pi_label_a_given():
    request = "The arc subtends an angle of 2π/3 at the center of a circle of radius 6. Find its length."
    assert _findings('label_text("2π/3", at=(4, 8))', request) == []


@pytest.mark.parametrize("request_text,label", [
    ("Triangle ABC has AB perpendicular to BC. Find AC.", "90°"),
    ("Points A, B, C are collinear. Find BC.", "180°"),
    ("An equilateral triangle has side 5. Find its area.", "60°"),
    ("Square ABCD has side 4. Find the diagonal.", "90°"),
])
def test_numbers_the_request_implies_are_allowed(request_text, label):
    assert _findings(f't.angle_at(b).label("{label}")', request_text) == []


def test_subscripts_and_exponents_are_not_values():
    assert _findings('t.side(a, b).label("x_1"); t.side(b, c).label("y^{2}"); t.side(a, c).label("a_{12}")') == []


def test_a_request_with_the_number_among_its_own_makes_it_a_given():
    assert _findings('t.side(a, c).label("10")', HYP + " The hypotenuse should come out to 10.") == []


def test_numbers_are_compared_as_numbers_not_text():
    assert _findings('t.side(a, b).label("6.0")') == []
