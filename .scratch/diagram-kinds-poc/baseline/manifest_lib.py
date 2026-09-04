"""Manifest schema + read/write helpers for ticket 07's baseline run.

A manifest entry records one of the 30 taxonomy kinds' verdict:

- kind: the kind name (see kinds_prompts.KIND_NAMES).
- verdict: "pass" | "partial" | "fail".
- svg_path: path (relative to this baseline/ directory) to the rendered
  SVG, required for "pass"/"partial" and forbidden for "fail" (per ticket
  07: "fail" means no usable SVG was produced at all).
- notes: short free-text note, especially for partial/fail.

Kept separate from run_baseline.py (the generation driver) and from
kinds_prompts.py (the prompt data) so each piece is independently
testable, per the ticket's "Code Organization" note.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

VALID_VERDICTS = frozenset({"pass", "partial", "fail"})


@dataclass
class ManifestEntry:
    kind: str
    verdict: str
    svg_path: "str | None" = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(
                f"invalid verdict {self.verdict!r} for kind {self.kind!r}; "
                f"must be one of {sorted(VALID_VERDICTS)}"
            )
        if self.verdict in ("pass", "partial") and not self.svg_path and self.kind != "none":
            # "none" is the one deliberate exception (ticket 07, item 30): it
            # is not a rendering kind at all, so its trivial "pass" verdict
            # legitimately carries no SVG -- every other kind's pass/partial
            # must point at an actual rendered file.
            raise ValueError(
                f"kind {self.kind!r} has verdict {self.verdict!r} but no svg_path -- "
                "pass/partial require an actual rendered SVG (except the 'none' kind)"
            )
        if self.verdict == "fail" and self.svg_path:
            raise ValueError(
                f"kind {self.kind!r} has verdict 'fail' but svg_path={self.svg_path!r} "
                "is set -- a fail with a usable SVG should be 'partial' instead"
            )


def write_manifest(
    entries: "list[ManifestEntry]",
    path: "str | Path",
    expected_kinds: "list[str] | None" = None,
) -> None:
    """Write entries as a JSON array. Validates no duplicate kinds and,
    when `expected_kinds` is given, that entries cover exactly that set
    (no missing kind, no unexpected extra one) -- this is what catches an
    incomplete baseline run before it's ever committed."""
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


def read_manifest(path: "str | Path") -> "list[ManifestEntry]":
    data = json.loads(Path(path).read_text())
    return [ManifestEntry(**item) for item in data]
