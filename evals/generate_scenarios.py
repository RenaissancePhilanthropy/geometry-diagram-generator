"""Template-based geometry scenario generator.

Each template defines a parameterized construction and emits one or more
scenarios across an axis of label sets, numeric parameters, and phrasings.
Because the prompt prose and the `expected_properties` are derived from the
same template, the generated checks are guaranteed consistent with the
construction.

Usage:
    .venv/bin/python evals/generate_scenarios.py
    .venv/bin/python evals/generate_scenarios.py --tier 2
    .venv/bin/python evals/generate_scenarios.py --output evals/scenarios_generated.yaml
    .venv/bin/python evals/generate_scenarios.py --dry-run
    .venv/bin/python evals/generate_scenarios.py --split-by-tier
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterator
from itertools import islice
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from evals.scenarios import _validate_scenarios

# ---------------------------------------------------------------------------
# Label sets — meaningful variation across vertex naming conventions
# ---------------------------------------------------------------------------

_TRIPLE_LABELS: list[tuple[str, str, str]] = [
    ("A", "B", "C"),
    ("D", "E", "F"),
    ("J", "K", "L"),
    ("M", "N", "O"),
    ("P", "Q", "R"),
    ("S", "T", "U"),
    ("X", "Y", "Z"),
    ("E", "F", "G"),
    ("R", "S", "T"),
    ("U", "V", "W"),
]

_QUAD_LABELS: list[tuple[str, str, str, str]] = [
    ("A", "B", "C", "D"),
    ("E", "F", "G", "H"),
    ("J", "K", "L", "M"),
    ("P", "Q", "R", "S"),
    ("W", "X", "Y", "Z"),
    ("Q", "R", "S", "T"),
]

_PAIR_LABELS: list[tuple[str, str]] = [
    ("A", "B"),
    ("C", "D"),
    ("P", "Q"),
    ("R", "S"),
    ("X", "Y"),
    ("M", "N"),
    ("U", "V"),
    ("E", "F"),
]

# Aux-point candidate pool — used when picking a label not already in `used`
_AUX_POOL = "HKMNDEFLJUVWGITOXYZAB"

# ---------------------------------------------------------------------------
# Numeric parameter sweeps
# ---------------------------------------------------------------------------

# Pythagorean leg pairs (right triangle adjacent sides)
_LEG_PAIRS: list[tuple[int, int]] = [(3, 4), (5, 12), (6, 8), (8, 15), (9, 12)]

# Side lengths for equilateral triangles
_EQ_SIDES: list[int] = [3, 4, 5, 6, 8]

# Apex side lengths for isosceles triangles (leg, base)
_ISO_SIDES: list[tuple[int, int]] = [(5, 6), (6, 4), (8, 6), (10, 8), (7, 5)]

# Square side lengths
_SQ_SIDES: list[int] = [3, 4, 5, 6]

# Rectangle width × height combos
_RECT_DIMS: list[tuple[int, int]] = [(5, 3), (6, 4), (8, 4), (7, 3), (10, 5)]

# Acute triangle angle/side specs (suitable for altitude foot inside base)
_ACUTE_SPECS: list[tuple[int, int, int]] = [
    (60, 70, 6), (50, 80, 5), (55, 65, 6), (65, 55, 7), (45, 80, 5),
]

# Right-triangle leg lengths suitable for the altitude-to-hypotenuse construction
_RT_HYP_LEGS: list[tuple[int, int]] = [(3, 4), (6, 8), (5, 12), (9, 12), (8, 15)]

# Circle radii
_RADII: list[int] = [3, 4, 5, 6, 7]

# ---------------------------------------------------------------------------
# Phrasing variation
# ---------------------------------------------------------------------------

_OPENERS: list[str] = [
    "Draw",
    "Sketch",
    "Construct",
    "Make a diagram of",
    "Show",
    "Create a diagram showing",
    "I need a drawing of",
]


def _opener(idx: int) -> str:
    return _OPENERS[idx % len(_OPENERS)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_label(used: set[str], prefer: list[str] | None = None) -> str:
    """Return a single-letter label not present in `used`, preferring `prefer`."""
    for c in (prefer or []):
        if c not in used:
            return c
    for c in _AUX_POOL:
        if c not in used:
            return c
    raise RuntimeError(f"No free label available; used={used}")


def _scenario(
    *,
    id: str,
    tier: int,
    tags: list[str],
    prompt: str,
    required_labels: list[str],
    expected_properties: list[dict],
    required_entities: list[dict] | None = None,
) -> dict:
    s: dict = {
        "id": id,
        "tier": tier,
        "tags": ["templated", *tags],
        "prompt": prompt,
        "required_labels": required_labels,
        "expected_properties": expected_properties,
    }
    if required_entities:
        s["required_entities"] = required_entities
    return s


# ===========================================================================
# Tier 1 — single shape, no auxiliary constructions
# ===========================================================================

def t1_right_triangle() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for ra in (a, b, c):
            for (l1, l2) in _LEG_PAIRS[:2]:
                others = [v for v in (a, b, c) if v != ra]
                yield _scenario(
                    id=f"tpl-t1-rt-{a}{b}{c}-ra{ra}-{l1}-{l2}",
                    tier=1,
                    tags=["triangle", "right-angle"],
                    prompt=(
                        f"{_opener(idx)} a right triangle {a}{b}{c} with the right "
                        f"angle at {ra}. The two legs adjacent to {ra} have lengths "
                        f"{l1} and {l2}. Label all three vertices and mark the "
                        f"right angle at {ra}."
                    ),
                    required_labels=[a, b, c],
                    expected_properties=[
                        {"name": f"right_angle_at_{ra}", "type": "right_angle",
                         "args": [others[0], ra, others[1]]},
                        {"name": f"right_angle_marked_at_{ra}", "type": "mark_present",
                         "args": ["right_angle", ra]},
                    ],
                )
                idx += 1


def t1_equilateral_triangle() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for side in _EQ_SIDES[:3]:
            yield _scenario(
                id=f"tpl-t1-eq-{a}{b}{c}-s{side}",
                tier=1,
                tags=["triangle", "equilateral"],
                prompt=(
                    f"{_opener(idx)} an equilateral triangle {a}{b}{c} where every "
                    f"side has length {side}. Label all three vertices."
                ),
                required_labels=[a, b, c],
                expected_properties=[
                    {"name": "all_sides_equal", "type": "equal_lengths",
                     "args": [[a, b], [b, c], [c, a]]},
                ],
            )
            idx += 1


def t1_isosceles_triangle() -> Iterator[dict]:
    """Apex at first vertex; the two equal sides are the apex's adjacent sides."""
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (leg, base) in _ISO_SIDES[:3]:
            yield _scenario(
                id=f"tpl-t1-iso-{a}{b}{c}-l{leg}-b{base}",
                tier=1,
                tags=["triangle", "isosceles"],
                prompt=(
                    f"{_opener(idx)} an isosceles triangle {a}{b}{c} where {a}{b} "
                    f"and {a}{c} both have length {leg} and the base {b}{c} has "
                    f"length {base}. Label all three vertices."
                ),
                required_labels=[a, b, c],
                expected_properties=[
                    {"name": f"{a}{b}_eq_{a}{c}", "type": "equal_lengths",
                     "args": [[a, b], [a, c]]},
                ],
            )
            idx += 1


