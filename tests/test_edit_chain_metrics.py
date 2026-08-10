"""Tests for evals/edit_chain_metrics.py."""
from __future__ import annotations

from evals.edit_chain_metrics import categorize_edit_error


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
