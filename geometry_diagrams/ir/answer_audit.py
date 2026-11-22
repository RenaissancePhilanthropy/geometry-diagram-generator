"""Find labels that show a number the request never states.

A figure that accompanies a question ("find x", "what is the area") should show what the request
gives and name the unknown (x, ?), not the solved value. The prompts say so, but some models write
the answer, or the whole derivation, onto the figure anyway. The request's own numbers are the
givens, so a label with a number that is not among them is, in practice, a computed result.

`audit_answer_labels` reads the text of the labels that can carry a value (segment, angle, free
text, along-arc) and returns the ones with such a number. Point names (`A1`, `P2`) are never read.
It is a heuristic and says so: it knows nothing about what the question asks. A few numbers the
request implies without writing them are allowed (a right angle's 90 when the request says
"perpendicular", and so on), and numbers written as words ("twelve") are not read from the request.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import ir

ANSWER_CHECK_MODES: tuple[str, ...] = ("off", "warn", "retry")

_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
# LaTeX-style sub/superscripts in label text ("x^{2}", "a_1"): their digits are not values.
_SCRIPTS = re.compile(r"[_^](?:\{[^}]*\}|\w)")
# A digit directly before a pi sign is a multiple of pi (an arc length, a circumference).
_PI_MULTIPLE = re.compile(r"\d\s*(?:π|\\pi\b)")
_HAS_PI = re.compile(r"π|\\pi\b|\bpi\b", re.IGNORECASE)

# Numbers a request implies without writing them, keyed by the words that imply them.
_IMPLIED: tuple[tuple[float, re.Pattern], ...] = (
    (90.0, re.compile(r"right angle|right-angled|right triangle|perpendicular|⊥|square|rectangle|altitude|tangent", re.I)),
    (180.0, re.compile(r"straight|supplementary|linear pair|collinear|semicircle|diameter", re.I)),
    (60.0, re.compile(r"equilateral", re.I)),
)


def _numbers(text: str) -> set[float]:
    return {round(float(m), 6) for m in _NUMBER.findall(_SCRIPTS.sub("", text))}


@dataclass(frozen=True)
class AnswerFinding:
    """One label whose text shows a number the request does not state."""
    kind: str     # the label op's kind: label_segment, label_angle, label_free_text, label_along_arc
    text: str
    numbers: tuple[float, ...]   # the label's numbers that the request does not state (-1.0 = a multiple of pi)
    message: str


def audit_answer_labels(diagram: ir.DiagramIR, request_text: str) -> list[AnswerFinding]:
    """Labels in render order whose text has a number that `request_text` does not contain."""
    stated = _numbers(request_text)
    for number, pattern in _IMPLIED:
        if pattern.search(request_text):
            stated.add(number)
    request_has_pi = bool(_HAS_PI.search(request_text))

    findings: list[AnswerFinding] = []
    for op in diagram.render:
        if not isinstance(op, (ir.LabelSegment, ir.LabelAngle, ir.LabelFreeText, ir.LabelAlongArc)):
            continue
        text = op.text or ""
        unstated = sorted(n for n in _numbers(text) if n not in stated)
        if _PI_MULTIPLE.search(text) and not request_has_pi:
            unstated.append(-1.0)
        if unstated:
            findings.append(AnswerFinding(
                op.kind, text, tuple(unstated),
                f'Label "{text}" shows a number the request does not state. A figure shows what the '
                f"request gives and names the unknown (x or ?); remove it unless the question asks for it",
            ))
    return findings


def label_texts(diagram: ir.DiagramIR) -> list[str]:
    """The texts of the labels the audit reads, in render order. What an edit starts from: the
    numbers a stored figure already shows count as stated, its coordinates do not."""
    return [
        op.text for op in diagram.render
        if isinstance(op, (ir.LabelSegment, ir.LabelAngle, ir.LabelFreeText, ir.LabelAlongArc)) and op.text
    ]
