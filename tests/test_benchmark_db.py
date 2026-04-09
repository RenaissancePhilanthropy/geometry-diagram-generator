from __future__ import annotations

from pathlib import Path

import pytest
import sqlite3

from benchmark.db import (
    get_db,
    get_annotations_for_result,
    get_result,
    get_run,
    insert_result,
    insert_run,
    list_results_for_run,
    list_runs,
    upsert_annotation,
)


@pytest.fixture
def conn():
    c = get_db(Path(":memory:"))
    yield c
    c.close()


@pytest.fixture
def db_conn():
    c = get_db(Path(":memory:"))
    yield c
    c.close()


def test_insert_and_get_run(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    row = get_run(conn, "run1")
    assert row is not None
    assert row["run_id"] == "run1"
    assert row["benchmark_id"] == "bench_core"
    assert row["label"] == "Test run"
    assert "created_at" in row


def test_get_run_missing(conn):
    assert get_run(conn, "nope") is None


def test_insert_and_get_result(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", "/tmp/a.svg", "\\draw...", True, {"k": "v"})
    row = get_result(conn, "run1__p1")
    assert row is not None
    assert row["result_id"] == "run1__p1"
    assert row["run_id"] == "run1"
    assert row["prompt_id"] == "p1"
    assert row["svg_path"] == "/tmp/a.svg"
    assert row["tikz_code"] == "\\draw..."
    assert row["generation_success"] == 1
    assert row["metadata"] == {"k": "v"}


def test_get_result_missing(conn):
    assert get_result(conn, "nope") is None


def test_upsert_annotation_insert(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, False, None)
    upsert_annotation(conn, "run1__p1", "angle_B_90", "human:gordon", "human", 1)
    annotations = get_annotations_for_result(conn, "run1__p1")
    assert len(annotations) == 1
    assert annotations[0]["value"] == 1
    assert annotations[0]["annotator_type"] == "human"


def test_upsert_annotation_update(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, False, None)
    upsert_annotation(conn, "run1__p1", "angle_B_90", "human:gordon", "human", 1)
    # update same key with different value
    upsert_annotation(conn, "run1__p1", "angle_B_90", "human:gordon", "human", 0)
    annotations = get_annotations_for_result(conn, "run1__p1")
    assert len(annotations) == 1
    assert annotations[0]["value"] == 0


def test_different_annotators_both_stored(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, False, None)
    upsert_annotation(conn, "run1__p1", "angle_B_90", "human:gordon", "human", 1)
    # Different annotator for same rubric item — should be allowed
    upsert_annotation(conn, "run1__p1", "angle_B_90", "ai:claude-sonnet-4-6", "ai", 0)
    annotations = get_annotations_for_result(conn, "run1__p1")
    assert len(annotations) == 2


def test_get_annotations_for_result(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, False, None)
    upsert_annotation(conn, "run1__p1", "angle_B_90", "human:gordon", "human", 1)
    upsert_annotation(conn, "run1__p1", "vertices_labeled", "human:gordon", "human", 1)
    upsert_annotation(conn, "run1__p1", "right_angle_mark", "human:gordon", "human", 0)
    annotations = get_annotations_for_result(conn, "run1__p1")
    assert len(annotations) == 3
    rubric_ids = {a["rubric_item_id"] for a in annotations}
    assert rubric_ids == {"angle_B_90", "vertices_labeled", "right_angle_mark"}


def test_list_runs(conn):
    insert_run(conn, "run_a", "bench_core", "Alpha")
    insert_run(conn, "run_b", "bench_core", "Beta")
    runs = list_runs(conn)
    assert len(runs) == 2
    ids = [r["run_id"] for r in runs]
    assert "run_a" in ids
    assert "run_b" in ids


def test_list_results_for_run(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, True, None)
    insert_result(conn, "run1__p2", "run1", "p2", None, None, False, None)
    results = list_results_for_run(conn, "run1")
    assert len(results) == 2
    prompt_ids = {r["prompt_id"] for r in results}
    assert prompt_ids == {"p1", "p2"}


def test_result_fk_enforced(db_conn):
    with pytest.raises(sqlite3.IntegrityError):
        insert_result(db_conn, "nonexistent__prompt", "nonexistent_run", "prompt", None, None, False, None)


def test_result_unique_constraint(conn):
    insert_run(conn, "run1", "bench_core", "Test run")
    insert_result(conn, "run1__p1", "run1", "p1", None, None, True, None)
    with pytest.raises(sqlite3.IntegrityError):
        insert_result(conn, "run1__p1", "run1", "p1", None, None, False, None)
