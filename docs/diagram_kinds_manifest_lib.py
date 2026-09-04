"""Schema + read/write helpers for the diagram-kinds-poc gallery's final
30-kind manifest (docs/examples/diagram_kinds/manifest.json).

Each entry records, for one of the 30 taxonomy kinds, where its gallery
SVG comes from and whether it's presentable:

- kind: the kind name (see .scratch/diagram-kinds-poc/baseline/kinds_prompts.KIND_NAMES,
  while that PoC working area still exists).
- svg_path: path (relative to docs/examples/diagram_kinds/) to the SVG to
  show in the gallery, or None. Required for status="ok" except the "none"
  kind (which is not a rendering kind at all). Optional for
  status="known-gap" (a known-gap kind has no presentable SVG by
  definition, though a best-effort attempt may still be referenced
  elsewhere for evidence).
- source: "baseline-reuse" (a kind whose original baseline SVG, verdict
  "pass", was reused as-is) or "fresh-generation" (a genuine new
  PythonFullStrategy.run() was used for it).
- status: "ok" (a presentable SVG exists) or "known-gap" (no clean render
  was produced after reasonable iteration -- must carry a real note on
  what was tried).
- notes: short free-text note. Required (non-empty) for "known-gap".

Kept separate from assemble_diagram_kinds_manifest.py (the assembly logic)
so the schema is independently testable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

VALID_SOURCES = frozenset({"baseline-reuse", "fresh-generation"})
VALID_STATUSES = frozenset({"ok", "known-gap"})


@dataclass
class FinalManifestEntry:
    kind: str
    svg_path: "str | None"
    source: str
    status: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"invalid source {self.source!r} for kind {self.kind!r}; "
                f"must be one of {sorted(VALID_SOURCES)}"
            )
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {self.status!r} for kind {self.kind!r}; "
                f"must be one of {sorted(VALID_STATUSES)}"
            )
        if self.status == "ok" and not self.svg_path and self.kind != "none":
            # "none" is the one deliberate exception (not a rendering kind
            # at all) -- same as the baseline manifest's schema.
            raise ValueError(
                f"kind {self.kind!r} has status 'ok' but no svg_path -- "
                "an 'ok' entry requires an actual rendered SVG (except the "
                "'none' kind)"
            )
        if self.status == "known-gap" and not self.notes.strip():
            raise ValueError(
                f"kind {self.kind!r} has status 'known-gap' but no notes -- "
                "a known gap must record what was tried and why it didn't "
                "converge (the Honesty requirement)"
            )


def write_manifest(
    entries: "list[FinalManifestEntry]",
    path: "str | Path",
    expected_kinds: "list[str] | None" = None,
) -> None:
    """Write entries as a JSON array. Validates no duplicate kinds and,
    when `expected_kinds` is given, that entries cover exactly that set."""
    kinds = [e.kind for e in entries]
    if len(kinds) != len(set(kinds)):
        seen: set[str] = set()
        dupes = {k for k in kinds if k in seen or seen.add(k)}
        raise ValueError(f"duplicate kind(s) in manifest entries: {sorted(dupes)}")
    if expected_kinds is not None:
        actual = set(kinds)
        expected = set(expected_kinds)
        if actual != expected:
            missing = expected - actual
            extra = actual - expected
            raise ValueError(
                f"manifest kinds don't match expected set; missing={sorted(missing)} "
                f"extra={sorted(extra)}"
            )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(e) for e in entries], indent=2) + "\n")


def read_manifest(path: "str | Path") -> "list[FinalManifestEntry]":
    data = json.loads(Path(path).read_text())
    return [FinalManifestEntry(**item) for item in data]