def t1_square() -> Iterator[dict]:
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for side in _SQ_SIDES:
            yield _scenario(
                id=f"tpl-t1-sq-{a}{b}{c}{d}-s{side}",
                tier=1,
                tags=["quadrilateral", "square"],
                prompt=(
                    f"{_opener(idx)} a square {a}{b}{c}{d} with side length {side}. "
                    f"Label all four vertices in order."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": f"right_angle_at_{a}", "type": "right_angle",
                     "args": [d, a, b]},
                    {"name": f"right_angle_at_{b}", "type": "right_angle",
                     "args": [a, b, c]},
                    {"name": f"right_angle_at_{c}", "type": "right_angle",
                     "args": [b, c, d]},
                    {"name": f"right_angle_at_{d}", "type": "right_angle",
                     "args": [c, d, a]},
                    {"name": "all_sides_equal", "type": "equal_lengths",
                     "args": [[a, b], [b, c], [c, d], [d, a]]},
                ],
            )
            idx += 1


def t1_rectangle() -> Iterator[dict]:
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for (w, h) in _RECT_DIMS:
            yield _scenario(
                id=f"tpl-t1-rect-{a}{b}{c}{d}-{w}x{h}",
                tier=1,
                tags=["quadrilateral", "rectangle"],
                prompt=(
                    f"{_opener(idx)} a rectangle {a}{b}{c}{d} with horizontal side "
                    f"length {w} and vertical side length {h}. Label all four "
                    f"vertices in order."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": f"right_angle_at_{a}", "type": "right_angle",
                     "args": [d, a, b]},
                    {"name": f"right_angle_at_{b}", "type": "right_angle",
                     "args": [a, b, c]},
                    {"name": f"right_angle_at_{c}", "type": "right_angle",
                     "args": [b, c, d]},
                    {"name": f"right_angle_at_{d}", "type": "right_angle",
                     "args": [c, d, a]},
                    {"name": "horizontal_sides_equal", "type": "equal_lengths",
                     "args": [[a, b], [d, c]]},
                    {"name": "vertical_sides_equal", "type": "equal_lengths",
                     "args": [[b, c], [a, d]]},
                ],
            )
            idx += 1


def t1_segment_midpoint() -> Iterator[dict]:
    idx = 0
    for (a, b) in _PAIR_LABELS:
        m = _free_label({a, b}, prefer=["M", "N", "K", "P"])
        for length in [4, 6, 8, 10]:
            yield _scenario(
                id=f"tpl-t1-mid-{a}{b}-{m}-l{length}",
                tier=1,
                tags=["segment", "midpoint"],
                prompt=(
                    f"{_opener(idx)} a segment {a}{b} of length {length} and mark "
                    f"its midpoint {m}. Label points {a}, {b}, and {m}."
                ),
                required_labels=[a, b, m],
                expected_properties=[
                    {"name": f"{m}_is_midpoint", "type": "midpoint",
                     "args": [m, a, b]},
                    {"name": f"{m}_on_segment", "type": "point_on_segment",
                     "args": [m, a, b]},
                ],
            )
            idx += 1


def t1_parallel_segments() -> Iterator[dict]:
    idx = 0
    pairs = [
        (("A", "B"), ("C", "D")), (("P", "Q"), ("R", "S")),
        (("E", "F"), ("G", "H")), (("J", "K"), ("L", "M")),
        (("W", "X"), ("Y", "Z")),
    ]
    for ((a, b), (c, d)) in pairs:
        for length in [4, 6, 8]:
            yield _scenario(
                id=f"tpl-t1-par-{a}{b}-{c}{d}-l{length}",
                tier=1,
                tags=["parallel", "segments"],
                prompt=(
                    f"{_opener(idx)} two parallel horizontal segments of length "
                    f"{length}: {a}{b} on top and {c}{d} below it. Label all "
                    f"four endpoints."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": "segments_parallel", "type": "parallel",
                     "args": [[a, b], [c, d]]},
                ],
            )
            idx += 1


