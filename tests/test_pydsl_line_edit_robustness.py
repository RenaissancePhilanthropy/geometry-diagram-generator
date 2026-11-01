"""Field validation and line-splitting robustness for hashline / line_number."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.hashline import HashlineError, apply_hashline_ops, render_hashline_view
from geometry_diagrams.pydsl.line_number import (
    LineNumberError,
    apply_line_number_ops,
    render_line_number_view,
)


@pytest.mark.parametrize(
    "op, field",
    [
        ({"kind": "insert", "after": "start"}, "content"),
        ({"kind": "replace", "line": "1"}, "content"),
        ({"kind": "block_replace", "start_line": "1", "end_line": "1"}, "content"),
        ({"kind": "delete"}, "line"),
    ],
)
def test_line_number_missing_field_raises_module_error(op, field):
    with pytest.raises(LineNumberError, match=field):
        apply_line_number_ops("a\nb\n", [op])


@pytest.mark.parametrize(
    "op, field",
    [
        ({"kind": "insert", "after": "start"}, "content"),
        ({"kind": "insert", "content": "x"}, "after"),
        ({"kind": "delete"}, "tag"),
        ({"kind": "replace", "tag": "1:00"}, "content"),
        ({"kind": "block_replace", "start_tag": "1:00", "content": "x"}, "end_tag"),
    ],
)
def test_hashline_missing_field_raises_module_error(op, field):
    with pytest.raises(HashlineError, match=field):
        apply_hashline_ops("a\nb\n", [op])


def test_line_number_splits_on_newline_only():
    script = "a\x0cb\nc\n"
    assert render_line_number_view(script).startswith("1| a\x0cb")
    out = apply_line_number_ops(script, [{"kind": "replace", "line": "2", "content": "z"}])
    assert out == "a\x0cb\nz\n"


def test_line_number_preserves_crlf_and_trailing_newline_rules():
    out = apply_line_number_ops("a\r\nb\r\n", [{"kind": "replace", "line": "2", "content": "z"}])
    assert out == "a\r\nz\r\n"
    assert render_line_number_view("a\r\nb\r\n") == "1| a\n2| b"
    out = apply_line_number_ops("a\nb", [{"kind": "replace", "line": "1", "content": "z"}])
    assert out == "z\nb\n"
    assert apply_line_number_ops("a", [{"kind": "delete", "line": "1"}]) == ""


def test_hashline_splits_on_newline_only_and_preserves_eol():
    script = "a\x0cb\r\nc\r\n"
    view = render_hashline_view(script)
    assert len(view.split("\n")) == 2
    tag = view.split("|", 1)[0]
    out = apply_hashline_ops(script, [{"kind": "replace", "tag": tag, "content": "z"}])
    assert out == "z\r\nc\r\n"
