"""Plain line-number-anchored editing for pydsl scripts ("line_number").

Same op model and atomicity discipline as hashline.py (see that module's
docstring), but with no hash of any kind — a line is referenced by its
plain 1-indexed position, read directly off an annotated view
(render_line_number_view). All line-reference fields (line, after,
start_line, end_line) are strings, mirroring hashline's string tags, so
a stringified int and the "start" sentinel share one field type with no
int/string union to coerce.

Content echo: delete/replace ops may carry an optional expected_content
field — an exact-match check against the real line's current content,
rejected loudly on mismatch. It's the closest analog to hashline's
stale-tag check available without a hash. It's optional: omitting it
means no check is performed for that op (see design doc, Component A,
"Isolation risk" — this is intentional, to let eval results be
stratified by whether the model used it, not a gap to close)."""
from __future__ import annotations


class LineNumberError(ValueError):
    pass


def render_line_number_view(script: str) -> str:
    """The annotated view shown to the model: one line per source line,
    prefixed with its 1-indexed line number, e.g. "3| c = point(0, 1)"."""
    lines = script.splitlines()
    return "\n".join(f"{i}| {line}" for i, line in enumerate(lines, start=1))


def _parse_line_ref(value: "str | None", field_name: str, max_line: int) -> int:
    """Parse a 1-indexed line-reference string, bounds-checked against
    the original script's line count. Raises LineNumberError naming the
    field and value on failure — never returns an out-of-range int."""
    if value is None:
        raise LineNumberError(f"line_number op is missing required field {field_name!r}")
    try:
        line_number = int(value)
    except ValueError:
        raise LineNumberError(
            f"line_number op has an invalid line reference in {field_name!r}: {value!r}"
        )
    if not (1 <= line_number <= max_line):
        raise LineNumberError(
            f"line_number op has an invalid line reference in {field_name!r}: "
            f"{value!r} (script has {max_line} lines)"
        )
    return line_number


def _check_expected_content(lines: list[str], line_number: int, expected_content: "str | None") -> None:
    if expected_content is None:
        return
    actual = lines[line_number - 1]
    if actual != expected_content:
        raise LineNumberError(
            f"line {line_number} does not match expected content: "
            f"expected {expected_content!r}, got {actual!r}"
        )


def apply_line_number_ops(script: str, ops: list[dict]) -> str:
    """Apply `ops` (each a flat dict; kind is one of insert/delete/replace/
    block_replace) to `script`. Validates every op's line reference(s)
    against the ORIGINAL script's line count (and, for delete/replace,
    an optional expected_content check) up front, requires
    non-overlapping, non-decreasing line ranges, then applies as a single
    batch. Raises LineNumberError naming exactly what went wrong if any
    check fails — the whole turn fails, never a partial application."""
    lines = script.splitlines()
    max_line = len(lines)

    # Resolve every op to (start_line, end_line_or_None) against the
    # ORIGINAL script, before anything is applied.
    resolved: list[tuple[int, "int | None", dict]] = []
    for op in ops:
        kind = op.get("kind")
        if kind == "insert":
            after = op.get("after")
            start_line = 0 if after == "start" else _parse_line_ref(after, "after", max_line)
            resolved.append((start_line, None, op))
        elif kind == "delete":
            line_number = _parse_line_ref(op.get("line"), "line", max_line)
            _check_expected_content(lines, line_number, op.get("expected_content"))
            resolved.append((line_number, line_number, op))
        elif kind == "replace":
            line_number = _parse_line_ref(op.get("line"), "line", max_line)
            _check_expected_content(lines, line_number, op.get("expected_content"))
            resolved.append((line_number, line_number, op))
        elif kind == "block_replace":
            start_line = _parse_line_ref(op.get("start_line"), "start_line", max_line)
            end_line = _parse_line_ref(op.get("end_line"), "end_line", max_line)
            if end_line < start_line:
                raise LineNumberError(
                    f"block_replace end_line {end_line} is before start_line {start_line}"
                )
            resolved.append((start_line, end_line, op))
        else:
            raise LineNumberError(f"unknown line_number op kind: {kind!r}")

    # Non-decreasing, non-overlapping order (mirrors hashline.py's check —
    # same principle, same rationale, including the insert-anchor fix:
    # an insert's end_line is None, but its start_line still occupies
    # that anchor position and must block any other op touching the same
    # line, regardless of list order).
    ops_by_start = sorted(resolved, key=lambda r: r[0])
    previous_end = -1
    for start_line, end_line, _op in ops_by_start:
        if start_line <= previous_end:
            raise LineNumberError(
                f"line_number ops overlap or are out of order at line {start_line} "
                f"(previous op ended at line {previous_end}); "
                "ops must reference non-overlapping, non-decreasing line ranges"
            )
        previous_end = end_line if end_line is not None else start_line

    # Single batch pass over the original lines, splicing in each op's
    # effect at its resolved (pre-turn) position.
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
    return "\n".join(result_lines) + "\n"
