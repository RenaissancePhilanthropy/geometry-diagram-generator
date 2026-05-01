"""Tests for curriculum/to_benchmark.py."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from curriculum.to_benchmark import (
    PROPERTY_FORMATTERS,
    _build_rubric,
    _fmt_mark_present,
    build_benchmark_definition,
)
from evals.scenarios import _SUPPORTED_PROPERTY_TYPES


# ---------------------------------------------------------------------------
# 1. All supported property types are covered by formatters
# ---------------------------------------------------------------------------

def test_all_property_types_covered():
    assert set(PROPERTY_FORMATTERS.keys()) >= _SUPPORTED_PROPERTY_TYPES


# ---------------------------------------------------------------------------
# 2. Each formatter produces a non-empty string for representative args
# ---------------------------------------------------------------------------

_FORMATTER_SAMPLE_ARGS: dict[str, list] = {
    "right_angle": ["A", "C", "B"],
    "collinear": ["A", "B", "C"],
    "equal_lengths": [["A", "B"], ["C", "D"]],
    "parallel": [["A", "B"], ["C", "D"]],
    "perpendicular": [["A", "B"], ["C", "D"]],
    "midpoint": ["M", "A", "B"],
    "point_on_line": ["P", "A", "B"],
    "point_on_segment": ["P", "A", "B"],
    "point_on_circle": ["P", "O", "R"],
    "tangent": [["P", "Q"], "O", "T"],
    "angle_equal": [["A", "V1", "B"], ["C", "V2", "D"]],
    "angle_bisector": ["D", "V", "P1", "P2"],
    "mark_present": ["right_angle", "C"],
    "label_present": ["A"],
    "equidistant_from_sides": ["I", "A", "B", "C"],
    "centroid": ["G", "A", "B", "C"],
    "opposite_side": ["P", "Q", "A", "B"],
    "not_between": ["P", "A", "B"],
    "same_side": ["P", "Q", "A", "B"],
    "intersects": [["A", "B"], ["C", "D"]],
}


@pytest.mark.parametrize("prop_type", sorted(_SUPPORTED_PROPERTY_TYPES))
def test_formatters_produce_nonempty_strings(prop_type: str):
    formatter = PROPERTY_FORMATTERS[prop_type]
    args = _FORMATTER_SAMPLE_ARGS[prop_type]
    result = formatter(args)
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 3. Weights sum to 1.0 for a known fixture scenario
# ---------------------------------------------------------------------------

_FIXTURE_SCENARIO = {
    "id": "test-scenario-1",
    "tier": 1,
    "tags": ["test"],
    "prompt": "Draw a right triangle.",
    "expected_properties": [
        {"name": "right_angle_at_C", "type": "right_angle", "args": ["A", "C", "B"]},
        {"name": "label_A", "type": "label_present", "args": ["A"]},
        {"name": "label_B", "type": "label_present", "args": ["B"]},
        {"name": "mark_at_C", "type": "mark_present", "args": ["right_angle", "C"]},
    ],
    "required_labels": ["A", "B", "C"],
    "structural_checks": [],
    "required_entities": [],
    "required_canvas": {},
    "expected_points": {},
    "coordinate_tolerance": 0.0001,
    "queries": [],
}


def test_weights_sum_to_one():
    rubric = _build_rubric(_FIXTURE_SCENARIO)
    total = sum(item["weight"] for item in rubric)
    assert math.isclose(total, 1.0, abs_tol=1e-3), f"weights sum to {total}, expected ~1.0"


# ---------------------------------------------------------------------------
# 4. required_labels deduplication — no duplicate rubric item for covered labels
# ---------------------------------------------------------------------------

_DEDUP_SCENARIO = {
    "id": "test-dedup-1",
    "tier": 1,
    "tags": [],
    "prompt": "Test dedup.",
    "expected_properties": [
        {"name": "label_A", "type": "label_present", "args": ["A"]},
        {"name": "label_B", "type": "label_present", "args": ["B"]},
    ],
    "required_labels": ["A", "B", "C"],  # A and B already covered; C is new
    "structural_checks": [],
    "required_entities": [],
    "required_canvas": {},
    "expected_points": {},
    "coordinate_tolerance": 0.0001,
    "queries": [],
}


def test_label_dedup():
    rubric = _build_rubric(_DEDUP_SCENARIO)
    # Should have 2 label_present from expected_properties + 1 extra for C
    label_texts = [r["text"] for r in rubric if "labeled" in r["text"]]
    # C must appear exactly once
    c_texts = [t for t in label_texts if "point C" in t]
    assert len(c_texts) == 1, f"Expected exactly 1 rubric item for label C, got {c_texts}"
    # A and B must each appear exactly once (no duplicate)
    a_texts = [t for t in label_texts if "point A" in t]
    b_texts = [t for t in label_texts if "point B" in t]
    assert len(a_texts) == 1
    assert len(b_texts) == 1


# ---------------------------------------------------------------------------
# 5. End-to-end: convert 3 fixture scenarios, validate with Pydantic
# ---------------------------------------------------------------------------

_THREE_SCENARIOS = [
    {
        "id": "e2e-scenario-1",
        "tier": 1,
        "tags": ["test"],
        "prompt": "Draw a right triangle ABC.",
        "expected_properties": [
            {"name": "right_angle_at_C", "type": "right_angle", "args": ["A", "C", "B"]},
            {"name": "label_A", "type": "label_present", "args": ["A"]},
        ],
        "required_labels": ["A", "B", "C"],
        "structural_checks": [],
        "required_entities": [],
        "required_canvas": {},
        "expected_points": {},
        "coordinate_tolerance": 0.0001,
        "queries": [],
    },
    {
        "id": "e2e-scenario-2",
        "tier": 2,
        "tags": ["test"],
        "prompt": "Draw two parallel lines.",
        "expected_properties": [
            {"name": "parallel_AB_CD", "type": "parallel", "args": [["A", "B"], ["C", "D"]]},
        ],
        "required_labels": ["A", "B", "C", "D"],
        "structural_checks": [],
        "required_entities": [],
        "required_canvas": {},
        "expected_points": {},
        "coordinate_tolerance": 0.0001,
        "queries": [],
    },
    {
        "id": "e2e-scenario-3",
        "tier": 3,
        "tags": ["test"],
        "prompt": "Draw a triangle with its centroid.",
        "expected_properties": [
            {"name": "centroid_G", "type": "centroid", "args": ["G", "A", "B", "C"]},
            {"name": "label_G", "type": "label_present", "args": ["G"]},
        ],
        "required_labels": ["A", "B", "C", "G"],
        "structural_checks": [],
        "required_entities": [],
        "required_canvas": {},
        "expected_points": {},
        "coordinate_tolerance": 0.0001,
        "queries": [],
    },
]


# ---------------------------------------------------------------------------
# 6. mark_present variant mark types produce sensible rubric text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mark_type,expected_substring", [
    ("tick",              "single tick"),
    ("tick1",             "single tick"),
    ("tick_single",       "single tick"),
    ("double_tick",       "double tick"),
    ("tick2",             "double tick"),
    ("tick_double",       "double tick"),
    ("triple_tick",       "triple tick"),
    ("tick_triple",       "triple tick"),
    ("arc",               "angle arc"),
    ("angle_single",      "angle arc"),
    ("double_arc",        "double angle arc"),
    ("angle_double",      "double angle arc"),
    ("midpoint",          "midpoint"),
    ("radius",            "radius"),
    ("slant_height",      "slant height"),
    ("cross_section",     "cross-section"),
    ("circumference_label", "circumference"),
])
def test_mark_present_variants(mark_type: str, expected_substring: str):
    text = _fmt_mark_present([mark_type, "X"])
    assert isinstance(text, str) and len(text) > 0
    assert expected_substring in text.lower(), (
        f"mark_type={mark_type!r}: expected {expected_substring!r} in {text!r}"
    )


def test_end_to_end_pydantic(tmp_path: Path):
    from benchmark.models import BenchmarkDefinition, load_definition

    definition_dict = build_benchmark_definition(_THREE_SCENARIOS, benchmark_id="test_bench")

    out_path = tmp_path / "test_bench.yaml"
    with out_path.open("w", encoding="utf-8") as fh:
        yaml.dump(definition_dict, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    definition = load_definition(out_path)

    assert isinstance(definition, BenchmarkDefinition)
    assert len(definition.prompts) == 3

    for prompt in definition.prompts:
        assert len(prompt.rubric) > 0, f"Prompt {prompt.id} has empty rubric"
        total = sum(r.weight for r in prompt.rubric if r.weight is not None)
        assert math.isclose(total, 1.0, abs_tol=1e-3), (
            f"Prompt {prompt.id} weights sum to {total}, expected ~1.0"
        )
