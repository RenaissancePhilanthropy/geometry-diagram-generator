"""Tests for evals/edit_chain_metrics.py."""
from __future__ import annotations

from evals.edit_chain_metrics import aggregate_turn_records
from evals.edit_chain_metrics import categorize_edit_error
from evals.edit_chain_metrics import circuit_breaker_tripped
from evals.edit_chain_metrics import resolve_and_validate_properties
from evals.edit_chain_metrics import update_circuit_breaker_tally


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


def test_categorizes_search_replace_errors():
    assert categorize_edit_error(
        "search_replace block 0: old_string not found: 'b = point(9, 9)'"
    ) == "no_match"
    assert categorize_edit_error(
        "search_replace block 0: old_string is ambiguous (2 matches): 'point(0, 0)'"
    ) == "ambiguous_match"


def test_categorizes_hashline_errors():
    assert categorize_edit_error(
        "hashline op references a stale or unknown tag: '1:zz'"
    ) == "stale_tag"
    assert categorize_edit_error(
        "hashline ops overlap or are out of order at line 1 (previous op ended at line 1); "
        "ops must reference non-overlapping, non-decreasing line ranges"
    ) == "invalid_op_order"
    assert categorize_edit_error(
        "block_replace end_tag '2:b2' (line 2) is before start_tag '3:c3' (line 3)"
    ) == "invalid_op_order"


def test_categorizes_line_number_errors():
    assert categorize_edit_error(
        "line_number op has an invalid line reference in 'line': '5' (script has 2 lines)"
    ) == "invalid_line"
    assert categorize_edit_error(
        "line_number op has an invalid line reference in 'after': 'not-a-number'"
    ) == "invalid_line"
    assert categorize_edit_error(
        "line 2 does not match expected content: expected 'x', got 'y'"
    ) == "content_mismatch"
    assert categorize_edit_error(
        "line_number ops overlap or are out of order at line 1 (previous op ended at line 1); "
        "ops must reference non-overlapping, non-decreasing line ranges"
    ) == "invalid_op_order"
    assert categorize_edit_error(
        "block_replace end_line 2 is before start_line 3"
    ) == "invalid_op_order"


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


def test_update_circuit_breaker_tally_counts_failures_excluding_content_mismatch():
    tally = {"total": 0, "failed": 0, "categories": {}}
    records = [
        _record(success=True),
        _record(success=False, error_category="context_mismatch"),
        _record(success=False, error_category="content_mismatch"),
    ]
    tally = update_circuit_breaker_tally(tally, records)
    assert tally == {"total": 3, "failed": 1, "categories": {"context_mismatch": 1}}


def test_update_circuit_breaker_tally_counts_cascade_failures():
    # Unlike aggregate_turn_records, cascade turns (prior_failure_count > 0)
    # still count — the circuit breaker asks a different question.
    tally = {"total": 0, "failed": 0, "categories": {}}
    records = [
        _record(success=False, error_category="sandbox_error", prior_failure_count=0),
        _record(success=False, error_category="sandbox_error", prior_failure_count=1),
    ]
    tally = update_circuit_breaker_tally(tally, records)
    assert tally == {"total": 2, "failed": 2, "categories": {"sandbox_error": 2}}


def test_update_circuit_breaker_tally_accumulates_across_calls():
    tally = {"total": 0, "failed": 0, "categories": {}}
    tally = update_circuit_breaker_tally(tally, [_record(success=False, error_category="other")])
    tally = update_circuit_breaker_tally(tally, [_record(success=True)])
    assert tally == {"total": 2, "failed": 1, "categories": {"other": 1}}


def test_update_circuit_breaker_tally_treats_missing_category_as_other():
    tally = {"total": 0, "failed": 0, "categories": {}}
    tally = update_circuit_breaker_tally(tally, [_record(success=False, error_category=None)])
    assert tally == {"total": 1, "failed": 1, "categories": {"other": 1}}


def test_circuit_breaker_tripped_requires_minimum_sample_size():
    # 100% failure but under the floor — not eligible to trip yet.
    assert circuit_breaker_tripped({"total": 19, "failed": 19, "categories": {}}) is False


def test_circuit_breaker_tripped_at_threshold_and_above():
    assert circuit_breaker_tripped({"total": 20, "failed": 15, "categories": {}}) is True  # exactly 75%
    assert circuit_breaker_tripped({"total": 20, "failed": 16, "categories": {}}) is True  # 80%


def test_circuit_breaker_tripped_below_threshold():
    assert circuit_breaker_tripped({"total": 20, "failed": 14, "categories": {}}) is False  # 70%


def test_circuit_breaker_tripped_handles_empty_tally():
    assert circuit_breaker_tripped({"total": 0, "failed": 0, "categories": {}}) is False
