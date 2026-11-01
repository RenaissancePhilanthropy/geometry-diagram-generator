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


def _needs_unescape(text: str) -> bool:
    return "\n" not in text and "\\n" in text


def _normalize_transport_artifacts(text: str) -> str:
    """Undo a JSON-string-field transport artifact already confirmed for
    this project's other edit modes: literal "\\n" escaping when a model
    emits every line break in a string field as a literal two-character
    sequence instead of a real newline (mirrors python_full.py's
    _unescape_literal_newlines, applied here per-block instead of to a
    whole script). Callers try the literal text first; this is the fallback."""
    if _needs_unescape(text):
        return text.replace("\\n", "\n")
    return text


def _require_block_fields(block: dict, index: int) -> None:
    for name in ("old_string", "new_string"):
        if not isinstance(block, dict) or not isinstance(block.get(name), str):
            raise SearchReplaceError(
                f"search_replace block {index} is missing required string field {name!r}"
            )


def apply_search_replace(script: str, blocks: list[dict]) -> str:
    """Apply `blocks` (each {"old_string": str, "new_string": str}) to
    `script` in order. Raises SearchReplaceError naming exactly what went
    wrong (not found / ambiguous / missing field) if any block doesn't
    match exactly once in the buffer at the time it's applied. The literal
    old_string is tried first; the unescaped variant (and an unescaped
    new_string) is used only when the literal has no match."""
    buffer = script
    for index, block in enumerate(blocks):
        _require_block_fields(block, index)
        old_string = block["old_string"]
        new_string = block["new_string"]
        count = buffer.count(old_string)
        if count == 0:
            unescaped = _normalize_transport_artifacts(old_string)
            if unescaped != old_string:
                old_string = unescaped
                new_string = _normalize_transport_artifacts(new_string)
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
