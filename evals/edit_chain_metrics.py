"""Pure-function helpers for the pydsl edit-chain reliability eval
(evals/run_edit_chains.py): error categorization, the property-check
resolution shim, and turn-record aggregation. Kept separate from the
harness script so each is independently testable without spinning up a
build_agent()."""
from __future__ import annotations

from evals.sympy_checks import _validate_properties_sympy


_SIZE_BUCKET_WIDTH = 200  # characters


def resolve_and_validate_properties(
    expected_properties: list[dict],
    variable_ids: dict,
    sym_table: dict,
) -> list[dict]:
    """Resolve each property's point-name args through variable_ids (script
    variable name -> internal id) before validating against sym_table
    (keyed by internal id — see StructuredRunResult.sym_table). A property
    referencing a name absent from variable_ids is recorded as SKIPPED
    (passed=None), never as a failure: the model may have named the entity
    differently than the scenario assumed, or an earlier turn's failure
    means it was never created — neither is evidence the edit itself was
    unreliable (see design doc, Component A, "Required resolution shim")."""
    results: list[dict] = []
    for prop in expected_properties:
        args = prop.get("args", [])
        resolved_args = []
        unresolved = None
        for name in args:
            resolved_id = variable_ids.get(name)
            if resolved_id is None:
                unresolved = name
                break
            resolved_args.append(resolved_id)

        if unresolved is not None:
            results.append({
                "name": prop.get("name", ""),
                "type": prop.get("type", ""),
                "passed": None,
                "message": f"skipped: {unresolved!r} not in variable_ids",
            })
            continue

        resolved_prop = {**prop, "args": resolved_args}
        results.extend(_validate_properties_sympy([resolved_prop], sym_table))
    return results


def categorize_edit_error(error_message: str) -> str:
    """Coarse category for an edit-turn's error message.

    Categories map to the actual error shapes this project's own code
    produces:
    - "context_mismatch": geometry_diagrams/pydsl/patch.py's
      apply_script_patch ValueErrors ("context mismatch", "no recognizable
      @@ hunks", "hunk header ... points backward", "invalid hunk header").
    - "sandbox_error": geometry_diagrams/strategies/python_full.py's
      _run_from_script wrapping ("patch-mode script failed: ...") — a
      script that patched/generated cleanly but errored when actually run
      (e.g. a hallucinated API call).
    - "exhausted_retries": PythonFullStrategy.run()'s own RuntimeIf a
      full_rewrite turn exhausts its MAX_RETRIES budget ("... failed after
      N attempts. Last error: ...") — never occurs for patch turns, which
      are deliberately unretried.
    - "other": anything else (timeouts, tool-invocation-machinery errors,
      unrecognized shapes).
    """
    if (
        "context mismatch" in error_message
        or "no recognizable" in error_message
        or "hunk header" in error_message
    ):
        return "context_mismatch"
    if "patch-mode script failed" in error_message:
        return "sandbox_error"
    if "failed after" in error_message and "attempts" in error_message:
        return "exhausted_retries"
    return "other"


def aggregate_turn_records(records: list[dict]) -> dict:
    """Bucket failure rate by turn_index and by script-size, restricted to
    clean-prefix turns (prior_failure_count == 0), split by
    (model, edit_generation_mode) — see design doc, Component D. A chain
    that derails early produces cascade failures in later turns; those are
    excluded entirely (not just excluded from being counted as failures)
    since they say nothing about size-driven degradation."""
    clean = [r for r in records if r.get("prior_failure_count", 0) == 0]

    by_cell: dict = {}
    for r in clean:
        cell_key = f"{r['model']}::{r['edit_generation_mode']}"
        cell = by_cell.setdefault(cell_key, {
            "by_turn_index": {}, "by_script_size_bucket": {}, "error_categories": {},
        })

        turn_bucket = cell["by_turn_index"].setdefault(r["turn_index"], {"total": 0, "failed": 0})
        turn_bucket["total"] += 1

        size_key = (r["script_chars_before"] // _SIZE_BUCKET_WIDTH) * _SIZE_BUCKET_WIDTH
        size_bucket = cell["by_script_size_bucket"].setdefault(size_key, {"total": 0, "failed": 0})
        size_bucket["total"] += 1

        if not r["success"]:
            turn_bucket["failed"] += 1
            size_bucket["failed"] += 1
            category = r.get("error_category") or "other"
            cell["error_categories"][category] = cell["error_categories"].get(category, 0) + 1

    summary: dict = {}
    for cell_key, cell in by_cell.items():
        summary[cell_key] = {
            "by_turn_index": {
                idx: {**v, "failure_rate": v["failed"] / v["total"] if v["total"] else 0.0}
                for idx, v in sorted(cell["by_turn_index"].items())
            },
            "by_script_size_bucket": {
                size: {**v, "failure_rate": v["failed"] / v["total"] if v["total"] else 0.0}
                for size, v in sorted(cell["by_script_size_bucket"].items())
            },
            "error_categories": dict(cell["error_categories"]),
        }
    return summary
