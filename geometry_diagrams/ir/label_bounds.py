# geometry_diagrams/ir/label_bounds.py
"""Black-box label-bounds checker for rendered SVG diagrams.

This is a pure post-render check: it parses an already-rendered SVG string
(as produced by :func:`geometry_diagrams.ir.to_svg.ir_to_svg`) and reports
every label whose bounding box extends past the SVG's own declared
``viewBox``. It does not re-derive positions/widths from geometry or
recompute anything `to_svg.py`'s layout pass already did — it trusts the
``data-bbox`` attribute `to_svg.py` stamps on every emitted label element at
the point it finalizes label positions (after nudging/collision
resolution), so this stays independent of `to_svg.py`'s internal
nudging/bbox-estimation machinery and needs no change when that machinery
changes.

Why both `<text>` and `<g>` matter: `to_svg.py` renders plain-text labels as
``<text>`` elements but renders anything `label_needs_mathtext()` flags
(LaTeX fractions, sub/superscripts, arrows -- exactly what
`equation_steps()`/`stack_lines()` produce) as ``<g>``-wrapped path glyphs
via `MathGlyph`, with no `<text>` element at all. Reading the stamped
``data-bbox``/``data-label-text`` attributes (present on both element kinds,
stamped at the same call site regardless of which one gets emitted) is what
makes this checker correct for both -- a checker that only looked for
`<text>` elements would silently miss every math/LaTeX label.

Caveat: `data-bbox` is only as accurate as `to_svg.py`'s own width estimate
for the label (a matplotlib-derived box for math labels, a char-count
heuristic -- `_estimate_text_width` -- for plain text). This checker cannot
be more precise than that estimate; it inherits the same false-positive/
false-negative risk the label-nudging system already has today.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelOverflow:
    """One label whose stamped bbox extends past the SVG's viewBox."""

    text: str
    bbox: tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max), SVG px
    overflow: float  # max distance any single edge extends past the viewBox, SVG px


def find_out_of_bounds_labels(svg: str) -> list[LabelOverflow]:
    """Parse rendered *svg* and return every label extending past its viewBox.

    Reads the SVG's `viewBox` attribute for the canvas bounds, then walks
    every element carrying a `data-bbox` attribute (stamped by `to_svg.py`
    on both `<text>` and math-glyph `<g>` label elements) and flags any
    whose box is not fully contained within the viewBox.

    Returns an empty list if *svg* has no `viewBox` (nothing to check
    against) or no labels at all.
    """
    root = ET.fromstring(svg)
    viewbox = root.get("viewBox")
    if not viewbox:
        return []
    vx0, vy0, vw, vh = (float(v) for v in viewbox.split())
    vx1, vy1 = vx0 + vw, vy0 + vh

    violations: list[LabelOverflow] = []
    for el in root.iter():
        bbox_attr = el.get("data-bbox")
        if bbox_attr is None:
            continue
        bx0, by0, bx1, by1 = (float(v) for v in bbox_attr.split(","))
        overflow = max(vx0 - bx0, bx1 - vx1, vy0 - by0, by1 - vy1, 0.0)
        if overflow > 0:
            text = el.get("data-label-text", "")
            violations.append(
                LabelOverflow(text=text, bbox=(bx0, by0, bx1, by1), overflow=overflow)
            )
    return violations
