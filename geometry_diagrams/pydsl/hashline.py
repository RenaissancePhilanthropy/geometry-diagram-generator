"""Content-hash line-anchored editing for pydsl scripts ("hashline").

Each line of a script gets tagged {line_number}:{hash}, where hash is a
short prefix of a fast content hash (see _compute_hash — the algorithm is
swappable, see design doc Component D). The model references lines by tag
instead of raw position; a stale tag (the line's current hash doesn't
match) is rejected, never silently misapplied.

Atomicity: ops are validated against the ORIGINAL (pre-turn) script's tag
map ALL AT ONCE, then applied as a single batch pass — never one at a
time against a mutating buffer. Applying sequentially would make later
ops' tags stale the moment an earlier op shifts line numbers, even when
the model copied them perfectly (see design doc, Component B) — the same
failure class that sank patch mode's unified diffs, reproduced inside the
mechanism meant to avoid it.

Deprecated as of 2026-08-12: a cross-model eval comparison found
search_replace (geometry_diagrams/pydsl/search_replace.py) wins or ties
for best on every model tested. hashline's compound {line_number}:{hash}
tag turned out to be a real reliability liability — direct data analysis
found most of its failures were models dropping the line-number prefix
and returning only the hash, not genuine staleness detection. Still fully
functional and available for comparison via evals/run_edit_chains.py, but
no longer recommended for new usage."""
from __future__ import annotations

import hashlib

_TAG_HEX_CHARS = 2  # visible hash-tag length, matching the reference hashline tool


class HashlineError(ValueError):
    pass


def _compute_hash(line: str, hash_algorithm: str) -> str:
    if hash_algorithm == "blake2s":
        return hashlib.blake2s(line.encode("utf-8"), digest_size=1).hexdigest()
    if hash_algorithm == "xxhash":
        import xxhash
        return xxhash.xxh32(line.encode("utf-8")).hexdigest()[:_TAG_HEX_CHARS]
    raise HashlineError(f"unknown hash_algorithm: {hash_algorithm!r}")


def _tag_map(script: str, hash_algorithm: str) -> dict[str, int]:
    """tag -> 1-indexed line number, computed against `script` as given."""
    lines = script.splitlines()
    return {
        f"{i}:{_compute_hash(line, hash_algorithm)}": i
        for i, line in enumerate(lines, start=1)
    }


def render_hashline_view(script: str, hash_algorithm: str = "blake2s") -> str:
    """The annotated view shown to the model: one line per source line,
    prefixed with its tag, e.g. "3:a1| c = point(0, 1)"."""
    lines = script.splitlines()
    return "\n".join(
        f"{i}:{_compute_hash(line, hash_algorithm)}| {line}"
        for i, line in enumerate(lines, start=1)
    )


def apply_hashline_ops(script: str, ops: list[dict], hash_algorithm: str = "blake2s") -> str:
    """Apply `ops` (each a flat dict; kind is one of insert/delete/replace/
    block_replace — see design doc Component B) to `script`. Validates
    every op's tag(s) against the ORIGINAL script's tag map up front,
    requires non-overlapping, non-decreasing line ranges, then applies as
    a single batch. Raises HashlineError naming exactly what went wrong
    (stale tag / invalid order / unknown kind) if any check fails — the
    whole turn fails, never a partial application."""
    lines = script.splitlines()
    tag_to_line = _tag_map(script, hash_algorithm)

    def resolve(tag: str) -> int:
        line_number = tag_to_line.get(tag)
        if line_number is None:
            raise HashlineError(f"hashline op references a stale or unknown tag: {tag!r}")
        return line_number

    # Resolve every op to (start_line, end_line_or_None) against the
    # ORIGINAL script, before anything is applied.
    resolved: list[tuple[int, "int | None", dict]] = []
    for op in ops:
        kind = op.get("kind")
        if kind == "insert":
            after = op["after"]
            start_line = 0 if after == "start" else resolve(after)
            resolved.append((start_line, None, op))
        elif kind == "delete":
            line_number = resolve(op["tag"])
            resolved.append((line_number, line_number, op))
        elif kind == "replace":
            line_number = resolve(op["tag"])
            resolved.append((line_number, line_number, op))
        elif kind == "block_replace":
            start_line = resolve(op["start_tag"])
            end_line = resolve(op["end_tag"])
            if end_line < start_line:
                raise HashlineError(
                    f"block_replace end_tag {op['end_tag']!r} (line {end_line}) is "
                    f"before start_tag {op['start_tag']!r} (line {start_line})"
                )
            resolved.append((start_line, end_line, op))
        else:
            raise HashlineError(f"unknown hashline op kind: {kind!r}")

    # Non-decreasing, non-overlapping order (mirrors apply_script_patch's
    # backward-hunk check — same principle, same rationale).
    ops_by_start = sorted(resolved, key=lambda r: r[0])
    previous_end = -1
    for start_line, end_line, _op in ops_by_start:
        if start_line <= previous_end:
            raise HashlineError(
                f"hashline ops overlap or are out of order at line {start_line} "
                f"(previous op ended at line {previous_end}); "
                "ops must reference non-overlapping, non-decreasing line ranges"
            )
        # An insert's end_line is None (it doesn't consume an original
        # line, just anchors after one) — but its start_line still
        # occupies that anchor position and must block any other op
        # (insert/delete/replace/block_replace) touching the same line,
        # regardless of the ops' order in the input list. Without this,
        # Python's stable sort would make the outcome depend on list
        # order for ties at the same line.
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