def t1_perpendicular_segments() -> Iterator[dict]:
    idx = 0
    pairs = [
        (("A", "B"), ("C", "D")), (("P", "Q"), ("R", "S")),
        (("E", "F"), ("G", "H")), (("J", "K"), ("L", "M")),
        (("W", "X"), ("Y", "Z")),
    ]
    for ((a, b), (c, d)) in pairs:
        for length in [4, 6, 8]:
            yield _scenario(
                id=f"tpl-t1-perp-{a}{b}-{c}{d}-l{length}",
                tier=1,
                tags=["perpendicular", "segments"],
                prompt=(
                    f"{_opener(idx)} two perpendicular segments {a}{b} and {c}{d}, "
                    f"each of length {length}. Label all four endpoints."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": "segments_perpendicular", "type": "perpendicular",
                     "args": [[a, b], [c, d]]},
                ],
            )
            idx += 1


def t1_circle_with_point() -> Iterator[dict]:
    """Circle centered at O with a labeled point P on it."""
    idx = 0
    for (o, p) in [("O", "P"), ("C", "A"), ("M", "T"), ("K", "B"), ("O", "T")]:
        for r in _RADII:
            yield _scenario(
                id=f"tpl-t1-circle-{o}-{p}-r{r}",
                tier=1,
                tags=["circle", "radius"],
                prompt=(
                    f"{_opener(idx)} a circle centered at {o} with radius {r}. "
                    f"Mark a point {p} on the circle. Label both points."
                ),
                required_labels=[o, p],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{p}_on_circle", "type": "point_on_circle",
                     "args": [p, o, p]},
                ],
            )
            idx += 1


# ===========================================================================
# Tier 2 — one shape with one auxiliary construction
# ===========================================================================

def t2_triangle_with_altitude() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:3]:
            h = _free_label({a, b, c}, prefer=["H", "K"])
            yield _scenario(
                id=f"tpl-t2-alt-{a}{b}{c}-{h}-{ang_b}-{ang_c}",
                tier=2,
                tags=["triangle", "altitude", "perpendicular"],
                prompt=(
                    f"{_opener(idx)} an acute triangle {a}{b}{c} where the angle at "
                    f"{b} is {ang_b}° and the angle at {c} is {ang_c}°. Drop the "
                    f"altitude from vertex {a} to side {b}{c}, meeting it at the "
                    f"foot {h}. Mark the right angle at {h} and label all four "
                    f"points."
                ),
                required_labels=[a, b, c, h],
                expected_properties=[
                    {"name": f"right_angle_at_{h}", "type": "right_angle",
                     "args": [a, h, b]},
                    {"name": f"{h}_on_base", "type": "point_on_segment",
                     "args": [h, b, c]},
                    {"name": f"right_angle_marked_at_{h}", "type": "mark_present",
                     "args": ["right_angle", h]},
                ],
            )
            idx += 1


def t2_triangle_with_median() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:3]:
            m = _free_label({a, b, c}, prefer=["M", "N", "K"])
            yield _scenario(
                id=f"tpl-t2-med-{a}{b}{c}-{m}-{ang_b}-{ang_c}",
                tier=2,
                tags=["triangle", "median", "midpoint"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°. Draw the median from vertex {a} "
                    f"to side {b}{c}, meeting at the midpoint {m}. Label all "
                    f"four points."
                ),
                required_labels=[a, b, c, m],
                expected_properties=[
                    {"name": f"{m}_is_midpoint", "type": "midpoint",
                     "args": [m, b, c]},
                    {"name": f"{m}_on_segment", "type": "point_on_segment",
                     "args": [m, b, c]},
                ],
            )
            idx += 1


def t2_triangle_with_angle_bisector() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:3]:
            d = _free_label({a, b, c}, prefer=["D", "E", "P"])
            yield _scenario(
                id=f"tpl-t2-bis-{a}{b}{c}-{d}-{ang_b}-{ang_c}",
                tier=2,
                tags=["triangle", "angle-bisector"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°. Bisect the angle at vertex {a}; "
                    f"the bisector meets side {b}{c} at point {d}. Label all "
                    f"four points."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": f"{d}_bisects_angle_{a}", "type": "angle_bisector",
                     "args": [d, a, b, c]},
                    {"name": f"{d}_on_segment", "type": "point_on_segment",
                     "args": [d, b, c]},
                ],
            )
            idx += 1


def t2_perpendicular_bisector() -> Iterator[dict]:
    idx = 0
    for (a, b) in _PAIR_LABELS:
        used = {a, b}
        m = _free_label(used, prefer=["M", "N"]); used.add(m)
        x = _free_label(used, prefer=["L", "K", "T"])
        for length in [4, 6, 8]:
            yield _scenario(
                id=f"tpl-t2-pb-{a}{b}-{m}-{x}-l{length}",
                tier=2,
                tags=["segment", "perpendicular-bisector"],
                prompt=(
                    f"{_opener(idx)} a segment {a}{b} of length {length} and its "
                    f"perpendicular bisector. The bisector passes through the "
                    f"midpoint {m} of {a}{b} and another point {x} on the "
                    f"bisector line. Mark the right angle at {m}."
                ),
                required_labels=[a, b, m, x],
                expected_properties=[
                    {"name": f"{m}_is_midpoint", "type": "midpoint",
                     "args": [m, a, b]},
                    {"name": "bisector_perpendicular", "type": "perpendicular",
                     "args": [[a, b], [m, x]]},
                    {"name": f"right_angle_marked_at_{m}", "type": "mark_present",
                     "args": ["right_angle", m]},
                ],
            )
            idx += 1


