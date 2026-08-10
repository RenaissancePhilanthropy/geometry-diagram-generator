"""Tests for geometry_diagrams/pydsl/search_replace.py."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.search_replace import SearchReplaceError, apply_search_replace


def test_apply_search_replace_single_block():
    script = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
    blocks = [{"old_string": "b = point(1, 0)", "new_string": "b = point(2, 0)"}]
    result = apply_search_replace(script, blocks)
    assert result == "a = point(0, 0)\nb = point(2, 0)\ndraw_points(a, b)\n"


def test_apply_search_replace_sequential_blocks_where_second_depends_on_first():
    # Block 2's old_string only exists in the buffer AFTER block 1 runs —
    # this is Aider's real sequential-matching semantics, not simultaneous
    # matching against the original script.
    script = "a = point(0, 0)\n"
    blocks = [
        {"old_string": "a = point(0, 0)", "new_string": "a = point(1, 1)\nb = point(2, 2)"},
        {"old_string": "b = point(2, 2)", "new_string": "b = point(3, 3)"},
    ]
    result = apply_search_replace(script, blocks)
    assert result == "a = point(1, 1)\nb = point(3, 3)\n"


def test_apply_search_replace_raises_on_not_found():
    script = "a = point(0, 0)\n"
    blocks = [{"old_string": "b = point(9, 9)", "new_string": "b = point(1, 1)"}]
    with pytest.raises(SearchReplaceError, match="not found"):
        apply_search_replace(script, blocks)


def test_apply_search_replace_raises_on_ambiguous_match():
    script = "a = point(0, 0)\nb = point(0, 0)\n"
    blocks = [{"old_string": "point(0, 0)", "new_string": "point(1, 1)"}]
    with pytest.raises(SearchReplaceError, match="ambiguous"):
        apply_search_replace(script, blocks)


def test_apply_search_replace_tolerates_literal_newline_escapes():
    # A JSON-string-field transport artifact already confirmed for patch
    # mode this session: a model emits every line break in a string field
    # as a literal two-character "\n" instead of a real newline.
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    blocks = [{"old_string": "a = point(0, 0)\\nb = point(1, 0)", "new_string": "a = point(9, 9)\\nb = point(9, 9)"}]
    result = apply_search_replace(script, blocks)
    assert result == "a = point(9, 9)\nb = point(9, 9)\n"
