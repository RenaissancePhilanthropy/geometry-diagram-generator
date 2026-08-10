"""Applies a list of exact-match search/replace blocks to a pydsl script.

Sequential, all-or-nothing: blocks apply in order against a single
mutating buffer (an earlier block's new_string can create or destroy a
later block's match — Aider's real semantics, not simultaneous matching
against the original script), and each block's old_string must match
EXACTLY ONCE in the buffer at the time it's applied. Zero matches ("not
found") or 2+ matches ("ambiguous") both reject the entire turn — no
fuzzy matching, no partial application (see design doc, Component A)."""
from __future__ import annotations


class SearchReplaceError(ValueError):
    pass


def _normalize_transport_artifacts(text: str) -> str:
    """Undo a JSON-string-field transport artifact already confirmed for
    this project's other edit modes: literal "\\n" escaping when a model
    emits every line break in a string field as a literal two-character
    sequence instead of a real newline (mirrors python_full.py's
    _unescape_literal_newlines, applied here per-block instead of to a
    whole script)."""
    if "\n" not in text and "\\n" in text:
        return text.replace("\\n", "\n")
    return text


def apply_search_replace(script: str, blocks: list[dict]) -> str:
    """Apply `blocks` (each {"old_string": str, "new_string": str}) to
    `script` in order. Raises SearchReplaceError naming exactly what went
    wrong (not found / ambiguous) if any block doesn't match exactly once
    in the buffer at the time it's applied."""
    buffer = script
    for index, block in enumerate(blocks):
        old_string = _normalize_transport_artifacts(block["old_string"])
        new_string = _normalize_transport_artifacts(block["new_string"])
        count = buffer.count(old_string)
        if count == 0:
            raise SearchReplaceError(
                f"search_replace block {index}: old_string not found: {old_string!r}"
            )
        if count > 1:
            raise SearchReplaceError(
                f"search_replace block {index}: old_string is ambiguous "
                f"({count} matches): {old_string!r}"
            )
        buffer = buffer.replace(old_string, new_string, 1)
    return buffer
