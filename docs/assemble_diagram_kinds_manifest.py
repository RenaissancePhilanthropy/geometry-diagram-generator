"""Assemble the diagram-kinds gallery's final 30-kind manifest.

Combines:
- .scratch/diagram-kinds-poc/baseline/manifest.json: the kinds with
  baseline verdict "pass" (including "none", which needs no SVG) are
  reused as-is -- source="baseline-reuse", status="ok".
- FRESH_CHOICES below (hand-reviewed, after actually looking at every
  rendered attempt's SVG): the kinds that needed a genuine fresh
  PythonFullStrategy.run() -- source="fresh-generation", status="ok"
  (pointing at the winning attempt) or "known-gap" (no clean render after
  reasonable iteration).

NOTE: this script's baseline input lives under .scratch/diagram-kinds-poc/,
diagram-kinds-poc's disposable working area. This script and its output
(docs/examples/diagram_kinds/manifest.json + svgs/) were relocated out of
.scratch to survive that area being deleted, but re-running this assembly
script from scratch still depends on .scratch/diagram-kinds-poc/baseline/
existing -- it was intentionally left in place at the time of this move
(a separate decision for whoever eventually cleans up .scratch). If that
directory is gone, this script can no longer be re-run as-is; the already
-assembled manifest.json + svgs/ remain valid as a frozen snapshot either
way.

This module's `build_final_entries` is the pure, unit-testable assembly
logic. `main()` additionally copies every referenced SVG into ./svgs/ (or
the attempts/ output of gen_diagram_kinds_examples.py) so the final
manifest is self-contained, and writes the final manifest.json.

Usage: .venv/bin/python docs/assemble_diagram_kinds_manifest.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BASELINE_DIR = REPO_ROOT / ".scratch" / "diagram-kinds-poc" / "baseline"
OUT_DIR = SCRIPT_DIR / "examples" / "diagram_kinds"

for p in (str(SCRIPT_DIR), str(BASELINE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from kinds_prompts import KIND_NAMES  # noqa: E402
from diagram_kinds_manifest_lib import FinalManifestEntry, write_manifest  # noqa: E402

BASELINE_MANIFEST_PATH = BASELINE_DIR / "manifest.json"
FINAL_MANIFEST_PATH = OUT_DIR / "manifest.json"
FINAL_SVG_DIR = OUT_DIR / "svgs"
FINAL_SCRIPTS_DIR = OUT_DIR / "scripts"

# Hand-reviewed outcome for each of the 5 kinds that needed a genuine fresh
# PythonFullStrategy.run() (see gen_diagram_kinds_examples.py +
# diagram_kinds_prompts.py). Filled in after visually reviewing every
# attempt's rendered SVG (headless-Chrome screenshot) -- not a hand-authored
# fix, a *choice* of which real strategy-run attempt to keep.
#
# kind -> {
#   "status": "ok" | "known-gap",
#   "attempt_svg": path relative to OUT_DIR (attempts/<kind>_attempt<N>.svg),
#       required for "ok", omitted for "known-gap" (no presentable output),
#   "attempt_script": path relative to OUT_DIR
#       (attempt_scripts/<kind>_attempt<N>.py) to the exact generated pydsl
#       script text, when captured -- optional; omitted for the original 5
#       kinds below (area_model .. shape_comparison), whose generation
#       predates script capture being added (round-2 gallery review) and
#       whose attempts/ files were not kept around afterward,
#   "notes": str,
# }
#
# NOTE (round-2 gallery review): work_table and l_prism were originally
# "baseline-reuse" kinds (see .scratch/diagram-kinds-poc/baseline/
# manifest.json, verdict "pass") whose baseline SVGs were later found by a
# human reviewer to have real construction bugs the original baseline
# review missed (non-uniform row height; a depth edge braced twice in
# reversed direction). They are added here as "fresh-generation" overrides
# of that stale "pass" verdict -- see their notes below for the exact
# coordinate evidence of the fix. prism_net's softer "crowded labels" issue
# was also investigated (2 fresh PythonFullStrategy.run() attempts, no
# cookbook) but deliberately NOT added here: attempt 0 introduced a new
# defect (a title label clipped outside the canvas viewBox) and attempt 1
# regressed further (dropped one of the 6 net faces entirely) -- neither
# was an improvement on the baseline's "crowded but legible" SVG, so per
# the "don't force a worse result" guidance the baseline SVG was kept as-is
# and only its notes (in the final manifest.json, not this historical
# baseline snapshot) were updated to record what was tried and why it
# wasn't adopted.
#
# NOTE (round-3 gallery review): balance_scale was also originally a
# "baseline-reuse" kind whose baseline SVG was later found by a human
# reviewer to have a real construction bug the original baseline review
# missed: both pans' contents (blocks / coins) were drawn entirely below
# (larger y than) their pan platform's surface -- i.e. hanging off the
# bottom of the pan rather than resting inside/on top of it. It is added
# here as a "fresh-generation" override of that stale "pass" verdict; see
# its notes below for the exact coordinate evidence of the fix.
FRESH_CHOICES: "dict[str, dict]" = {
    "area_model": {
        "status": "ok",
        "attempt_svg": "attempts/area_model_attempt0.svg",
        "notes": (
            "Fresh PythonFullStrategy.run() with experimental_diagram_cookbook=True "
            "(1 attempt). All 4 box-method cells (200, 30, 100, 15) render with "
            "distinct, non-overlapping labels and both factor braces (23 = 20+3, "
            "15 = 10+5) are correct -- baseline's defect (2 empty right-column "
            "cells, overlapping left-column text) is gone."
        ),
    },
    "attribute_chart": {
        "status": "ok",
        "attempt_svg": "attempts/attribute_chart_attempt0.svg",
        "notes": (
            "Fresh PythonFullStrategy.run() with experimental_diagram_cookbook=True "
            "(1 attempt). Single bordered table, one header row (Square/Rectangle/"
            "Triangle) and one header column (the three attributes), each check/X "
            "mark rendered exactly once -- baseline's defect (duplicated headers, "
            "2 stray decorative bands) is gone."
        ),
    },
    "coordinate_plane": {
        "status": "ok",
        "attempt_svg": "attempts/coordinate_plane_attempt0.svg",
        "notes": (
            "Fresh PythonFullStrategy.run() (no cookbook; 1 attempt) with a prompt "
            "explicitly asking for the 'Translation: (x-2, y-3)' caption to be "
            "placed with safe left margin, not flush against the canvas edge. "
            "The caption now renders fully inside the canvas, bottom-left, fully "
            "legible -- baseline's clipped-caption defect is gone."
        ),
    },
    "scatter_plot": {
        "status": "ok",
        "attempt_svg": "attempts/scatter_plot_attempt3.svg",
        "attempt_script": "attempt_scripts/scatter_plot_attempt3.py",
        "notes": (
            "Round-4 re-attempt (ticket 06, pydsl-authoring-quality) with "
            "experimental_diagram_cookbook=True, using the new chart_axes() "
            "cookbook helper (ticket 03). Prior 3 attempts (no cookbook; "
            "attempts 0-2, see diagram_kinds_prompts.py) all rendered as a "
            "tall, narrow canvas (viewBox widths ~80-92 vs height 500) with "
            "clipped/overlapping text -- root cause was to_svg.py's single "
            "shared x/y scale factor forcing a bad aspect ratio for this "
            "dataset's very different axis ranges (0-8 hours vs 0-100 "
            "score). This attempt's prompt explicitly instructed the script "
            "to call chart_axes(x_data_range=(0, 8), y_data_range=(0, 100), "
            "geom_size=10.0) and route every point, axis tick, and "
            "best-fit-line endpoint through axes.map() for PLACEMENT only, "
            "while labeling every tick/point with its true, unmapped data "
            "value. Converged on the first try (1 fresh "
            "PythonFullStrategy.run() attempt this round): the rendered SVG "
            "has a square viewBox (0 0 500 500, not a tall strip), all 18 "
            "text labels' data-bbox attributes lie fully inside "
            "[0,500]x[0,500] (checked programmatically, none clipped), no "
            "two label bboxes overlap (checked pairwise), tick labels read "
            "the true axis values (0/2/4/6/8 for Hours, 0/25/50/75/100 for "
            "Score), and all 6 point labels read the true, unmapped scores "
            "(55, 60, 68, 74, 85, 90) even though their geometry positions "
            "are the compressed chart_axes() coordinates -- confirming "
            "labels never leaked the mapped coordinate. A dashed red "
            "best-fit line and black x/y axes with tick marks are also "
            "present."
        ),
    },
    "shape_comparison": {
        "status": "ok",
        "attempt_svg": "attempts/shape_comparison_attempt2.svg",
        "notes": (
            "3 fresh PythonFullStrategy.run() attempts (no cookbook). Attempts 0-1 "
            "both wrapped the closing summary onto two lines whose vertical "
            "spacing was too small, so the lines rendered overlapping each other "
            "(baseline's exact defect, reproduced both times despite explicit "
            "margin/spacing instructions). Attempt 2's prompt instead forced a "
            "single short summary line ('Rectangle has more area; both have "
            "equal perimeter') -- this rendered cleanly with no overlap and no "
            "clipping, so it was kept as the final SVG."
        ),
    },
    "work_table": {
        "status": "ok",
        "attempt_svg": "attempts/work_table_attempt0.svg",
        "attempt_script": "attempt_scripts/work_table_attempt0.py",
        "notes": (
            "Fresh PythonFullStrategy.run() with experimental_diagram_cookbook=True "
            "(1 attempt), prompted to require every row -- including the header "
            "row -- to have exactly the same height. The generated script uses "
            "table_grid() with a uniform row_heights list; the rendered SVG's 6 "
            "row-divider lines land at y = 48.75, 106.25, 163.75, 221.25, 278.75, "
            "336.25 -- every gap exactly 57.5 -- confirming baseline's defect (one "
            "row 69 tall vs. 46 for every other row) is gone."
        ),
    },
    "l_prism": {
        "status": "ok",
        "attempt_svg": "attempts/l_prism_attempt0.svg",
        "attempt_script": "attempt_scripts/l_prism_attempt0.py",
        "notes": (
            "Fresh PythonFullStrategy.run() (no cookbook; 1 attempt) with a "
            "prompt explicitly enumerating the 5 distinct edge dimensions to "
            "brace (overall length 6, width 4, height 3, notch width 2, notch "
            "depth 2) and explicitly forbidding bracing the same edge twice or "
            "reusing the same endpoint pair reversed. The rendered SVG has "
            "exactly 5 draw_brace() paths, one per label (6, 4, 3, 2, 2), and "
            "all 5 have distinct (p1, p2) endpoint pairs (checked as unordered "
            "sets) -- baseline's defect (the same depth edge braced twice, "
            "forward and reversed, producing two overlapping '2' labels ~2px "
            "apart) is gone."
        ),
    },
    "balance_scale": {
        "status": "ok",
        "attempt_svg": "attempts/balance_scale_attempt0.svg",
        "attempt_script": "attempt_scripts/balance_scale_attempt0.py",
        "notes": (
            "Fresh PythonFullStrategy.run() (no cookbook; 1 attempt) with a "
            "prompt spelling out the physical constraint that unsecured pan "
            "contents must rest ABOVE (smaller y than) the pan platform's "
            "surface, not below it. In the rendered SVG the left pan's "
            "platform polygon spans y = 239.95-243.97 and its contents (two "
            "steelblue blocks then three tomato unit-square blocks, stacked "
            "upward) span y = 200.43-239.95; the right pan's platform spans "
            "the same y = 239.95-243.97 and its contents (7 gold coins in "
            "two rows) span y = 203.78-239.95. Every content shape's y-range "
            "sits entirely at or above the platform's top surface (239.95) "
            "on both sides -- baseline's defect (pan contents drawn entirely "
            "below the platform, y = 313.33-443.33 vs. the platform's own "
            "303.33-313.33) is gone."
        ),
    },
}


def build_final_entries(
    baseline_manifest: "list[dict]",
    fresh_choices: "dict[str, dict]",
) -> "list[FinalManifestEntry]":
    """Combine the baseline manifest with `fresh_choices` into
    FinalManifestEntry objects, one per kind in `baseline_manifest`.

    A kind present in `fresh_choices` always gets a "fresh-generation"
    entry built from that dict, regardless of its baseline verdict (this
    is what lets a baseline "partial" kind be legitimately overridden by
    a fresh run's outcome). Every other kind must have had baseline
    verdict "pass" -- raises if not, since a baseline "partial"/"fail"
    kind with no fresh_choices entry would otherwise silently end up
    without any accounted-for outcome.
    """
    entries: "list[FinalManifestEntry]" = []
    for row in baseline_manifest:
        kind = row["kind"]
        if kind in fresh_choices:
            choice = fresh_choices[kind]
            entries.append(
                FinalManifestEntry(
                    kind=kind,
                    svg_path=choice.get("attempt_svg"),
                    source="fresh-generation",
                    status=choice["status"],
                    notes=choice["notes"],
                    script_path=choice.get("attempt_script"),
                )
            )
            continue
        if row["verdict"] != "pass":
            raise ValueError(
                f"kind {kind!r} has baseline verdict {row['verdict']!r} (not "
                "'pass') but no entry in fresh_choices -- every non-passing "
                "baseline kind must be explicitly accounted for"
            )
        entries.append(
            FinalManifestEntry(
                kind=kind,
                svg_path=row["svg_path"],
                source="baseline-reuse",
                status="ok",
                notes=row["notes"],
            )
        )
    return entries


def _copy_svgs(entries: "list[FinalManifestEntry]") -> "list[FinalManifestEntry]":
    """Copy every entry's source SVG into ./svgs/<kind>.svg (and, when
    present, its source script into ./scripts/<kind>.py) and return new
    entries pointing at the copies, so the final manifest is self-contained
    (does not depend on baseline's or gen_diagram_kinds_examples.py's
    output directories staying put)."""
    FINAL_SVG_DIR.mkdir(parents=True, exist_ok=True)
    updated: "list[FinalManifestEntry]" = []
    for entry in entries:
        if entry.svg_path is None:
            updated.append(entry)
            continue
        if entry.source == "baseline-reuse":
            src = BASELINE_DIR / entry.svg_path
        else:
            src = OUT_DIR / entry.svg_path
        dest = FINAL_SVG_DIR / f"{entry.kind}.svg"
        shutil.copyfile(src, dest)

        script_path = None
        if entry.script_path is not None:
            FINAL_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            script_src = OUT_DIR / entry.script_path
            script_dest = FINAL_SCRIPTS_DIR / f"{entry.kind}.py"
            shutil.copyfile(script_src, script_dest)
            script_path = str(script_dest.relative_to(OUT_DIR))

        updated.append(
            FinalManifestEntry(
                kind=entry.kind,
                svg_path=str(dest.relative_to(OUT_DIR)),
                source=entry.source,
                status=entry.status,
                notes=entry.notes,
                script_path=script_path,
            )
        )
    return updated


def main() -> None:
    baseline_manifest = json.loads(BASELINE_MANIFEST_PATH.read_text())
    entries = build_final_entries(baseline_manifest, FRESH_CHOICES)
    entries = _copy_svgs(entries)
    write_manifest(entries, FINAL_MANIFEST_PATH, expected_kinds=KIND_NAMES)
    n_ok = sum(1 for e in entries if e.status == "ok")
    n_gap = sum(1 for e in entries if e.status == "known-gap")
    print(f"[final] wrote {len(entries)} entries to {FINAL_MANIFEST_PATH} ({n_ok} ok, {n_gap} known-gap)")


if __name__ == "__main__":
    main()
