"""
Tests for GenExam filtering and BenchmarkDefinition conversion.
Covers filter_genexam.py (build_benchmark_definition, _tags_from_problem,
should_include) and the extended benchmark/models.py fields (weight, metadata).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from benchmark.models import BenchmarkDefinition, BenchmarkPrompt, RubricItem, load_definition
from benchmark.genexam.filter_genexam import (
    RELEVANCE,
    build_benchmark_definition,
    should_include,
    _tags_from_problem,
    DIFFICULTY_TIER,
)

# ---------------------------------------------------------------------------
# Path to the real JSONL so we can test with actual data
# ---------------------------------------------------------------------------
JSONL_PATH = Path(__file__).parent.parent / "benchmark" / "genexam" / "Mathematics.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    problems = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


# ---------------------------------------------------------------------------
# Extended model fields
# ---------------------------------------------------------------------------

def test_rubric_item_weight_default_none():
    item = RubricItem(id="x", text="y")
    assert item.weight is None


def test_rubric_item_weight_round_trips():
    item = RubricItem(id="x", text="y", weight=0.3)
    assert item.weight == pytest.approx(0.3)


def test_benchmark_prompt_metadata_default_empty():
    p = BenchmarkPrompt(id="p", prompt="Draw something.")
    assert p.metadata == {}


def test_benchmark_prompt_metadata_stored():
    p = BenchmarkPrompt(id="p", prompt="Draw.", metadata={"image_path": "foo/bar.png", "difficulty": "easy"})
    assert p.metadata["image_path"] == "foo/bar.png"
    assert p.metadata["difficulty"] == "easy"


# ---------------------------------------------------------------------------
# Relevance filtering (should_include)
# ---------------------------------------------------------------------------

def test_high_always_included():
    assert should_include("Mathematics_72", include_3d=False, high_only=False) is True
    assert should_include("Mathematics_72", include_3d=False, high_only=True) is True


def test_low_always_excluded():
    assert should_include("Mathematics_45", include_3d=True, high_only=False) is False
    assert should_include("Mathematics_45", include_3d=False, high_only=True) is False


def test_medium_cartesian_included_by_default():
    assert should_include("Mathematics_13", include_3d=False, high_only=False) is True


def test_medium_cartesian_excluded_with_high_only():
    assert should_include("Mathematics_13", include_3d=False, high_only=True) is False


def test_medium_3d_excluded_by_default():
    assert should_include("Mathematics_127", include_3d=False, high_only=False) is False


def test_medium_3d_included_with_flag():
    assert should_include("Mathematics_127", include_3d=True, high_only=False) is True


def test_unknown_id_excluded(capsys):
    result = should_include("Mathematics_9999", include_3d=False, high_only=False)
    assert result is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


# ---------------------------------------------------------------------------
# Relevance table counts — these must stay in sync with the manual counts
# ---------------------------------------------------------------------------

def _count_tiers() -> dict[str, int]:
    from collections import Counter
    counts: Counter = Counter()
    for tier, sub, _ in RELEVANCE.values():
        counts[tier] += 1
    return dict(counts)


def _count_sub(tier: str, sub: str) -> int:
    return sum(1 for t, s, _ in RELEVANCE.values() if t == tier and s == sub)


def test_relevance_high_count():
    counts = _count_tiers()
    # 77 HIGH entries in the hardcoded table
    assert counts["HIGH"] == 77


def test_relevance_medium_cartesian_count():
    assert _count_sub("MEDIUM", "cartesian") == 14


def test_relevance_medium_3d_count():
    assert _count_sub("MEDIUM", "3d") == 11


# ---------------------------------------------------------------------------
# Tags derivation
# ---------------------------------------------------------------------------

def test_tags_include_difficulty():
    p = {"difficulty": "hard", "img_type": "diagrams", "taxonomy": "Mathematics/Plane_Geometry/Triangle"}
    tags = _tags_from_problem(p)
    assert "hard" in tags


def test_tags_include_img_type():
    p = {"difficulty": "easy", "img_type": "geometric shapes", "taxonomy": "Mathematics/Plane_Geometry/Triangle"}
    tags = _tags_from_problem(p)
    assert "geometric shapes" in tags


def test_tags_include_taxonomy_leaves():
    p = {"difficulty": "easy", "img_type": "diagrams", "taxonomy": "Mathematics/Plane_Geometry/Triangle/Right_Triangle"}
    tags = _tags_from_problem(p)
    assert "Triangle" in tags
    assert "Right_Triangle" in tags


def test_tags_empty_for_missing_fields():
    tags = _tags_from_problem({})
    assert tags == []


# ---------------------------------------------------------------------------
# Difficulty → tier mapping
# ---------------------------------------------------------------------------

def test_difficulty_tier_mapping():
    assert DIFFICULTY_TIER["easy"] == 1
    assert DIFFICULTY_TIER["medium"] == 2
    assert DIFFICULTY_TIER["hard"] == 3


# ---------------------------------------------------------------------------
# build_benchmark_definition (unit, with synthetic data)
# ---------------------------------------------------------------------------

SYNTHETIC_PROBLEMS = [
    {
        "id": "Mathematics_72",
        "prompt": "Draw two parallel lines cut by a transversal.",
        "image_path": "Mathematics/Mathematics_72.png",
        "scoring_points": [
            {"question": "Are two parallel lines drawn?", "score": 0.4},
            {"question": "Is a transversal drawn?", "score": 0.4},
            {"question": "Are angle marks shown?", "score": 0.2},
        ],
        "taxonomy": "Mathematics/Plane_Geometry/Parallel_Lines",
        "img_type": "diagrams",
        "difficulty": "easy",
    },
    {
        "id": "Mathematics_45",  # LOW — should be excluded
        "prompt": "Draw area between curves.",
        "image_path": "Mathematics/Mathematics_45.png",
        "scoring_points": [{"question": "Is there a curve?", "score": 1.0}],
        "taxonomy": "Mathematics/Analytic_Geometry/Definite_Integral_Area",
        "img_type": "diagrams",
        "difficulty": "medium",
    },
]


def test_low_problems_excluded():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    ids = [p["id"] for p in defn["prompts"]]
    assert "Mathematics_45" not in ids
    assert "Mathematics_72" in ids


def test_rubric_items_from_scoring_points():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert len(prompt["rubric"]) == 3
    assert prompt["rubric"][0]["id"] == "Mathematics_72_sp0"
    assert prompt["rubric"][0]["text"] == "Are two parallel lines drawn?"
    assert prompt["rubric"][0]["weight"] == pytest.approx(0.4)
    assert prompt["rubric"][0]["category"] == "genexam"


def test_rubric_weights_sum_preserved():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    total = sum(r["weight"] for r in prompt["rubric"])
    assert total == pytest.approx(1.0)


def test_metadata_contains_image_path():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert prompt["metadata"]["image_path"] == "Mathematics/Mathematics_72.png"


def test_metadata_contains_taxonomy():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert prompt["metadata"]["taxonomy"] == "Mathematics/Plane_Geometry/Parallel_Lines"


def test_metadata_relevance_fields():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert prompt["metadata"]["relevance_tier"] == "HIGH"
    assert prompt["metadata"]["relevance_sub"] is None


def test_tier_from_difficulty():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert prompt["tier"] == 1  # easy → 1


def test_reference_svg_is_none():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    prompt = next(p for p in defn["prompts"] if p["id"] == "Mathematics_72")
    assert prompt["reference_svg"] is None


def test_benchmark_id_set():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "my_bench", include_3d=False, high_only=False)
    assert defn["id"] == "my_bench"


def test_shared_rubric_empty():
    defn = build_benchmark_definition(SYNTHETIC_PROBLEMS, "test_bench", include_3d=False, high_only=False)
    assert defn["shared_rubric"] == []


# ---------------------------------------------------------------------------
# Round-trip: YAML → load_definition parses correctly
# ---------------------------------------------------------------------------

def test_round_trip_yaml_parses(tmp_path):
    defn_dict = build_benchmark_definition(SYNTHETIC_PROBLEMS, "round_trip", include_3d=False, high_only=False)
    out = tmp_path / "test_bench.yaml"
    with out.open("w") as fh:
        yaml.dump(defn_dict, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

    loaded = load_definition(out)
    assert loaded.id == "round_trip"
    assert len(loaded.prompts) == 1
    p = loaded.prompts[0]
    assert p.id == "Mathematics_72"
    assert len(p.rubric) == 3
    assert p.rubric[0].weight == pytest.approx(0.4)
    assert p.metadata["image_path"] == "Mathematics/Mathematics_72.png"


# ---------------------------------------------------------------------------
# Integration: run against the real Mathematics.jsonl
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not JSONL_PATH.exists(), reason="Mathematics.jsonl not present")
def test_real_jsonl_default_mode_count():
    problems = load_jsonl(JSONL_PATH)
    defn = build_benchmark_definition(problems, "bench_genexam", include_3d=False, high_only=False)
    # HIGH (77) + MEDIUM-cartesian (14) = 91
    assert len(defn["prompts"]) == 91


@pytest.mark.skipif(not JSONL_PATH.exists(), reason="Mathematics.jsonl not present")
def test_real_jsonl_high_only_count():
    problems = load_jsonl(JSONL_PATH)
    defn = build_benchmark_definition(problems, "bench_genexam", include_3d=False, high_only=True)
    assert len(defn["prompts"]) == 77


@pytest.mark.skipif(not JSONL_PATH.exists(), reason="Mathematics.jsonl not present")
def test_real_jsonl_include_3d_count():
    problems = load_jsonl(JSONL_PATH)
    defn = build_benchmark_definition(problems, "bench_genexam", include_3d=True, high_only=False)
    # HIGH (77) + MEDIUM-cartesian (14) + MEDIUM-3d (11) = 102
    assert len(defn["prompts"]) == 102


@pytest.mark.skipif(not JSONL_PATH.exists(), reason="Mathematics.jsonl not present")
def test_real_jsonl_round_trip(tmp_path):
    problems = load_jsonl(JSONL_PATH)
    defn_dict = build_benchmark_definition(problems, "bench_genexam", include_3d=False, high_only=False)
    out = tmp_path / "bench_genexam.yaml"
    with out.open("w") as fh:
        yaml.dump(defn_dict, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    loaded = load_definition(out)
    assert loaded.id == "bench_genexam"
    assert len(loaded.prompts) == 91
    total_rubric = sum(len(p.rubric) for p in loaded.prompts)
    assert total_rubric > 0
