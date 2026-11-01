"""Literal-first matching and field validation for search_replace."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.search_replace import SearchReplaceError, apply_search_replace


def test_literal_backslash_n_in_script_is_matchable():
    script = 'label(a, "a\\nb")\n'
    out = apply_search_replace(script, [{"old_string": '"a\\nb"', "new_string": '"c\\nd"'}])
    assert out == 'label(a, "c\\nd")\n'


def test_unescape_fallback_still_applies_to_both_strings():
    script = "a = 1\nb = 2\n"
    out = apply_search_replace(
        script, [{"old_string": "a = 1\\nb = 2", "new_string": "a = 3\\nb = 4"}]
    )
    assert out == "a = 3\nb = 4\n"


def test_new_string_not_unescaped_when_old_matched_literally():
    script = 'x = "p\\nq"\n'
    out = apply_search_replace(script, [{"old_string": "p\\nq", "new_string": "r\\ns"}])
    assert out == 'x = "r\\ns"\n'


@pytest.mark.parametrize("missing", ["old_string", "new_string"])
def test_missing_field_raises_module_error(missing):
    block = {"old_string": "a", "new_string": "b"}
    del block[missing]
    with pytest.raises(SearchReplaceError, match=missing):
        apply_search_replace("a\n", [block])
