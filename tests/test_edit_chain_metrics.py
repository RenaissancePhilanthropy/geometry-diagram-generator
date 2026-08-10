"""Tests for evals/edit_chain_metrics.py."""
from __future__ import annotations

from evals.edit_chain_metrics import aggregate_turn_records
from evals.edit_chain_metrics import categorize_edit_error
from evals.edit_chain_metrics import resolve_and_validate_properties


def test_categorizes_context_mismatch_errors():
    assert categorize_edit_error(
        "patch context mismatch at line 22: expected 'A.label(\"A\")\\n', patch has '# comment\\n'"
    ) == "context_mismatch"
    assert categorize_edit_error("patch contains no recognizable @@ hunks") == "context_mismatch"
    assert categorize_edit_error(
        "hunk header at old-file line 3 points backward before the previous hunk's end (line 5); "
        "hunks must be in non-decreasing order"
    ) == "context_mismatch"
    assert categorize_edit_error("invalid hunk header line number: '@@ -0,1 +0,1 @@'") == "context_mismatch"


def test_categorizes_sandbox_errors():
    assert categorize_edit_error(
        "patch-mode script failed: Code execution failed at line 'draw(tri, fill_color=\"blue\")' "
        "due to: TypeError: draw() got an unexpected keyword argument 'fill_color'"
    ) == "sandbox_error"


def test_categorizes_exhausted_retries():
    assert categorize_edit_error(
        "PythonFullStrategy failed after 3 attempts. Last error: some sandbox error"
    ) == "exhausted_retries"


def test_categorizes_unrecognized_errors_as_other():
    assert categorize_edit_error("connection reset by peer") == "other"
    assert categorize_edit_error("") == "other"


def test_resolve_and_validate_properties_resolves_known_names():
    expected_properties = [
        {"name": "right angle at A", "type": "right_angle", "args": ["B", "A", "C"]},
    ]
    variable_ids = {"A": "__pydsl_pt_1", "B": "__pydsl_pt_2", "C": "__pydsl_pt_3"}
    sym_table = {
        "__pydsl_pt_1": (0.0, 0.0),
        "__pydsl_pt_2": (4.0, 0.0),
        "__pydsl_pt_3": (0.0, 3.0),
    }
    results = resolve_and_validate_properties(expected_properties, variable_ids, sym_table)
    assert len(results) == 1
    assert results[0]["passed"] is True


def test_resolve_and_validate_properties_skips_unresolved_names_without_failing():
    expected_properties = [
        {"name": "right angle at A", "type": "right_angle", "args": ["B", "A", "C"]},
    ]
    # The model named its points differently than the scenario assumed.
    variable_ids = {"p1": "__pydsl_pt_1", "p2": "__pydsl_pt_2", "p3": "__pydsl_pt_3"}
    sym_table = {
        "__pydsl_pt_1": (0.0, 0.0),
        "__pydsl_pt_2": (4.0, 0.0),
        "__pydsl_pt_3": (0.0, 3.0),
    }
    results = resolve_and_validate_properties(expected_properties, variable_ids, sym_table)
    assert len(results) == 1
    assert results[0]["passed"] is None
    assert "skipped" in results[0]["message"]
    assert "'B'" in results[0]["message"]


def test_resolve_and_validate_properties_handles_a_mix():
    expected_properties = [
        {"name": "resolvable", "type": "right_angle", "args": ["B", "A", "C"]},
        {"name": "unresolvable", "type": "right_angle", "args": ["X", "Y", "Z"]},
    ]
    variable_ids = {"A": "__pydsl_pt_1", "B": "__pydsl_pt_2", "C": "__pydsl_pt_3"}
    sym_table = {
        "__pydsl_pt_1": (0.0, 0.0),
        "__pydsl_pt_2": (4.0, 0.0),
        "__pydsl_pt_3": (0.0, 3.0),
    }
    results = resolve_and_validate_properties(expected_properties, variable_ids, sym_table)
    assert len(results) == 2
    assert results[0]["passed"] is True
    assert results[1]["passed"] is None


def _record(**overrides):
    base = {
        "model": "test-model",
        "edit_generation_mode": "patch",
        "turn_index": 1,
        "success": True,
        "prior_failure_count": 0,
        "error_category": None,
        "script_chars_before": 50,
    }
    base.update(overrides)
    return base


def test_aggregate_turn_records_computes_failure_rate_by_turn_index():
    records = [
        _record(turn_index=1, success=True),
        _record(turn_index=1, success=True),
        _record(turn_index=2, success=False, error_category="context_mismatch"),
        _record(turn_index=2, success=True),
    ]
    summary = aggregate_turn_records(records)
    cell = summary["test-model::patch"]
    assert cell["by_turn_index"][1] == {"total": 2, "failed": 0, "failure_rate": 0.0}
    assert cell["by_turn_index"][2] == {"total": 2, "failed": 1, "failure_rate": 0.5}
    assert cell["error_categories"] == {"context_mismatch": 1}


def test_aggregate_turn_records_excludes_cascade_failures():
    records = [
        _record(turn_index=1, success=False, error_category="sandbox_error", prior_failure_count=0),
        # Cascade: this turn only failed because turn 1 failed first.
        _record(turn_index=2, success=False, error_category="sandbox_error", prior_failure_count=1),
    ]
    summary = aggregate_turn_records(records)
    cell = summary["test-model::patch"]
    # turn_index 1 is included (prior_failure_count == 0); turn_index 2 is excluded entirely.
    assert cell["by_turn_index"][1] == {"total": 1, "failed": 1, "failure_rate": 1.0}
    assert 2 not in cell["by_turn_index"]


def test_aggregate_turn_records_buckets_by_script_size():
    records = [
        _record(script_chars_before=50, success=True),
        _record(script_chars_before=210, success=False, error_category="other"),
    ]
    summary = aggregate_turn_records(records)
    cell = summary["test-model::patch"]
    assert cell["by_script_size_bucket"][0] == {"total": 1, "failed": 0, "failure_rate": 0.0}
    assert cell["by_script_size_bucket"][200] == {"total": 1, "failed": 1, "failure_rate": 1.0}


def test_aggregate_turn_records_separates_model_and_mode_cells():
    records = [
        _record(model="model-a", edit_generation_mode="full_rewrite", success=True),
        _record(model="model-b", edit_generation_mode="patch", success=False, error_category="other"),
    ]
    summary = aggregate_turn_records(records)
    assert set(summary.keys()) == {"model-a::full_rewrite", "model-b::patch"}
