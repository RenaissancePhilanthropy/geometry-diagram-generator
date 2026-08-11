"""Tests for geometry_diagrams/pydsl/line_number.py."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.line_number import (
    LineNumberError,
    apply_line_number_ops,
    render_line_number_view,
)


def test_render_line_number_view_numbers_every_line():
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    view = render_line_number_view(script)
    lines = view.splitlines()
    assert lines == ["1| a = point(0, 0)", "2| b = point(1, 0)"]


def test_apply_line_number_ops_replace():
    script = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
    ops = [{"kind": "replace", "line": "2", "content": "b = point(2, 0)"}]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\nb = point(2, 0)\ndraw_points(a, b)\n"


def test_apply_line_number_ops_replace_with_matching_expected_content():
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    ops = [{
        "kind": "replace", "line": "2",
        "content": "b = point(2, 0)", "expected_content": "b = point(1, 0)",
    }]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\nb = point(2, 0)\n"


def test_apply_line_number_ops_raises_on_expected_content_mismatch():
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    ops = [{
        "kind": "replace", "line": "2",
        "content": "b = point(2, 0)", "expected_content": "b = point(9, 9)",
    }]
    with pytest.raises(LineNumberError, match="does not match expected content"):
        apply_line_number_ops(script, ops)


def test_apply_line_number_ops_insert_after():
    script = "a = point(0, 0)\ndraw_points(a)\n"
    ops = [{"kind": "insert", "after": "1", "content": 'a.label("A")'}]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\na.label(\"A\")\ndraw_points(a)\n"


def test_apply_line_number_ops_insert_at_start():
    script = "a = point(0, 0)\n"
    ops = [{"kind": "insert", "after": "start", "content": "# a comment"}]
    result = apply_line_number_ops(script, ops)
    assert result == "# a comment\na = point(0, 0)\n"


def test_apply_line_number_ops_delete():
    script = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
    ops = [{"kind": "delete", "line": "2"}]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\ndraw_points(a, b)\n"


def test_apply_line_number_ops_delete_with_matching_expected_content():
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    ops = [{"kind": "delete", "line": "2", "expected_content": "b = point(1, 0)"}]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\n"


def test_apply_line_number_ops_block_replace():
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\ndraw_points(a, b, c)\n"
    ops = [{"kind": "block_replace", "start_line": "2", "end_line": "3", "content": "b = point(5, 5)"}]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(0, 0)\nb = point(5, 5)\ndraw_points(a, b, c)\n"


def test_apply_line_number_ops_multiple_ops_in_one_batch():
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\ndraw_points(a, b, c)\n"
    ops = [
        {"kind": "replace", "line": "1", "content": "a = point(9, 9)"},
        {"kind": "delete", "line": "3"},
    ]
    result = apply_line_number_ops(script, ops)
    assert result == "a = point(9, 9)\nb = point(1, 0)\ndraw_points(a, b, c)\n"


def test_apply_line_number_ops_raises_on_out_of_range_line():
    script = "a = point(0, 0)\n"
    with pytest.raises(LineNumberError, match="invalid line reference"):
        apply_line_number_ops(script, [{"kind": "replace", "line": "5", "content": "x"}])


def test_apply_line_number_ops_raises_on_non_numeric_line():
    script = "a = point(0, 0)\n"
    with pytest.raises(LineNumberError, match="invalid line reference"):
        apply_line_number_ops(script, [{"kind": "replace", "line": "not-a-number", "content": "x"}])


def test_apply_line_number_ops_raises_on_zero_as_after_sentinel():
    # "0" is not accepted as a spelling of "insert at start" — "start" is
    # the only sentinel, per design (no dual spelling for the same case).
    script = "a = point(0, 0)\n"
    with pytest.raises(LineNumberError, match="invalid line reference"):
        apply_line_number_ops(script, [{"kind": "insert", "after": "0", "content": "# x"}])


def test_apply_line_number_ops_raises_on_reversed_block_replace_range():
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\n"
    with pytest.raises(LineNumberError, match="is before start_line"):
        apply_line_number_ops(
            script,
            [{"kind": "block_replace", "start_line": "3", "end_line": "2", "content": "x"}],
        )


def test_apply_line_number_ops_raises_on_overlapping_ops():
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    ops = [
        {"kind": "delete", "line": "1"},
        {"kind": "replace", "line": "1", "content": "a = point(9, 9)"},
    ]
    with pytest.raises(LineNumberError, match="overlap"):
        apply_line_number_ops(script, ops)


def test_apply_line_number_ops_raises_on_unknown_kind():
    script = "a = point(0, 0)\n"
    with pytest.raises(LineNumberError, match="unknown line_number op kind"):
        apply_line_number_ops(script, [{"kind": "swap", "line": "1"}])


def _five_line_script():
    return (
        "a = point(0, 0)\n"
        "b = point(1, 0)\n"
        "c = point(0, 1)\n"
        "d = point(1, 1)\n"
        "e = point(2, 2)\n"
    )


def test_apply_line_number_ops_raises_on_insert_then_delete_same_line():
    # insert-after-L5, then delete-L5, in that list order: the insert's
    # end_line is None, so without correctly advancing previous_end for
    # inserts too, its start_line would never block the delete from also
    # touching line 5 (see hashline.py's identical fix/test).
    script = _five_line_script()
    ops = [
        {"kind": "insert", "after": "5", "content": "# note"},
        {"kind": "delete", "line": "5"},
    ]
    with pytest.raises(LineNumberError, match="overlap"):
        apply_line_number_ops(script, ops)


def test_apply_line_number_ops_raises_on_delete_then_insert_same_line():
    script = _five_line_script()
    ops = [
        {"kind": "delete", "line": "5"},
        {"kind": "insert", "after": "5", "content": "# note"},
    ]
    with pytest.raises(LineNumberError, match="overlap"):
        apply_line_number_ops(script, ops)


def test_apply_line_number_ops_insert_and_delete_on_different_lines_do_not_overlap():
    script = _five_line_script()
    ops = [
        {"kind": "insert", "after": "2", "content": "# note"},
        {"kind": "delete", "line": "4"},
    ]
    result = apply_line_number_ops(script, ops)
    assert result == (
        "a = point(0, 0)\n"
        "b = point(1, 0)\n"
        "# note\n"
        "c = point(0, 1)\n"
        "e = point(2, 2)\n"
    )
