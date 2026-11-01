"""Shared mechanics for the line-anchored edit modes (hashline, line_number).

Both modes resolve each op to a ``(start_line, end_line_or_None, op)`` triple
against the ORIGINAL script, then check ordering and splice in one batch.
That second half is identical, so it lives here; each mode passes its own
error class so callers still catch the module's own error type."""
from __future__ import annotations


def split_script_lines(script: str) -> tuple[list[str], str, bool]:
    """Split on "\\n" only (never on form feeds or other str.splitlines
    separators). Returns (lines, eol, had_trailing_newline); eol is "\\r\\n"
    when the script contains CRLF, else "\\n", and a CRLF script's lines have
    their trailing "\\r" removed."""
    if not script:
        return [], "\n", False
    eol = "\r\n" if "\r\n" in script else "\n"
    lines = script.split("\n")
    had_trailing = lines[-1] == ""
    if had_trailing:
        lines.pop()
    if eol == "\r\n":
        lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    return lines, eol, had_trailing


def check_and_splice(
    lines: list[str],
    eol: str,
    had_trailing_newline: bool,
    resolved: "list[tuple[int, int | None, dict]]",
    error_cls: type[Exception],
    label: str,
) -> str:
    """Require non-overlapping, non-decreasing ranges, then apply every op in
    a single batch pass over the original `lines`. `label` names the mode in
    error messages (e.g. "hashline")."""
    ops_by_start = sorted(resolved, key=lambda r: r[0])
    previous_end = -1
    for start_line, end_line, _op in ops_by_start:
        if start_line <= previous_end:
            raise error_cls(
                f"{label} ops overlap or are out of order at line {start_line} "
                f"(previous op ended at line {previous_end}); "
                "ops must reference non-overlapping, non-decreasing line ranges"
            )
        # An insert's end_line is None (it doesn't consume an original
        # line, just anchors after one) — but its start_line still
        # occupies that anchor position and must block any other op
        # touching the same line, regardless of list order.
        previous_end = end_line if end_line is not None else start_line

    result_lines: list[str] = []
    cursor = 0  # 0-indexed position into `lines` already emitted
    for start_line, end_line, op in ops_by_start:
        kind = op["kind"]
        if kind == "insert":
            result_lines.extend(lines[cursor:start_line])
            result_lines.append(op["content"])
            cursor = start_line
        elif kind == "delete":
            result_lines.extend(lines[cursor : start_line - 1])
            cursor = start_line
        elif kind == "replace":
            result_lines.extend(lines[cursor : start_line - 1])
            result_lines.append(op["content"])
            cursor = start_line
        elif kind == "block_replace":
            result_lines.extend(lines[cursor : start_line - 1])
            result_lines.append(op["content"])
            cursor = end_line

    result_lines.extend(lines[cursor:])
    text = eol.join(result_lines)
    if had_trailing_newline or result_lines:
        text += eol
    return text


def require_op_fields(op: dict, fields: tuple[str, ...], error_cls: type[Exception], label: str) -> None:
    """Raise `error_cls` naming the first missing required field of `op`."""
    for name in fields:
        if name not in op or op[name] is None:
            raise error_cls(f"{label} op {op.get('kind')!r} is missing required field {name!r}")