def t2_triangle_with_circumcircle() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:3]:
            o = _free_label({a, b, c}, prefer=["O", "U", "K"])
            yield _scenario(
                id=f"tpl-t2-cc-{a}{b}{c}-{o}-{ang_b}-{ang_c}",
                tier=2,
                tags=["triangle", "circle", "circumcircle"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°, together with its circumscribed "
                    f"circle (passing through all three vertices). Label the "
                    f"circumcenter {o} and all three vertices."
                ),
                required_labels=[a, b, c, o],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{a}_on_circumcircle", "type": "point_on_circle",
                     "args": [a, o, b]},
                    {"name": f"{c}_on_circumcircle", "type": "point_on_circle",
                     "args": [c, o, b]},
                ],
            )
            idx += 1


def t2_triangle_with_incircle() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:3]:
            i = _free_label({a, b, c}, prefer=["I", "J", "Q"])
            yield _scenario(
                id=f"tpl-t2-ic-{a}{b}{c}-{i}-{ang_b}-{ang_c}",
                tier=2,
                tags=["triangle", "circle", "incircle"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°, together with its inscribed "
                    f"circle (the largest circle that fits inside). Label the "
                    f"incenter {i} and all three vertices."
                ),
                required_labels=[a, b, c, i],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{i}_equidistant_from_sides", "type": "equidistant_from_sides",
                     "args": [i, a, b, c]},
                ],
            )
            idx += 1


def t2_parallelogram() -> Iterator[dict]:
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for (base, side, ang) in [(6, 4, 60), (8, 5, 70), (5, 5, 80), (7, 4, 65)]:
            yield _scenario(
                id=f"tpl-t2-par-{a}{b}{c}{d}-{base}-{side}-{ang}",
                tier=2,
                tags=["quadrilateral", "parallelogram", "parallel"],
                prompt=(
                    f"{_opener(idx)} a parallelogram {a}{b}{c}{d} with base {a}{b} "
                    f"of length {base} and side {b}{c} of length {side} meeting "
                    f"at an angle of {ang}°. Label all four vertices in order "
                    f"going around."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": f"{a}{b}_parallel_{d}{c}", "type": "parallel",
                     "args": [[a, b], [d, c]]},
                    {"name": f"{b}{c}_parallel_{a}{d}", "type": "parallel",
                     "args": [[b, c], [a, d]]},
                    {"name": f"{a}{b}_eq_{d}{c}", "type": "equal_lengths",
                     "args": [[a, b], [d, c]]},
                    {"name": f"{b}{c}_eq_{a}{d}", "type": "equal_lengths",
                     "args": [[b, c], [a, d]]},
                ],
            )
            idx += 1


def t2_rhombus() -> Iterator[dict]:
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for (side, ang) in [(5, 60), (6, 70), (4, 80), (7, 65), (5, 75)]:
            yield _scenario(
                id=f"tpl-t2-rh-{a}{b}{c}{d}-s{side}-{ang}",
                tier=2,
                tags=["quadrilateral", "rhombus", "parallel"],
                prompt=(
                    f"{_opener(idx)} a rhombus {a}{b}{c}{d} where every side has "
                    f"length {side} and the angle at {a} measures {ang}°. Label "
                    f"all four vertices in order."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": "all_sides_equal", "type": "equal_lengths",
                     "args": [[a, b], [b, c], [c, d], [d, a]]},
                    {"name": f"{a}{b}_parallel_{d}{c}", "type": "parallel",
                     "args": [[a, b], [d, c]]},
                    {"name": f"{b}{c}_parallel_{a}{d}", "type": "parallel",
                     "args": [[b, c], [a, d]]},
                ],
            )
            idx += 1


def t2_trapezoid() -> Iterator[dict]:
    """A trapezoid with one pair of parallel sides (AB || DC)."""
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for (top, bot, h) in [(4, 8, 3), (5, 9, 4), (3, 7, 3), (6, 10, 4)]:
            yield _scenario(
                id=f"tpl-t2-trap-{a}{b}{c}{d}-{top}-{bot}-{h}",
                tier=2,
                tags=["quadrilateral", "trapezoid", "parallel"],
                prompt=(
                    f"{_opener(idx)} a trapezoid {a}{b}{c}{d} where the parallel "
                    f"sides are {a}{b} (length {top}, on top) and {d}{c} (length "
                    f"{bot}, on the bottom). The vertical distance between the "
                    f"parallel sides is {h}. Label all four vertices in order."
                ),
                required_labels=[a, b, c, d],
                expected_properties=[
                    {"name": f"{a}{b}_parallel_{d}{c}", "type": "parallel",
                     "args": [[a, b], [d, c]]},
                ],
            )
            idx += 1


def t2_chord_in_circle() -> Iterator[dict]:
    """Two distinct points on a circle define a chord."""
    idx = 0
    for (o, p, q) in [
        ("O", "A", "B"), ("C", "P", "Q"), ("M", "X", "Y"),
        ("O", "R", "S"), ("K", "U", "V"),
    ]:
        for r in _RADII[:3]:
            yield _scenario(
                id=f"tpl-t2-chord-{o}-{p}{q}-r{r}",
                tier=2,
                tags=["circle", "chord"],
                prompt=(
                    f"{_opener(idx)} a circle centered at {o} with radius {r}. "
                    f"Mark two distinct points {p} and {q} on the circle and "
                    f"draw the chord {p}{q}. Label all three points."
                ),
                required_labels=[o, p, q],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{p}_on_circle", "type": "point_on_circle",
                     "args": [p, o, p]},
                    {"name": f"{q}_on_circle", "type": "point_on_circle",
                     "args": [q, o, p]},
                ],
            )
            idx += 1


