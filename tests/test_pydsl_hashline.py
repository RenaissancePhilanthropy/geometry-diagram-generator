"""Tests for geometry_diagrams/pydsl/hashline.py."""
from __future__ import annotations

import pytest

from geometry_diagrams.pydsl.hashline import (
    HashlineError,
    apply_hashline_ops,
    render_hashline_view,
)


@pytest.mark.parametrize("hash_algorithm", ["blake2s", "xxhash"])
def test_render_hashline_view_tags_every_line(hash_algorithm):
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    view = render_hashline_view(script, hash_algorithm)
    lines = view.splitlines()
    assert len(lines) == 2
    assert lines[0].split("|", 1)[1] == " a = point(0, 0)"
    assert lines[1].split("|", 1)[1] == " b = point(1, 0)"
    tag0 = lines[0].split("|", 1)[0]
    assert tag0.startswith("1:")
    tag1 = lines[1].split("|", 1)[0]
    assert tag1.startswith("2:")


@pytest.mark.parametrize("hash_algorithm", ["blake2s", "xxhash"])
def test_apply_hashline_ops_replace(hash_algorithm):
    script = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
    view = render_hashline_view(script, hash_algorithm)
    tag_for_line_2 = view.splitlines()[1].split("|", 1)[0]
    ops = [{"kind": "replace", "tag": tag_for_line_2, "content": "b = point(2, 0)"}]
    result = apply_hashline_ops(script, ops, hash_algorithm)
    assert result == "a = point(0, 0)\nb = point(2, 0)\ndraw_points(a, b)\n"


def test_apply_hashline_ops_insert_after():
    script = "a = point(0, 0)\ndraw_points(a)\n"
    view = render_hashline_view(script)
    tag_for_line_1 = view.splitlines()[0].split("|", 1)[0]
    ops = [{"kind": "insert", "after": tag_for_line_1, "content": 'a.label("A")'}]
    result = apply_hashline_ops(script, ops)
    assert result == "a = point(0, 0)\na.label(\"A\")\ndraw_points(a)\n"


def test_apply_hashline_ops_insert_at_start():
    script = "a = point(0, 0)\n"
    ops = [{"kind": "insert", "after": "start", "content": "# a comment"}]
    result = apply_hashline_ops(script, ops)
    assert result == "# a comment\na = point(0, 0)\n"


def test_apply_hashline_ops_delete():
    script = "a = point(0, 0)\nb = point(1, 0)\ndraw_points(a, b)\n"
    view = render_hashline_view(script)
    tag_for_line_2 = view.splitlines()[1].split("|", 1)[0]
    ops = [{"kind": "delete", "tag": tag_for_line_2}]
    result = apply_hashline_ops(script, ops)
    assert result == "a = point(0, 0)\ndraw_points(a, b)\n"


def test_apply_hashline_ops_block_replace():
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\ndraw_points(a, b, c)\n"
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [{"kind": "block_replace", "start_tag": tags[1], "end_tag": tags[2], "content": "b = point(5, 5)"}]
    result = apply_hashline_ops(script, ops)
    assert result == "a = point(0, 0)\nb = point(5, 5)\ndraw_points(a, b, c)\n"


def test_apply_hashline_ops_multiple_ops_in_one_batch():
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\ndraw_points(a, b, c)\n"
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [
        {"kind": "replace", "tag": tags[0], "content": "a = point(9, 9)"},
        {"kind": "delete", "tag": tags[2]},
    ]
    result = apply_hashline_ops(script, ops)
    assert result == "a = point(9, 9)\nb = point(1, 0)\ndraw_points(a, b, c)\n"


def test_apply_hashline_ops_raises_on_stale_tag():
    script = "a = point(0, 0)\n"
    with pytest.raises(HashlineError, match="stale or unknown tag"):
        apply_hashline_ops(script, [{"kind": "replace", "tag": "1:zz", "content": "x"}])


def test_apply_hashline_ops_raises_on_overlapping_ops():
    # Both ops resolve to line 1 — a delete and a replace of the same line
    # is a genuine overlap, not something to guess about.
    script = "a = point(0, 0)\nb = point(1, 0)\n"
    view = render_hashline_view(script)
    tag_for_line_1 = view.splitlines()[0].split("|", 1)[0]
    ops = [
        {"kind": "delete", "tag": tag_for_line_1},
        {"kind": "replace", "tag": tag_for_line_1, "content": "a = point(9, 9)"},
    ]
    with pytest.raises(HashlineError, match="overlap"):
        apply_hashline_ops(script, ops)


def test_apply_hashline_ops_raises_on_unknown_kind():
    script = "a = point(0, 0)\n"
    with pytest.raises(HashlineError, match="unknown hashline op kind"):
        apply_hashline_ops(script, [{"kind": "swap", "tag": "1:zz"}])


def _five_line_script():
    return (
        "a = point(0, 0)\n"
        "b = point(1, 0)\n"
        "c = point(0, 1)\n"
        "d = point(1, 1)\n"
        "e = point(2, 2)\n"
    )


def test_apply_hashline_ops_raises_on_insert_then_delete_same_line():
    # insert-after-L5, then delete-L5, in that list order: the insert's
    # end_line is None, so without the fix its start_line would never
    # block the delete from also touching line 5 — silently dropping the
    # delete instead of raising.
    script = _five_line_script()
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [
        {"kind": "insert", "after": tags[4], "content": "# note"},
        {"kind": "delete", "tag": tags[4]},
    ]
    with pytest.raises(HashlineError, match="overlap"):
        apply_hashline_ops(script, ops)


def test_apply_hashline_ops_raises_on_delete_then_insert_same_line():
    # Same pair, reverse list order — must also raise (this direction
    # already worked before the fix; confirming no regression).
    script = _five_line_script()
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [
        {"kind": "delete", "tag": tags[4]},
        {"kind": "insert", "after": tags[4], "content": "# note"},
    ]
    with pytest.raises(HashlineError, match="overlap"):
        apply_hashline_ops(script, ops)


def test_apply_hashline_ops_raises_on_insert_then_block_replace_overlap():
    # insert-after-L2, then block_replace(L2..L3): the insert's anchor
    # sits inside the block_replace's range, so this must raise rather
    # than silently leaking the original line 2 through untouched.
    script = "a = point(0, 0)\nb = point(1, 0)\nc = point(0, 1)\ndraw_points(a, b, c)\n"
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [
        {"kind": "insert", "after": tags[1], "content": "# note"},
        {"kind": "block_replace", "start_tag": tags[1], "end_tag": tags[2], "content": "b = point(5, 5)"},
    ]
    with pytest.raises(HashlineError, match="overlap"):
        apply_hashline_ops(script, ops)


def test_apply_hashline_ops_insert_and_delete_on_different_lines_do_not_overlap():
    # A genuinely non-overlapping pair (insert after L2, delete L4) must
    # still succeed — the fix must not make insert ops overly strict.
    script = _five_line_script()
    view = render_hashline_view(script)
    tags = [line.split("|", 1)[0] for line in view.splitlines()]
    ops = [
        {"kind": "insert", "after": tags[1], "content": "# note"},
        {"kind": "delete", "tag": tags[3]},
    ]
    result = apply_hashline_ops(script, ops)
    assert result == (
        "a = point(0, 0)\n"
        "b = point(1, 0)\n"
        "# note\n"
        "c = point(0, 1)\n"
        "e = point(2, 2)\n"
    )
