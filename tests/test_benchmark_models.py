from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmark.models import (
    BenchmarkDefinition,
    BenchmarkPrompt,
    RubricItem,
    load_definition,
)

BENCH_CORE_PATH = Path(__file__).parent.parent / "benchmark" / "definitions" / "bench_core.yaml"


def test_load_bench_core():
    defn = load_definition(BENCH_CORE_PATH)
    assert defn.id == "bench_core"
    assert len(defn.prompts) == 3
    assert len(defn.shared_rubric) == 3


def test_effective_rubric_order():
    defn = load_definition(BENCH_CORE_PATH)
    rubric = defn.effective_rubric("right-triangle")
    ids = [r.id for r in rubric]
    # prompt rubric items come first
    assert ids[:3] == ["angle_B_90", "vertices_labeled", "right_angle_mark"]
    # then shared rubric
    assert ids[3:] == ["labels_readable", "well_proportioned", "no_clipping"]


def test_effective_rubric_unknown_prompt():
    defn = load_definition(BENCH_CORE_PATH)
    with pytest.raises(ValueError, match="Unknown prompt_id"):
        defn.effective_rubric("nonexistent-prompt")


def test_unique_prompt_ids_validator():
    with pytest.raises(ValidationError):
        BenchmarkDefinition(
            id="test",
            prompts=[
                BenchmarkPrompt(id="dup", prompt="first"),
                BenchmarkPrompt(id="dup", prompt="second"),
            ],
        )


def test_rubric_item_default_category():
    item = RubricItem(id="foo", text="bar")
    assert item.category == "custom"


def test_rubric_item_custom_category():
    item = RubricItem(id="foo", text="bar", category="visual_quality")
    assert item.category == "visual_quality"


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        # 'prompts' is required
        BenchmarkDefinition.model_validate({"id": "test"})


def test_missing_prompt_field_raises():
    with pytest.raises(ValidationError):
        # BenchmarkPrompt requires 'id' and 'prompt'
        BenchmarkDefinition.model_validate(
            {"id": "test", "prompts": [{"id": "p1"}]}
        )
