"""Combine run_baseline.py's mechanical generation_log.json with hand-
reviewed verdicts (VERDICTS below -- filled in after actually looking at
each rendered SVG, per ticket 07's Honesty self-review criterion) into the
final manifest.json (manifest_lib.ManifestEntry schema) that later tickets
consume.

Usage: .venv/bin/python .scratch/diagram-kinds-poc/baseline/finalize_manifest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINE_DIR = Path(__file__).resolve().parent
if str(BASELINE_DIR) not in sys.path:
    sys.path.insert(0, str(BASELINE_DIR))

from kinds_prompts import KIND_NAMES, KIND_PROMPTS  # noqa: E402
from manifest_lib import ManifestEntry, write_manifest  # noqa: E402

GENERATION_LOG_PATH = BASELINE_DIR / "generation_log.json"
MANIFEST_PATH = BASELINE_DIR / "manifest.json"

# Filled in by hand after rendering every SVG in svgs/ with headless Chrome
# (see the ticket 07 report for the full rationale, including why headless
# Chrome rather than cairosvg -- cairosvg mis-renders a <text> element that
# mixes a <tspan> with trailing plain text, producing a false "overlapping
# text" artifact on several otherwise-clean SVGs that a real browser renders
# correctly). kind -> (verdict, notes).
VERDICTS: "dict[str, tuple[str, str]]" = {
    "grid_area": ("pass", "Clean 6x4 rectangle exactly aligned to the background unit grid; area label correct."),
    "tape_diagram": ("pass", "Three equal sections labeled 4, brace labeled 12, title equation correct."),
    "number_line": ("pass", "Clean 0-10 number line, correct tick marks, points at 3 and 7.5 plotted and labeled."),
    "coordinate_plane": (
        "partial",
        "Triangle, translation, and all vertex labels render correctly, but the "
        "'Translation: (x-2, y-3)' caption is positioned partly off the left edge "
        "of the canvas and is clipped/unreadable.",
    ),
    "scatter_plot": (
        "partial",
        "Points, line of best fit, and slope triangle are correctly placed, but the "
        "canvas is far too narrow for the content: axis title 'Hours...', the "
        "'rise'/'run' labels, and other text are cut off at the right edge.",
    ),
    "shape_comparison": (
        "partial",
        "Square and rectangle with correct dimensions, but the rectangle's "
        "'Area=...'/'Perimeter=...' labels are placed on top of each other and "
        "the closing summary sentence is clipped at the bottom of the canvas.",
    ),
    "attribute_chart": (
        "partial",
        "Correct table structure and check/cross marks, but every column header "
        "and row label is duplicated (rendered twice, stacked), and two extra "
        "blank decorative header bands sit above the real table.",
    ),
    "work_table": ("pass", "Clean two-column ratio table, correct values."),
    "area_model": (
        "partial",
        "2x2 box-method grid with factors placed outside as requested, but the "
        "right-hand column's cells are completely empty (missing 3x5 and 3x10 "
        "partial products) and the left column's cell text overlaps/runs together.",
    ),
    "equation_steps": ("pass", "Five solving steps stacked cleanly and correctly using the new equation_steps() primitive."),
    "angle_figure": ("pass", "Two parallel lines with matching arrowheads, transversal, and angles 1-4 correctly labeled."),
    "cube_volume": ("pass", "3x2x2 prism with a unit-cube grid on every visible face; dimensions labeled."),
    "prism_3d": ("pass", "Labeled 5x3x4 prism with dashed hidden edges, clean vertex labels."),
    "l_prism": ("pass", "Single joined L-shaped solid (not two separate boxes) with all edge lengths labeled."),
    "prism_net": ("pass", "Correct 6-face net on a grid with dimensions; face labels are a bit crowded but legible."),
    "composite_polygon": ("pass", "L-shaped floor plan correctly decomposed into two labeled rectangles with a total-area calculation."),
    "dot_plot": ("pass", "Correct stacked-dot counts above each shoe size value; axis label legible."),
    "circle": ("pass", "Circle with center, radius, and diameter segments correctly labeled (r = 4 cm, d = 8 cm)."),
    "column_arithmetic": ("pass", "Correct column-addition layout with carry marks, rule line, and operator in the left column."),
    "long_division": ("pass", "Correct house/bracket layout with quotient above and multiply-subtract steps shown below."),
    "composite": ("pass", "Two labeled figures (rectangle + circle) connected by a labeled draw_brace() curly brace."),
    "object_array": ("pass", "3 groups of 5 objects in distinct rows/colors with a correct summary label."),
    "bar_graph": ("pass", "Correct vertical bar chart with labeled axes and value labels; the 'Grapes' x-axis tick wraps onto two lines but is still readable."),
    "place_value_blocks": ("pass", "Correct 2 hundreds-flats / 4 tens-rods / 3 ones for 243, each internally ruled into unit squares."),
    "place_value_chart": ("pass", "Clean 4-column place-value chart with digits correctly placed."),
    "number_bond": ("pass", "Correct part-whole number bond: 12 on top, 7 and 5 as parts below."),
    "ruler_measure": ("pass", "Ruler with quarter-inch ticks and a pencil correctly aligned from 0 to 4.5 inches."),
    "fill_level": ("pass", "Two same-size containers correctly shaded to 25% and 75% with labels."),
    "balance_scale": ("pass", "Correct level beam on a fulcrum with two pans; left pan shows 2x+3, right pan shows 7, matching the requested equation."),
    "none": ("pass", "Not a rendering kind -- 'none' means no diagram should be shown, so there is nothing to generate or render."),
}


def build_entries(
    generation_log: "list[dict]",
    verdicts: "dict[str, tuple[str, str]]",
) -> "list[ManifestEntry]":
    """Combine `generation_log` (run_baseline.py's raw per-kind facts) with
    `verdicts` (hand-reviewed verdict + notes per kind) into ManifestEntry
    objects. Raises KeyError if `verdicts` is missing a kind that
    kinds_prompts.KIND_PROMPTS declares -- an incomplete review must fail
    loudly, not silently produce a partial manifest.

    A "pass"/"partial" verdict pulls its svg_path from the generation log
    (raising if that kind's generation didn't actually produce one -- a
    reviewer marking something "pass" must be reviewing a real SVG, not a
    typo). A "fail" verdict always gets svg_path=None, regardless of what
    the log says, per ticket 07's schema (fail means no usable SVG)."""
    log_by_kind = {r["kind"]: r for r in generation_log}
    entries: "list[ManifestEntry]" = []
    for kind, _prompt in KIND_PROMPTS:
        verdict, notes = verdicts[kind]
        svg_path = None
        if verdict in ("pass", "partial") and kind != "none":
            # "none" is the one deliberate exception (ticket 07, item 30) --
            # see manifest_lib.ManifestEntry's own docstring/validation.
            log_entry = log_by_kind.get(kind)
            svg_path = log_entry.get("svg_path") if log_entry else None
            if not svg_path:
                raise ValueError(
                    f"kind {kind!r} marked {verdict!r} but generation_log has no "
                    "svg_path for it"
                )
        entries.append(ManifestEntry(kind=kind, verdict=verdict, svg_path=svg_path, notes=notes))
    return entries


def main() -> None:
    if not VERDICTS:
        raise RuntimeError(
            "VERDICTS is empty -- fill it in by hand after reviewing every "
            "rendered SVG before running finalize_manifest.py"
        )
    generation_log = json.loads(GENERATION_LOG_PATH.read_text())
    entries = build_entries(generation_log, VERDICTS)
    write_manifest(entries, MANIFEST_PATH, expected_kinds=KIND_NAMES)
    print(f"[baseline] wrote {len(entries)} entries to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