# ===========================================================================
# Tier 3 — multi-step / composed constructions
# ===========================================================================

def t3_right_triangle_altitude_to_hypotenuse() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (l1, l2) in _RT_HYP_LEGS[:3]:
            h = _free_label({a, b, c}, prefer=["H", "K"])
            yield _scenario(
                id=f"tpl-t3-rt-alt-{a}{b}{c}-{h}-{l1}-{l2}",
                tier=3,
                tags=["triangle", "right-angle", "altitude", "advanced"],
                prompt=(
                    f"{_opener(idx)} a right triangle {a}{b}{c} with the right "
                    f"angle at {c}, leg {a}{c} of length {l1}, and leg {b}{c} of "
                    f"length {l2}. Drop the altitude from {c} to the hypotenuse "
                    f"{a}{b}, meeting at point {h}. Mark both right angles (at "
                    f"{c} and at {h}) and label all four points."
                ),
                required_labels=[a, b, c, h],
                expected_properties=[
                    {"name": f"right_angle_at_{c}", "type": "right_angle",
                     "args": [a, c, b]},
                    {"name": f"right_angle_at_{h}", "type": "right_angle",
                     "args": [c, h, a]},
                    {"name": f"{h}_on_hypotenuse", "type": "point_on_segment",
                     "args": [h, a, b]},
                    {"name": f"right_angle_marked_at_{c}", "type": "mark_present",
                     "args": ["right_angle", c]},
                    {"name": f"right_angle_marked_at_{h}", "type": "mark_present",
                     "args": ["right_angle", h]},
                ],
            )
            idx += 1


def t3_medial_triangle() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:2]:
            used: set[str] = {a, b, c}
            d = _free_label(used, prefer=["D", "L"]); used.add(d)
            e = _free_label(used, prefer=["E", "M"]); used.add(e)
            f = _free_label(used, prefer=["F", "N"]); used.add(f)
            yield _scenario(
                id=f"tpl-t3-medial-{a}{b}{c}-{d}{e}{f}-{ang_b}",
                tier=3,
                tags=["triangle", "medial-triangle", "midpoint", "parallel", "advanced"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°. Mark the midpoints {d} of side "
                    f"{b}{c}, {e} of side {c}{a}, and {f} of side {a}{b}. Then "
                    f"draw the inner triangle {d}{e}{f}. Label all six points."
                ),
                required_labels=[a, b, c, d, e, f],
                expected_properties=[
                    {"name": f"{d}_midpoint_{b}{c}", "type": "midpoint",
                     "args": [d, b, c]},
                    {"name": f"{e}_midpoint_{c}{a}", "type": "midpoint",
                     "args": [e, c, a]},
                    {"name": f"{f}_midpoint_{a}{b}", "type": "midpoint",
                     "args": [f, a, b]},
                    {"name": f"{d}{e}_parallel_{a}{b}", "type": "parallel",
                     "args": [[d, e], [a, b]]},
                    {"name": f"{e}{f}_parallel_{b}{c}", "type": "parallel",
                     "args": [[e, f], [b, c]]},
                    {"name": f"{f}{d}_parallel_{c}{a}", "type": "parallel",
                     "args": [[f, d], [c, a]]},
                ],
            )
            idx += 1


def t3_triangle_centroid_with_medians() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:2]:
            used: set[str] = {a, b, c}
            ma = _free_label(used, prefer=["D", "L"]); used.add(ma)
            mb = _free_label(used, prefer=["E", "M"]); used.add(mb)
            mc = _free_label(used, prefer=["F", "N"]); used.add(mc)
            g = _free_label(used, prefer=["G", "K", "I"]); used.add(g)
            yield _scenario(
                id=f"tpl-t3-cen-{a}{b}{c}-{g}-{ang_b}",
                tier=3,
                tags=["triangle", "centroid", "median", "advanced"],
                prompt=(
                    f"{_opener(idx)} a triangle {a}{b}{c} with angle {b} = {ang_b}° "
                    f"and angle {c} = {ang_c}°. Mark the midpoint {ma} of side "
                    f"{b}{c}, the midpoint {mb} of side {c}{a}, and the midpoint "
                    f"{mc} of side {a}{b}. Draw the three medians {a}{ma}, "
                    f"{b}{mb}, and {c}{mc} — they all meet at the centroid {g}. "
                    f"Label all seven points."
                ),
                required_labels=[a, b, c, ma, mb, mc, g],
                expected_properties=[
                    {"name": f"{g}_is_centroid", "type": "centroid",
                     "args": [g, a, b, c]},
                    {"name": f"{ma}_midpoint_{b}{c}", "type": "midpoint",
                     "args": [ma, b, c]},
                    {"name": f"{mb}_midpoint_{c}{a}", "type": "midpoint",
                     "args": [mb, c, a]},
                    {"name": f"{mc}_midpoint_{a}{b}", "type": "midpoint",
                     "args": [mc, a, b]},
                    {"name": f"{g}_on_median_{a}{ma}", "type": "point_on_segment",
                     "args": [g, a, ma]},
                ],
            )
            idx += 1


