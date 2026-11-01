"""patch.py edge cases: insert-only hunks, blank context lines, no trailing newline."""
from __future__ import annotations

from geometry_diagrams.pydsl.patch import apply_script_patch


def test_insert_only_hunk_at_start():
    out = apply_script_patch("a\nb\n", "@@ -0,0 +1,1 @@\n+z\n")
    assert out == "z\na\nb\n"


def test_insert_only_hunk_after_line():
    out = apply_script_patch("a\nb\n", "@@ -1,0 +2,1 @@\n+z\n")
    assert out == "a\nz\nb\n"


def test_blank_context_line_with_stripped_space():
    script = "a\n\nb\n"
    patch = "@@ -1,3 +1,3 @@\n a\n\n-b\n+c\n"
    assert apply_script_patch(script, patch) == "a\n\nc\n"


def test_patch_without_trailing_newline():
    assert apply_script_patch("a\nb\n", "@@ -2,1 +2,1 @@\n-b\n+c") == "a\nc\n"
