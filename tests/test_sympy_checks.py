"""Tests for evals/sympy_checks.py's scenario expected_properties validator.

This is the vocabulary the eval harness uses to grade LLM-produced diagrams
(evals/scenarios*.yaml `expected_properties`); an unhandled `type` silently
"passes" (see the `case _` fallback), so every supported type needs direct
coverage here — that's how the `angle_equal` gap (used by dozens of existing
scenarios, never actually checked) went unnoticed.
"""
from __future__ import annotations

import math

from evals.sympy_checks import _validate_properties_sympy


def _check_one(ptype: str, args: list, sym_float: dict, tol: float = 5e-3):
    results = _validate_properties_sympy(
        [{"name": "t", "type": ptype, "args": args}], sym_float, tol=tol
    )
    return results[0]


def test_right_angle_passes_for_true_right_angle():
    sym = {"A": (1, 0), "B": (0, 0), "C": (0, 1)}
    r = _check_one("right_angle", ["A", "B", "C"], sym)
    assert r["passed"]


def test_right_angle_fails_for_non_right_angle():
    sym = {"A": (1, 0), "B": (0, 0), "C": (1, 1)}
    r = _check_one("right_angle", ["A", "B", "C"], sym)
    assert not r["passed"]


def test_angle_bisector_passes():
    # Angle BAC = 90°, bisector AD at 45° from each ray.
    sym = {
        "A": (0, 0),
        "B": (1, 0),
        "C": (0, 1),
        "D": (1, 1),  # along the 45° bisector direction from A
    }
    r = _check_one("angle_bisector", ["D", "A", "B", "C"], sym)
    assert r["passed"]


def test_angle_bisector_fails_when_not_bisecting():
    sym = {
        "A": (0, 0),
        "B": (1, 0),
        "C": (0, 1),
        "D": (1, 0.1),  # far from the 45° bisector
    }
    r = _check_one("angle_bisector", ["D", "A", "B", "C"], sym)
    assert not r["passed"]


def test_angle_equal_passes_for_congruent_angles():
    # Angle BAC = 90° (at A); angle EDF = 90° (at D).
    sym = {
        "A": (0, 0), "B": (1, 0), "C": (0, 1),
        "D": (5, 5), "E": (6, 5), "F": (5, 6),
    }
    r = _check_one("angle_equal", [["B", "A", "C"], ["E", "D", "F"]], sym)
    assert r["passed"]


def test_angle_equal_fails_for_different_angles():
    sym = {
        "A": (0, 0), "B": (1, 0), "C": (0, 1),      # 90°
        "D": (5, 5), "E": (6, 5), "F": (6, 5 + 1.7320508),  # ~60°
    }
    r = _check_one("angle_equal", [["B", "A", "C"], ["E", "D", "F"]], sym)
    assert not r["passed"]


def test_angle_value_passes_for_exact_measure():
    # 60° angle at B between rays to C (along +x) and A (rotated 60°).
    rad = math.radians(60)
    sym = {
        "B": (0, 0),
        "C": (4, 0),
        "A": (4 * math.cos(rad), 4 * math.sin(rad)),
    }
    r = _check_one("angle_value", ["C", "B", "A", 60.0], sym)
    assert r["passed"]


def test_angle_value_fails_for_supplement():
    rad = math.radians(120)  # supplement of 60°
    sym = {
        "B": (0, 0),
        "C": (4, 0),
        "A": (4 * math.cos(rad), 4 * math.sin(rad)),
    }
    r = _check_one("angle_value", ["C", "B", "A", 60.0], sym)
    assert not r["passed"]


def test_distance_equals_passes():
    sym = {"A": (0, 0), "M": (3, 0)}
    r = _check_one("distance_equals", [["A", "M"], 3.0], sym)
    assert r["passed"]


def test_distance_equals_fails_for_wrong_distance():
    sym = {"A": (0, 0), "M": (3, 0)}
    r = _check_one("distance_equals", [["A", "M"], 2.0], sym)
    assert not r["passed"]


def test_equal_lengths_passes_for_square():
    sym = {"A": (0, 0), "B": (2, 0), "C": (2, 2), "D": (0, 2)}
    r = _check_one("equal_lengths", [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]], sym)
    assert r["passed"]


def test_equal_lengths_catches_mismatch_beyond_first_pair():
    # AB == BC (both 2), but CD and DA are a different length — a bug in this
    # check once silently ignored every segment after the first two.
    sym = {"A": (0, 0), "B": (2, 0), "C": (2, 2), "D": (0, 5)}
    r = _check_one("equal_lengths", [["A", "B"], ["B", "C"], ["C", "D"], ["D", "A"]], sym)
    assert not r["passed"]


def test_unsupported_type_is_skipped_not_failed():
    r = _check_one("not_a_real_check", [], {})
    assert r["passed"]
    assert "skipped" in r["message"]
