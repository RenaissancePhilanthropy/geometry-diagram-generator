from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from benchmark.db import get_db, get_run, list_results_for_run
from benchmark.import_run import import_from_dir, import_from_manifest

_MINIMAL_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'

_BENCH_PROMPT_IDS = ["right-triangle", "midpoint-segment", "circle-inscribed-triangle"]


def _write_svg(directory: Path, stem: str) -> Path:
    p = directory / f"{stem}.svg"
    p.write_text(_MINIMAL_SVG)
    return p


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_benchmark.db"


def test_import_from_dir_all_present(tmp_path, db_path):
    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    for pid in _BENCH_PROMPT_IDS:
        _write_svg(svgs_dir, pid)

    run_id = import_from_dir("bench_core", svgs_dir, "test label", db_path=db_path)

    conn = get_db(db_path)
    run = get_run(conn, run_id)
    assert run is not None
    assert run["benchmark_id"] == "bench_core"
    assert run["label"] == "test label"

    results = list_results_for_run(conn, run_id)
    assert len(results) == 3
    for r in results:
        assert r["generation_success"] == 1
        assert r["svg_path"] is not None
        assert Path(r["svg_path"]).exists()


def test_import_from_dir_missing_prompt(tmp_path, db_path):
    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    _write_svg(svgs_dir, "right-triangle")

    run_id = import_from_dir("bench_core", svgs_dir, "partial", db_path=db_path)

    conn = get_db(db_path)
    results = list_results_for_run(conn, run_id)
    assert len(results) == 3

    by_prompt = {r["prompt_id"]: r for r in results}
    assert by_prompt["right-triangle"]["generation_success"] == 1
    assert by_prompt["midpoint-segment"]["generation_success"] == 0
    assert by_prompt["circle-inscribed-triangle"]["generation_success"] == 0


def test_import_from_dir_unmatched_file(tmp_path, db_path):
    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    for pid in _BENCH_PROMPT_IDS:
        _write_svg(svgs_dir, pid)
    _write_svg(svgs_dir, "unknown-shape")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_id = import_from_dir("bench_core", svgs_dir, "extra file", db_path=db_path)

    assert any("unknown-shape" in str(w.message) for w in caught)

    conn = get_db(db_path)
    results = list_results_for_run(conn, run_id)
    assert len(results) == 3
    prompt_ids = {r["prompt_id"] for r in results}
    assert "unknown-shape" not in prompt_ids


def test_import_from_manifest_basic(tmp_path, db_path):
    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    for pid in _BENCH_PROMPT_IDS:
        _write_svg(svgs_dir, pid)

    manifest_path = tmp_path / "manifest.jsonl"
    lines = [
        {
            "prompt_id": "right-triangle",
            "svg_path": str(svgs_dir / "right-triangle.svg"),
            "metadata": {"strategy": "structured", "model": "claude-sonnet-4-6", "duration_s": 12.3},
        },
        {
            "prompt_id": "midpoint-segment",
            "svg_path": str(svgs_dir / "midpoint-segment.svg"),
        },
        {
            "prompt_id": "circle-inscribed-triangle",
            "svg_path": str(svgs_dir / "circle-inscribed-triangle.svg"),
            "metadata": {"strategy": "raw_code"},
        },
    ]
    manifest_path.write_text("\n".join(json.dumps(l) for l in lines))

    run_id = import_from_manifest("bench_core", manifest_path, "manifest run", db_path=db_path)

    conn = get_db(db_path)
    run = get_run(conn, run_id)
    assert run is not None

    results = list_results_for_run(conn, run_id)
    assert len(results) == 3
    by_prompt = {r["prompt_id"]: r for r in results}

    assert by_prompt["right-triangle"]["generation_success"] == 1
    assert by_prompt["right-triangle"]["metadata"] == {
        "strategy": "structured",
        "model": "claude-sonnet-4-6",
        "duration_s": 12.3,
    }
    assert by_prompt["midpoint-segment"]["generation_success"] == 1
    assert by_prompt["midpoint-segment"]["metadata"] is None
    assert by_prompt["circle-inscribed-triangle"]["metadata"] == {"strategy": "raw_code"}


def test_import_from_manifest_unknown_prompt_id(tmp_path, db_path):
    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    _write_svg(svgs_dir, "right-triangle")
    _write_svg(svgs_dir, "nonexistent-shape")

    manifest_path = tmp_path / "manifest.jsonl"
    lines = [
        {
            "prompt_id": "right-triangle",
            "svg_path": str(svgs_dir / "right-triangle.svg"),
        },
        {
            "prompt_id": "nonexistent-shape",
            "svg_path": str(svgs_dir / "nonexistent-shape.svg"),
        },
    ]
    manifest_path.write_text("\n".join(json.dumps(l) for l in lines))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_id = import_from_manifest("bench_core", manifest_path, "unknown id test", db_path=db_path)

    assert any("nonexistent-shape" in str(w.message) for w in caught)

    conn = get_db(db_path)
    results = list_results_for_run(conn, run_id)
    prompt_ids = {r["prompt_id"] for r in results}
    assert "nonexistent-shape" not in prompt_ids
    assert len(results) == 3
    by_prompt = {r["prompt_id"]: r for r in results}
    assert by_prompt["right-triangle"]["generation_success"] == 1