def t3_parallel_lines_transversal() -> Iterator[dict]:
    idx = 0
    label_groups = [
        ("P", "Q", "R", "S", "T", "U"),
        ("A", "B", "C", "D", "E", "F"),
        ("J", "K", "L", "M", "N", "O"),
        ("W", "X", "Y", "Z", "G", "H"),
    ]
    for (p, q, r, s, t, u) in label_groups:
        for ang in [40, 55, 65, 75]:
            yield _scenario(
                id=f"tpl-t3-trv-{p}{q}-{r}{s}-{t}{u}-{ang}",
                tier=3,
                tags=["parallel", "transversal", "angles", "advanced"],
                prompt=(
                    f"{_opener(idx)} two parallel horizontal lines: the first "
                    f"passes through points {p} and {q}, and the second passes "
                    f"through points {r} and {s} below it. Then draw a "
                    f"transversal line that makes a {ang}° angle with the lines, "
                    f"crossing the first at point {t} and the second at point "
                    f"{u}. Mark a pair of corresponding angles at {t} and {u} as "
                    f"equal. Label all six points."
                ),
                required_labels=[p, q, r, s, t, u],
                expected_properties=[
                    {"name": "lines_parallel", "type": "parallel",
                     "args": [[p, q], [r, s]]},
                    {"name": f"{t}_on_first_line", "type": "point_on_line",
                     "args": [t, p, q]},
                    {"name": f"{u}_on_second_line", "type": "point_on_line",
                     "args": [u, r, s]},
                    {"name": "corresponding_angles_equal", "type": "angle_equal",
                     "args": [[p, t, u], [r, u, t]]},
                ],
            )
            idx += 1


def t3_isosceles_altitude_bisects() -> Iterator[dict]:
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (leg, base) in _ISO_SIDES[:3]:
            m = _free_label({a, b, c}, prefer=["M", "H", "N"])
            yield _scenario(
                id=f"tpl-t3-iso-alt-{a}{b}{c}-{m}-l{leg}-b{base}",
                tier=3,
                tags=["triangle", "isosceles", "altitude", "midpoint", "advanced"],
                prompt=(
                    f"{_opener(idx)} an isosceles triangle {a}{b}{c} where {a}{b} "
                    f"and {a}{c} are both length {leg} and the base {b}{c} has "
                    f"length {base}. Drop the altitude from the apex {a} to "
                    f"base {b}{c}, meeting at point {m}. Show that {m} is also "
                    f"the midpoint of {b}{c}. Mark the right angle at {m} and "
                    f"label all four points."
                ),
                required_labels=[a, b, c, m],
                expected_properties=[
                    {"name": f"{a}{b}_eq_{a}{c}", "type": "equal_lengths",
                     "args": [[a, b], [a, c]]},
                    {"name": f"right_angle_at_{m}", "type": "right_angle",
                     "args": [a, m, b]},
                    {"name": f"{m}_midpoint_{b}{c}", "type": "midpoint",
                     "args": [m, b, c]},
                    {"name": f"{m}_on_segment_{b}{c}", "type": "point_on_segment",
                     "args": [m, b, c]},
                    {"name": f"right_angle_marked_at_{m}", "type": "mark_present",
                     "args": ["right_angle", m]},
                ],
            )
            idx += 1


def t3_tangent_to_circle() -> Iterator[dict]:
    """Tangent line to a circle is perpendicular to the radius at the point of tangency."""
    idx = 0
    label_groups = [
        ("O", "T", "P", "Q"), ("C", "K", "A", "B"),
        ("M", "T", "U", "V"), ("O", "S", "X", "Y"),
        ("K", "T", "P", "R"),
    ]
    for (o, t, p, q) in label_groups:
        for r in _RADII[:4]:
            yield _scenario(
                id=f"tpl-t3-tan-{o}-{t}-{p}{q}-r{r}",
                tier=3,
                tags=["circle", "tangent", "perpendicular", "advanced"],
                prompt=(
                    f"{_opener(idx)} a circle centered at {o} with radius {r}, "
                    f"and a point {t} on the circle. Draw the tangent line to "
                    f"the circle at {t}, with two labeled points {p} and {q} on "
                    f"that line, one on each side of {t}. Mark the right angle "
                    f"between radius {o}{t} and the tangent line. Label all "
                    f"four points."
                ),
                required_labels=[o, t, p, q],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"tangent_at_{t}", "type": "tangent",
                     "args": [[p, q], o, t]},
                    {"name": "radius_perp_tangent", "type": "perpendicular",
                     "args": [[o, t], [p, q]]},
                    {"name": f"{t}_between_{p}_and_{q}", "type": "point_on_segment",
                     "args": [t, p, q]},
                    {"name": f"right_angle_marked_at_{t}", "type": "mark_present",
                     "args": ["right_angle", t]},
                ],
            )
            idx += 1


def t3_cyclic_quadrilateral() -> Iterator[dict]:
    """Four labeled points concyclic on a circle centered at O."""
    idx = 0
    for (a, b, c, d) in _QUAD_LABELS:
        for (o, r) in [("O", 4), ("O", 5), ("O", 6), ("U", 5)]:
            if o in (a, b, c, d):
                continue
            yield _scenario(
                id=f"tpl-t3-cyc-{a}{b}{c}{d}-{o}-r{r}",
                tier=3,
                tags=["quadrilateral", "circle", "cyclic", "advanced"],
                prompt=(
                    f"{_opener(idx)} a circle centered at {o} with radius {r}. "
                    f"Mark four points {a}, {b}, {c}, {d} on the circle going "
                    f"around in order so they form a cyclic quadrilateral "
                    f"{a}{b}{c}{d}. Draw the four sides. Label all five points."
                ),
                required_labels=[a, b, c, d, o],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{a}_on_circle", "type": "point_on_circle",
                     "args": [a, o, b]},
                    {"name": f"{c}_on_circle", "type": "point_on_circle",
                     "args": [c, o, b]},
                    {"name": f"{d}_on_circle", "type": "point_on_circle",
                     "args": [d, o, b]},
                ],
            )
            idx += 1


