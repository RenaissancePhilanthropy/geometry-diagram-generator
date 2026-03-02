"""
SVG quality checks for TikZ/dvisvgm-rendered diagrams.

TikZ SVGs produced by dvisvgm (--no-fonts --bbox=min) differ from
Penrose-generated SVGs: they contain no <title> tags on geometric elements,
and text is converted to glyph paths. These checks focus on structural
well-formedness and visual sanity rather than semantic geometry parsing.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


_SVG_NS = "http://www.w3.org/2000/svg"
_DRAWING_TAGS = {
    f"{{{_SVG_NS}}}path",
    f"{{{_SVG_NS}}}line",
    f"{{{_SVG_NS}}}circle",
    f"{{{_SVG_NS}}}ellipse",
    f"{{{_SVG_NS}}}rect",
    f"{{{_SVG_NS}}}polyline",
    f"{{{_SVG_NS}}}polygon",
}


def check_svg_wellformed(svg: str) -> str | None:
    """
    Verify the SVG is valid XML with an <svg> root element and a viewBox.
    Returns None on success, or a failure message string.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return f"SVG is not valid XML: {e}"

    tag = root.tag
    if tag != f"{{{_SVG_NS}}}svg" and tag != "svg":
        return f"Root element is <{tag}>, expected <svg>"

    if root.get("viewBox") is None:
        return "SVG is missing a viewBox attribute"

    return None


def check_svg_has_content(svg: str) -> str | None:
    """
    Verify the SVG contains at least one visible drawing element.
    Catches cases where TikZ compiled but produced an empty picture.
    Returns None on success, or a failure message string.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return "SVG is not valid XML"

    for elem in root.iter():
        if elem.tag in _DRAWING_TAGS:
            # Verify the path actually has data (not empty d="")
            if elem.tag == f"{{{_SVG_NS}}}path":
                d = (elem.get("d") or "").strip()
                if not d:
                    continue
            return None  # Found a non-empty drawing element

    return "SVG contains no visible drawing elements (path, line, circle, etc.)"


def check_svg_reasonable_size(svg: str) -> str | None:
    """
    Verify the SVG viewBox dimensions are within sane bounds.
    Catches degenerate zero-size or astronomically large diagrams.
    Returns None on success, or a failure message string.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return "SVG is not valid XML"

    viewbox = root.get("viewBox", "")
    parts = viewbox.split()
    if len(parts) != 4:
        return f"viewBox has unexpected format: {viewbox!r}"

    try:
        _min_x, _min_y, width, height = (float(p) for p in parts)
    except ValueError:
        return f"viewBox contains non-numeric values: {viewbox!r}"

    if width <= 0 or height <= 0:
        return f"SVG has zero or negative viewBox dimensions: {width}×{height}"

    if width > 100_000 or height > 100_000:
        return f"SVG viewBox is unreasonably large: {width}×{height}"

    return None


def run_svg_checks(svg: str, checks: list | None = None) -> list[str]:
    """
    Run all SVG quality checks and return a list of failure messages.
    An empty list means all checks passed.

    Args:
        svg: SVG string to check.
        checks: Optional list of check functions to run. Defaults to all checks.
    """
    if checks is None:
        checks = [check_svg_wellformed, check_svg_has_content, check_svg_reasonable_size]

    failures = []
    for check in checks:
        result = check(svg)
        if result is not None:
            failures.append(result)

    return failures
