"""Applies a unified-diff-shaped patch to a pydsl script.

Deliberately a narrow subset of unified diff: hunk headers plus ' '/'-'/'+'
lines, context lines must match exactly. No fuzzy offset search — a
context mismatch is a hard error, not a best-effort guess, because
silently applying a patch to the wrong lines would corrupt a script in a
way that's hard to detect downstream (see design doc, Component 3, on why
patch mode is opt-in rather than default: weak-model diff-format
compliance is exactly the failure class this project already fought once
in the script extractor)."""
from __future__ import annotations

import re

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_script_patch(previous_script: str, patch_text: str) -> str:
    """Apply a unified-diff `patch_text` to `previous_script`, returning the
    patched script. Raises ValueError describing exactly what mismatched if
    the patch's context/removal lines don't match `previous_script`."""
    old_lines = previous_script.splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=True)
    # An LLM's patch is normally carried as a JSON string field, so its final
    # line routinely lacks a trailing "\n" as a pure transport artifact (the
    # value just ends there) — not a real diff signal. Left alone, that
    # drops a "\n" splitlines(keepends=True) would otherwise have kept,
    # causing a spurious mismatch against the real script's corresponding
    # line (which does have one), or — for an inserted line — silently
    # merging it into whatever line follows it in the output.
    if patch_lines and not patch_lines[-1].endswith("\n"):
        patch_lines[-1] += "\n"

    result_lines: list[str] = []
    old_index = 0
    applied_any_hunk = False
    i = 0
    while i < len(patch_lines):
        header = _HUNK_HEADER_RE.match(patch_lines[i])
        if not header:
            i += 1
            continue
        applied_any_hunk = True
        old_start = int(header.group(1)) - 1
        if old_start < 0:
            raise ValueError(
                f"invalid hunk header line number: {header.group(0)!r}"
            )
        if old_start < old_index:
            raise ValueError(
                f"hunk header at old-file line {old_start + 1} points backward "
                f"before the previous hunk's end (line {old_index + 1}); "
                "hunks must be in non-decreasing order"
            )
        result_lines.extend(old_lines[old_index:old_start])
        old_index = old_start
        i += 1
        while i < len(patch_lines) and not _HUNK_HEADER_RE.match(patch_lines[i]):
            hline = patch_lines[i]
            tag, content = hline[:1], hline[1:]
            if tag == "-" or tag == " ":
                if old_index >= len(old_lines) or old_lines[old_index] != content:
                    actual = old_lines[old_index] if old_index < len(old_lines) else "<eof>"
                    raise ValueError(
                        f"patch context mismatch at line {old_index + 1}: "
                        f"expected {actual!r}, patch has {content!r}"
                    )
                if tag == " ":
                    result_lines.append(content)
                old_index += 1
            elif tag == "+":
                result_lines.append(content)
            i += 1

    if not applied_any_hunk:
        raise ValueError("patch contains no recognizable @@ hunks")

    result_lines.extend(old_lines[old_index:])
    return "".join(result_lines)
