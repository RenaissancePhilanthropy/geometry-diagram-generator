"""The measure checks compare purely relatively (tol times the larger compared
magnitude, no absolute floor): the same figure at any uniform scale gets the
same verdict. Covers distance_equals (segments and arcs/sectors), ratio_equal,
radius_equals and the prism volume_equals / true_length_equals."""
from __future__ import annotations

import math

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.to_sympy import compile_defs

SCALES = [1e-3, 1.0, 1e3]
CANVAS = {"xmin": -1e6, "xmax": 1e6, "ymin": -1e6, "ymax": 1e6}


def _pt(i, x, y):
    return {"id": i, "kind": "point_fixed", "x": x, "y": y}


def _seg(i, a, b):
    return {"id": i, "kind": "segment", "a": a, "b": b}


def _sym(*defs):
    return compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": list(defs)}))


def _run(sym, check):
    c = ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [], "checks": [check]}).checks[0]
    return run_checks([c], sym)[0]


# A 0.1% miss passes the default 0.5% tolerance; a 1% miss fails it.
NEAR, FAR = 1.001, 1.01


@pytest.mark.parametrize("s", SCALES)
def test_distance_equals_segment(s):
    sym = _sym(_pt("A", 0, 0), _pt("B", s, 0), _seg("ab", "A", "B"))
    assert _run(sym, {"kind": "distance_equals", "seg": "ab", "expected": s * NEAR}).passed
    assert not _run(sym, {"kind": "distance_equals", "seg": "ab", "expected": s * FAR}).passed


@pytest.mark.parametrize("s", SCALES)
@pytest.mark.parametrize("kind", ["arc_center_start_end", "sector_center_start_end"])
def test_distance_equals_arc_and_sector_use_curve_length(s, kind):
    sym = _sym(
        _pt("O", 0, 0), _pt("A", s, 0), _pt("B", 0, s),
        {"id": "arc", "kind": kind, "center": "O", "start": "A", "end": "B"},
    )
    quarter = math.pi / 2 * s
    assert _run(sym, {"kind": "distance_equals", "seg": "arc", "expected": quarter * NEAR}).passed
    assert not _run(sym, {"kind": "distance_equals", "seg": "arc", "expected": quarter * FAR}).passed


@pytest.mark.parametrize("s", SCALES)
def test_ratio_equal(s):
    # |AB| : |CD| = 2 : 1 against |EF| : |GH| = 2 : 1, and a 1% miss
    pts = [_pt("A", 0, 0), _pt("B", 2 * s, 0), _pt("C", 0, s), _pt("D", 0, 2 * s),
           _pt("E", 0, 0), _pt("F", 0, 2 * s * NEAR), _pt("G", 0, 0), _pt("H", s, 0),
           _pt("I", 0, 0), _pt("J", 0, 2 * s * FAR)]
    segs = [_seg("ab", "A", "B"), _seg("cd", "C", "D"), _seg("ef", "E", "F"),
            _seg("gh", "G", "H"), _seg("ij", "I", "J")]
    sym = _sym(*pts, *segs)
    ok = {"kind": "ratio_equal", "s1": "ab", "s2": "cd", "s3": "ef", "s4": "gh"}
    bad = {"kind": "ratio_equal", "s1": "ab", "s2": "cd", "s3": "ij", "s4": "gh"}
    assert _run(sym, ok).passed
    assert not _run(sym, bad).passed


@pytest.mark.parametrize("s", SCALES)
def test_radius_equals(s):
    sym = _sym(_pt("O", 0, 0), {"id": "c", "kind": "circle_center_radius", "center": "O", "radius": s})
    assert _run(sym, {"kind": "radius_equals", "circle": "c", "expected": s * NEAR}).passed
    assert not _run(sym, {"kind": "radius_equals", "circle": "c", "expected": s * FAR}).passed


def _prism(s):
    return _sym(
        _pt("O", 0, 0),
        {"id": "P", "kind": "rectangular_prism", "origin": "O",
         "length": 4 * s, "width": 3 * s, "height": 2 * s},
        _seg("diag", "P_v000", "P_v111"),
    )


@pytest.mark.parametrize("s", SCALES)
def test_prism_volume_equals_near_exact_without_floor(s):
    sym = _prism(s)
    vol = 24 * s**3
    assert _run(sym, {"kind": "volume_equals", "prism": "P", "expected": vol}).passed
    assert not _run(sym, {"kind": "volume_equals", "prism": "P", "expected": vol * (1 + 1e-6)}).passed
    assert _run(sym, {"kind": "volume_equals", "prism": "P", "expected": vol * NEAR, "tol": 5e-3}).passed
    assert not _run(sym, {"kind": "volume_equals", "prism": "P", "expected": vol * FAR, "tol": 5e-3}).passed


@pytest.mark.parametrize("s", SCALES)
def test_prism_true_length_equals_near_exact_without_floor(s):
    sym = _prism(s)
    d = math.sqrt(29) * s
    assert _run(sym, {"kind": "true_length_equals", "seg": "diag", "expected": d}).passed
    assert not _run(sym, {"kind": "true_length_equals", "seg": "diag", "expected": d * (1 + 1e-6)}).passed
    assert _run(sym, {"kind": "true_length_equals", "seg": "diag", "expected": d * NEAR, "tol": 5e-3}).passed
    assert not _run(sym, {"kind": "true_length_equals", "seg": "diag", "expected": d * FAR, "tol": 5e-3}).passed


# --- zero expected: no scale, so exact-only -----------------------------------

def test_zero_expected_is_exact_only():
    sym = _sym(
        _pt("A", 0, 0), _pt("B", 1e-9, 0), _seg("ab", "A", "B"),
        _pt("O", 0, 0), {"id": "c", "kind": "circle_center_radius", "center": "O", "radius": 1e-9},
    )
    # a tiny nonzero measured value never matches an expected 0 (a zero-length
    # segment or circle cannot be compiled, so the measured-zero side is moot)
    assert not _run(sym, {"kind": "distance_equals", "seg": "ab", "expected": 0}).passed
    assert not _run(sym, {"kind": "radius_equals", "circle": "c", "expected": 0}).passed
