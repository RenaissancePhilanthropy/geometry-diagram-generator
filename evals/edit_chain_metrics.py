"""Pure-function helpers for the pydsl edit-chain reliability eval
(evals/run_edit_chains.py): error categorization, the property-check
resolution shim, and turn-record aggregation. Kept separate from the
harness script so each is independently testable without spinning up a
build_agent()."""
from __future__ import annotations


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