def t3_two_intersecting_circles() -> Iterator[dict]:
    """Two circles intersecting in two points P and Q."""
    idx = 0
    label_groups = [
        ("O", "C", "P", "Q"), ("M", "N", "A", "B"),
        ("U", "V", "X", "Y"), ("O", "K", "S", "T"),
    ]
    for (o1, o2, p, q) in label_groups:
        for (r1, r2) in [(5, 5), (4, 6), (5, 4), (6, 5)]:
            yield _scenario(
                id=f"tpl-t3-2cir-{o1}{o2}-{p}{q}-{r1}-{r2}",
                tier=3,
                tags=["circle", "intersection", "advanced"],
                prompt=(
                    f"{_opener(idx)} two circles that intersect in two points: the "
                    f"first centered at {o1} with radius {r1}, the second "
                    f"centered at {o2} with radius {r2}. Mark the two "
                    f"intersection points as {p} and {q}. Label all four points."
                ),
                required_labels=[o1, o2, p, q],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{p}_on_first", "type": "point_on_circle",
                     "args": [p, o1, q]},
                    {"name": f"{q}_on_first", "type": "point_on_circle",
                     "args": [q, o1, p]},
                    {"name": f"{p}_on_second", "type": "point_on_circle",
                     "args": [p, o2, q]},
                    {"name": f"{q}_on_second", "type": "point_on_circle",
                     "args": [q, o2, p]},
                ],
            )
            idx += 1


def t3_triangle_circumcircle_with_diameter() -> Iterator[dict]:
    """Right triangle inscribed in a semicircle (Thales' theorem): hypotenuse = diameter."""
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (l1, l2) in _RT_HYP_LEGS[:3]:
            o = _free_label({a, b, c}, prefer=["O", "M", "K"])
            yield _scenario(
                id=f"tpl-t3-thales-{a}{b}{c}-{o}-{l1}-{l2}",
                tier=3,
                tags=["triangle", "right-angle", "circle", "thales", "advanced"],
                prompt=(
                    f"{_opener(idx)} a right triangle {a}{b}{c} with the right "
                    f"angle at {c}, leg {a}{c} = {l1}, and leg {b}{c} = {l2}. "
                    f"Then draw the circle with diameter {a}{b}, with center {o} "
                    f"at the midpoint of {a}{b}. By Thales' theorem the right-"
                    f"angle vertex {c} lies on this circle. Label all four "
                    f"points and mark the right angle at {c}."
                ),
                required_labels=[a, b, c, o],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"right_angle_at_{c}", "type": "right_angle",
                     "args": [a, c, b]},
                    {"name": f"{o}_midpoint_{a}{b}", "type": "midpoint",
                     "args": [o, a, b]},
                    {"name": f"{c}_on_circle", "type": "point_on_circle",
                     "args": [c, o, a]},
                    {"name": f"right_angle_marked_at_{c}", "type": "mark_present",
                     "args": ["right_angle", c]},
                ],
            )
            idx += 1


def t3_triangle_with_two_altitudes() -> Iterator[dict]:
    """Triangle with two altitudes drawn from two different vertices."""
    idx = 0
    for (a, b, c) in _TRIPLE_LABELS:
        for (ang_b, ang_c, side_bc) in _ACUTE_SPECS[:2]:
            used: set[str] = {a, b, c}
            ha = _free_label(used, prefer=["H", "K"]); used.add(ha)
            hb = _free_label(used, prefer=["G", "J", "L"])
            yield _scenario(
                id=f"tpl-t3-2alt-{a}{b}{c}-{ha}-{hb}-{ang_b}",
                tier=3,
                tags=["triangle", "altitude", "perpendicular", "advanced"],
                prompt=(
                    f"{_opener(idx)} an acute triangle {a}{b}{c} with angle {b} = "
                    f"{ang_b}° and angle {c} = {ang_c}°. Drop two altitudes: "
                    f"one from {a} to {b}{c} meeting at foot {ha}, and one from "
                    f"{b} to {a}{c} meeting at foot {hb}. Mark both right angles "
                    f"and label all five points."
                ),
                required_labels=[a, b, c, ha, hb],
                expected_properties=[
                    {"name": f"right_angle_at_{ha}", "type": "right_angle",
                     "args": [a, ha, b]},
                    {"name": f"{ha}_on_base", "type": "point_on_segment",
                     "args": [ha, b, c]},
                    {"name": f"right_angle_at_{hb}", "type": "right_angle",
                     "args": [b, hb, a]},
                    {"name": f"{hb}_on_side", "type": "point_on_segment",
                     "args": [hb, a, c]},
                    {"name": f"right_angle_marked_at_{ha}", "type": "mark_present",
                     "args": ["right_angle", ha]},
                    {"name": f"right_angle_marked_at_{hb}", "type": "mark_present",
                     "args": ["right_angle", hb]},
                ],
            )
            idx += 1


