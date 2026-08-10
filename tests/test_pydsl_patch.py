"""Tests for geometry_diagrams/pydsl/patch.py's unified-diff applier."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.patch import apply_script_patch


def test_apply_script_patch_applies_a_single_hunk():
    previous = "a = point(0, 0)\nb = point(1, 0)\nt = triangle(a, b, point(0, 1))\ndraw(t)\n"
    patch_text = (
        "@@ -1,4 +1,4 @@\n"
        " a = point(0, 0)\n"
        "-b = point(1, 0)\n"
        "+b = point(2, 0)\n"
        " t = triangle(a, b, point(0, 1))\n"
        " draw(t)\n"
    )
    result = apply_script_patch(previous, patch_text)
    assert result == "a = point(0, 0)\nb = point(2, 0)\nt = triangle(a, b, point(0, 1))\ndraw(t)\n"


def test_apply_script_patch_supports_insertion_only_hunk():
    previous = "a = point(0, 0)\ndraw_points(a)\n"
    patch_text = (
        "@@ -1,2 +1,3 @@\n"
        " a = point(0, 0)\n"
        "+a.label(\"A\")\n"
        " draw_points(a)\n"
    )
    result = apply_script_patch(previous, patch_text)
    assert result == "a = point(0, 0)\na.label(\"A\")\ndraw_points(a)\n"


def test_apply_script_patch_raises_on_context_mismatch():
    previous = "a = point(0, 0)\nb = point(1, 0)\n"
    patch_text = (
        "@@ -1,2 +1,2 @@\n"
        " a = point(0, 0)\n"
        "-b = point(9, 9)\n"  # doesn't match previous's actual line 2
        "+b = point(2, 0)\n"
    )
    with pytest.raises(ValueError, match="context mismatch"):
        apply_script_patch(previous, patch_text)


def test_apply_script_patch_raises_when_no_hunks_present():
    with pytest.raises(ValueError, match="no recognizable"):
        apply_script_patch("a = point(0, 0)\n", "not a real patch")


def test_apply_script_patch_raises_on_out_of_order_hunk_header():
    # Hunk 1 replaces line 2. Hunk 2's header wrongly points backward to
    # line 2 again, with a context/removal line that happens to still match
    # the *original* (pre-hunk-1) content at that position. Without a
    # monotonicity check, this would silently re-walk already-consumed
    # lines and splice stale content into the output instead of raising.
    previous = (
        "a = point(0, 0)\n"
        "b = point(1, 0)\n"
        "c = point(2, 0)\n"
        "d = point(3, 0)\n"
        "e = point(4, 0)\n"
    )
    patch_text = (
        "@@ -2,1 +2,1 @@\n"
        "-b = point(1, 0)\n"
        "+b = point(9, 9)\n"
        "@@ -2,1 +2,1 @@\n"
        "-b = point(1, 0)\n"
        "+b = point(1, 1)\n"
    )
    with pytest.raises(ValueError, match="backward"):
        apply_script_patch(previous, patch_text)


def test_apply_script_patch_raises_on_negative_hunk_start():
    previous = "a = point(0, 0)\nb = point(1, 0)\n"
    patch_text = (
        "@@ -0,1 +0,1 @@\n"
        "-a = point(0, 0)\n"
        "+a = point(9, 9)\n"
    )
    with pytest.raises(ValueError, match="invalid hunk header"):
        apply_script_patch(previous, patch_text)


def test_apply_script_patch_tolerates_a_missing_trailing_newline_on_a_context_line():
    # LLM-produced patch strings routinely lack a trailing "\n" on their very
    # last line (an artifact of how the value was written into a JSON field,
    # not a real diff signal) — splitlines(keepends=True) then strips that
    # line's newline even though the real script's corresponding line has
    # one, causing a spurious mismatch on otherwise-identical content.
    previous = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\n"
    patch_text = (
        "@@ -1,3 +1,3 @@\n"
        " a = point(0, 0)\n"
        "-b = point(1, 0)\n"
        "+b = point(2, 0)\n"
        " c = point(0, 1)"  # no trailing newline: last line of the whole patch string
    )
    result = apply_script_patch(previous, patch_text)
    assert result == "a = point(0, 0)\nb = point(2, 0)\nc = point(0, 1)\n"


def test_apply_script_patch_tolerates_a_missing_trailing_newline_on_a_removal_line():
    # The removal line is the literal last content of patch_text (no
    # trailing "\n"), and nothing else follows it in the hunk or the patch.
    previous = "a = point(0, 0)\nb = point(1, 0)\n"
    patch_text = "@@ -1,2 +1,1 @@\n a = point(0, 0)\n-b = point(1, 0)"
    result = apply_script_patch(previous, patch_text)
    assert result == "a = point(0, 0)\n"


def test_apply_script_patch_normalizes_a_missing_trailing_newline_on_an_insertion_line():
    # The inserted line is the literal last content of patch_text (no
    # trailing "\n"), but the hunk only covers the first old line, leaving
    # "draw_points(a)\n" as an untouched tail appended after the hunk. Without
    # normalizing the missing newline, the inserted line and the tail would
    # be joined with no separator: "a.label(\"A\")draw_points(a)\n".
    previous = "a = point(0, 0)\ndraw_points(a)\n"
    patch_text = "@@ -1,1 +1,2 @@\n a = point(0, 0)\n+a.label(\"A\")"
    result = apply_script_patch(previous, patch_text)
    assert result == "a = point(0, 0)\na.label(\"A\")\ndraw_points(a)\n"
