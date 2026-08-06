# tests/test_pydsl_marks_and_holes.py
"""Tests for pydsl's congruence/right-angle mark functions and fill()'s
holes= parameter. MarkSegments/MarkRightAngles/Fill.holes are all
existing IR classes, already fully supported by both to_tikz.py and
to_svg.py, that were never exposed to pydsl until this plan. See
docs/superpowers/specs/2026-08-05-pydsl-marks-and-fill-holes-design.md
for the full design rationale, including a real wrinkle: mark_proportional()
renders visually IDENTICAL to mark_equal() (no separate symbol set exists
for "proportional" in either renderer) — kept anyway per explicit user
choice for a script's own semantic clarity, not visual distinction."""
import pytest

from geometry_diagrams.pydsl.builder import Builder, new_builder_context


def test_fresh_mark_group_returns_prefixed_unique_strings():
    builder = Builder()
    g1 = builder._fresh_mark_group("equal")
    g2 = builder._fresh_mark_group("equal")
    g3 = builder._fresh_mark_group("parallel")
    assert g1 != g2
    assert g1.startswith("equal")
    assert g2.startswith("equal")
    assert g3.startswith("parallel")


def test_fresh_mark_group_parallel_prefix_is_literal():
    """Critical correctness property: both renderers route purely on
    group.startswith("parallel") to pick the chevron symbol cycle instead
    of the tick-mark cycle. A kind="parallel" group string that doesn't
    literally start with "parallel" would silently render as tick marks
    instead of chevrons."""
    builder = Builder()
    g = builder._fresh_mark_group("parallel")
    assert g.startswith("parallel")


def test_fresh_mark_group_non_parallel_kinds_do_not_start_with_parallel():
    builder = Builder()
    assert not builder._fresh_mark_group("equal").startswith("parallel")
    assert not builder._fresh_mark_group("proportional").startswith("parallel")