def t3_inscribed_angle_in_semicircle() -> Iterator[dict]:
    """Inscribed angle subtending the diameter is a right angle."""
    idx = 0
    label_groups = [
        ("A", "B", "P", "O"), ("X", "Y", "Z", "M"),
        ("P", "Q", "R", "C"), ("E", "F", "G", "O"),
    ]
    for (a, b, p, o) in label_groups:
        for r in _RADII[:3]:
            yield _scenario(
                id=f"tpl-t3-semi-{a}{b}-{p}-{o}-r{r}",
                tier=3,
                tags=["circle", "inscribed-angle", "semicircle", "advanced"],
                prompt=(
                    f"{_opener(idx)} a circle centered at {o} with radius {r}. "
                    f"Draw the diameter {a}{b} (so {o} is the midpoint of {a}{b}). "
                    f"Mark another point {p} on the circle (not {a} or {b}) and "
                    f"draw segments {a}{p} and {b}{p}. Mark the right angle at "
                    f"{p}. Label all four points."
                ),
                required_labels=[a, b, p, o],
                required_entities=[{"type": "circle"}],
                expected_properties=[
                    {"name": f"{o}_midpoint_{a}{b}", "type": "midpoint",
                     "args": [o, a, b]},
                    {"name": f"{a}_on_circle", "type": "point_on_circle",
                     "args": [a, o, b]},
                    {"name": f"{p}_on_circle", "type": "point_on_circle",
                     "args": [p, o, a]},
                    {"name": f"right_angle_at_{p}", "type": "right_angle",
                     "args": [a, p, b]},
                    {"name": f"right_angle_marked_at_{p}", "type": "mark_present",
                     "args": ["right_angle", p]},
                ],
            )
            idx += 1


# ===========================================================================
# Template registry
# ===========================================================================

_TEMPLATES: list[Callable[[], Iterator[dict]]] = [
    # Tier 1
    t1_right_triangle,
    t1_equilateral_triangle,
    t1_isosceles_triangle,
    t1_square,
    t1_rectangle,
    t1_segment_midpoint,
    t1_parallel_segments,
    t1_perpendicular_segments,
    t1_circle_with_point,
    # Tier 2
    t2_triangle_with_altitude,
    t2_triangle_with_median,
    t2_triangle_with_angle_bisector,
    t2_perpendicular_bisector,
    t2_triangle_with_circumcircle,
    t2_triangle_with_incircle,
    t2_parallelogram,
    t2_rhombus,
    t2_trapezoid,
    t2_chord_in_circle,
    # Tier 3
    t3_right_triangle_altitude_to_hypotenuse,
    t3_medial_triangle,
    t3_triangle_centroid_with_medians,
    t3_parallel_lines_transversal,
    t3_isosceles_altitude_bisects,
    t3_tangent_to_circle,
    t3_cyclic_quadrilateral,
    t3_two_intersecting_circles,
    t3_triangle_circumcircle_with_diameter,
    t3_triangle_with_two_altitudes,
    t3_inscribed_angle_in_semicircle,
]


def generate_all(
    tier_filter: int | None = None,
    cap_per_tier: int | None = None,
) -> list[dict]:
    """Run every template; optionally cap each tier to at most N scenarios."""
    by_tier: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for tpl in _TEMPLATES:
        for s in tpl():
            t = s.get("tier", 1)
            by_tier.setdefault(t, []).append(s)

    out: list[dict] = []
    for tier in sorted(by_tier):
        if tier_filter is not None and tier != tier_filter:
            continue
        items = by_tier[tier]
        if cap_per_tier is not None and len(items) > cap_per_tier:
            items = list(islice(items, cap_per_tier))
        out.extend(items)
    return out


# ===========================================================================
# CLI
# ===========================================================================

def _write_yaml(scenarios: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(
            scenarios, f,
            default_flow_style=False, allow_unicode=True,
            sort_keys=False, width=120,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate templated geometry scenarios at multiple difficulty tiers."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(REPO_ROOT / "evals" / "scenarios_generated.yaml"),
        help="Output YAML path (default: evals/scenarios_generated.yaml)",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Only emit scenarios at this tier",
    )
    parser.add_argument(
        "--cap-per-tier",
        type=int,
        default=200,
        help="Maximum scenarios per tier (default: 200; use 0 for no cap)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats and validate but do not write the YAML file",
    )
    parser.add_argument(
        "--split-by-tier",
        action="store_true",
        help="Write three files (scenarios_easy/medium/hard.yaml) instead of one",
    )
    args = parser.parse_args()

    cap = None if args.cap_per_tier == 0 else args.cap_per_tier
    scenarios = generate_all(tier_filter=args.tier, cap_per_tier=cap)
    validated = _validate_scenarios(scenarios)

    by_tier: dict[int, int] = {}
    for s in validated:
        by_tier[s["tier"]] = by_tier.get(s["tier"], 0) + 1

    print(f"Generated {len(validated)} scenarios from {len(_TEMPLATES)} templates "
          f"(cap_per_tier={cap})")
    for tier in sorted(by_tier):
        print(f"  Tier {tier}: {by_tier[tier]}")

    if args.dry_run:
        print("\n[dry-run] not writing output")
        return

    if args.split_by_tier:
        out_dir = Path(args.output).parent
        tier_names = {1: "easy", 2: "medium", 3: "hard"}
        for tier, name in tier_names.items():
            tier_scenarios = [s for s in validated if s["tier"] == tier]
            if not tier_scenarios:
                continue
            path = out_dir / f"scenarios_{name}.yaml"
            _write_yaml(tier_scenarios, path)
            print(f"Wrote {path} ({len(tier_scenarios)} scenarios)")
    else:
        out_path = Path(args.output)
        _write_yaml(validated, out_path)
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
