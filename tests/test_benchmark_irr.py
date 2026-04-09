"""Tests for benchmark IRR computation."""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmark.irr import cohens_kappa, percent_agreement, compute_irr
from benchmark.db import get_db, insert_run, insert_result, upsert_annotation


# ---------------------------------------------------------------------------
# cohens_kappa unit tests
# ---------------------------------------------------------------------------


def test_perfect_agreement():
    assert cohens_kappa([1, 1, 0, 0], [1, 1, 0, 0]) == 1.0


def test_complete_disagreement():
    kappa = cohens_kappa([1, 1, 0, 0], [0, 0, 1, 1])
    assert kappa == -1.0


def test_random_agreement():
    # All same class → p_e == 1.0 → returns 1.0
    kappa = cohens_kappa([1, 1, 1, 1], [1, 1, 1, 1])
    assert kappa == 1.0


def test_all_zeros_edge_case():
    # p_e == 1.0 (both raters always say no)
    kappa = cohens_kappa([0, 0, 0], [0, 0, 0])
    assert kappa == 1.0


def test_empty_input():
    assert cohens_kappa([], []) == 0.0


def test_fifty_percent_chance_agreement():
    # 50/50 split in each rater, perfect agreement
    # p_e = 0.5 * 0.5 + 0.5 * 0.5 = 0.5; kappa = (1.0 - 0.5) / (1 - 0.5) = 1.0
    kappa = cohens_kappa([1, 0, 1, 0], [1, 0, 1, 0])
    assert kappa == 1.0


# ---------------------------------------------------------------------------
# percent_agreement unit tests
# ---------------------------------------------------------------------------


def test_percent_agreement():
    assert percent_agreement([1, 0, 1, 0], [1, 1, 1, 0]) == 0.75


def test_percent_agreement_empty():
    assert percent_agreement([], []) == 0.0


def test_percent_agreement_perfect():
    assert percent_agreement([1, 0, 1], [1, 0, 1]) == 1.0


# ---------------------------------------------------------------------------
# Helpers for DB-based tests
# ---------------------------------------------------------------------------

_MINIMAL_DEFINITION_YAML = """\
id: test_bench
shared_rubric:
  - id: visual_quality_overall
    text: Diagram is clear and readable
    category: visual_quality
prompts:
  - id: p1
    prompt: Draw a right triangle
    rubric:
      - id: has_right_angle
        text: Has a visible right angle
        category: custom
  - id: p2
    prompt: Draw a circle
    rubric:
      - id: has_circle
        text: Has a circle drawn
        category: custom
"""


def _setup_db(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal DB and definition file. Returns (db_path, def_path)."""
    db_path = tmp_path / "benchmark.db"
    definitions_dir = tmp_path / "definitions"
    definitions_dir.mkdir()
    def_path = definitions_dir / "test_bench.yaml"
    def_path.write_text(_MINIMAL_DEFINITION_YAML)

    conn = get_db(db_path)
    insert_run(conn, "run1", "test_bench", "Test Run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, True, None)
    insert_result(conn, "run1__p2", "run1", "p2", None, None, True, None)

    return db_path, definitions_dir


# ---------------------------------------------------------------------------
# compute_irr DB-based tests
# ---------------------------------------------------------------------------


def test_compute_irr_not_enough_annotators(tmp_path):
    """No annotations → error: not_enough_annotators."""
    db_path, _ = _setup_db(tmp_path)

    # Monkey-patch _DEFINITIONS_DIR in irr module
    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("run1", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert result["kappa"] is None
    assert result["error"] == "not_enough_annotators"


def test_compute_irr_not_enough_data(tmp_path):
    """Only one annotator type present → not_enough_annotators."""
    db_path, _ = _setup_db(tmp_path)
    conn = get_db(db_path)
    # Add only human annotations
    upsert_annotation(conn, "run1__p1", "has_right_angle", "human:alice", "human", 1)

    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("run1", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert result["kappa"] is None
    assert result["error"] == "not_enough_annotators"


def test_compute_irr_perfect(tmp_path):
    """Two annotators agreeing on everything → kappa = 1.0."""
    db_path, _ = _setup_db(tmp_path)
    conn = get_db(db_path)

    rubric_items = [
        ("run1__p1", "has_right_angle"),
        ("run1__p1", "visual_quality_overall"),
        ("run1__p2", "has_circle"),
        ("run1__p2", "visual_quality_overall"),
    ]
    for result_id, item_id in rubric_items:
        upsert_annotation(conn, result_id, item_id, "human:alice", "human", 1)
        upsert_annotation(conn, result_id, item_id, "ai:claude", "ai", 1)

    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("run1", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert result["kappa"] == 1.0
    assert result["percent_agreement"] == 1.0
    assert result["n_pairs"] == 4
    assert result["annotator1"] == "human:alice"
    assert result["annotator2"] == "ai:claude"


def test_compute_irr_explicit_annotators(tmp_path):
    """Explicit annotator pair selection."""
    db_path, _ = _setup_db(tmp_path)
    conn = get_db(db_path)

    upsert_annotation(conn, "run1__p1", "has_right_angle", "human:alice", "human", 1)
    upsert_annotation(conn, "run1__p1", "has_right_angle", "human:bob", "human", 0)
    upsert_annotation(conn, "run1__p1", "visual_quality_overall", "human:alice", "human", 1)
    upsert_annotation(conn, "run1__p1", "visual_quality_overall", "human:bob", "human", 1)

    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("run1", annotator1="human:alice", annotator2="human:bob", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert result["kappa"] is not None
    assert result["n_pairs"] == 2
    # alice=[1,1], bob=[0,1]: agree on item2 only → percent_agreement = 0.5
    assert result["percent_agreement"] == 0.5


def test_compute_irr_run_not_found(tmp_path):
    db_path = tmp_path / "benchmark.db"
    get_db(db_path)  # create empty DB

    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("nonexistent_run", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert result["kappa"] is None
    assert result["error"] == "run_not_found"


def test_compute_irr_by_category(tmp_path):
    """by_category contains expected categories."""
    db_path, _ = _setup_db(tmp_path)
    conn = get_db(db_path)

    rubric_items = [
        ("run1__p1", "has_right_angle", 1, 0),
        ("run1__p1", "visual_quality_overall", 1, 1),
        ("run1__p2", "has_circle", 0, 0),
        ("run1__p2", "visual_quality_overall", 1, 0),
    ]
    for result_id, item_id, v_human, v_ai in rubric_items:
        upsert_annotation(conn, result_id, item_id, "human:alice", "human", v_human)
        upsert_annotation(conn, result_id, item_id, "ai:claude", "ai", v_ai)

    import benchmark.irr as irr_mod
    original = irr_mod._DEFINITIONS_DIR
    irr_mod._DEFINITIONS_DIR = tmp_path / "definitions"
    try:
        result = compute_irr("run1", db_path=db_path)
    finally:
        irr_mod._DEFINITIONS_DIR = original

    assert "by_category" in result
    assert "custom" in result["by_category"]
    assert "visual_quality" in result["by_category"]
    assert result["by_category"]["custom"]["n_pairs"] == 2
    assert result["by_category"]["visual_quality"]["n_pairs"] == 2

    assert "by_item" in result
    item_ids = {item["rubric_item_id"] for item in result["by_item"]}
    assert "has_right_angle" in item_ids
    assert "visual_quality_overall" in item_ids
