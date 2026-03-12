from __future__ import annotations

import re


_POINT_NAME = r"([A-Z][A-Za-z0-9_]*)"
_NUMBER = r"([+-]?\d*\.?\d+)"
_COORD_PATTERNS = [
    re.compile(rf"\bplot\s+{_POINT_NAME}\s+at\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)", re.IGNORECASE),
    re.compile(rf"\b{_POINT_NAME}\s+at\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)", re.IGNORECASE),
    re.compile(rf"\b{_POINT_NAME}\s*=\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)", re.IGNORECASE),
    re.compile(rf"\b{_POINT_NAME}\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)"),
]


def extract_explicit_point_coordinates(prompt: str) -> dict[str, tuple[float, float]]:
    """Extract named point coordinates explicitly stated in the prompt."""
    coords: dict[str, tuple[float, float]] = {}
    for pattern in _COORD_PATTERNS:
        for match in pattern.finditer(prompt):
            name, x, y = match.group(1), float(match.group(2)), float(match.group(3))
            coords[name] = (x, y)
    return coords


def detect_prompt_features(prompt: str) -> dict[str, bool]:
    """Detect prompt features that benefit from deterministic structured hints."""
    lowered = prompt.lower()
    return {
        "grid": any(token in lowered for token in ("coordinate grid", "grid", "axes", "coordinate plane")),
        "perpendicular_bisector": "perpendicular bisector" in lowered,
        "midpoint": "midpoint" in lowered,
        "incircle": "incircle" in lowered or "inscribed circle" in lowered,
        "circumcircle": "circumcircle" in lowered or "circumscribed circle" in lowered,
        "tangent": "tangent" in lowered,
        "triangle_centers": any(
            token in lowered
            for token in ("euler line", "circumcenter", "centroid", "orthocenter", "incenter")
        ),
        "similar_triangles": "similar triangle" in lowered or "similar triangles" in lowered,
        "transversal": "transversal" in lowered,
    }


def build_structured_hint_text(prompt: str) -> str:
    """Build deterministic structured guidance derived only from the user prompt."""
    coords = extract_explicit_point_coordinates(prompt)
    features = detect_prompt_features(prompt)
    lines: list[str] = []

    if coords:
        lines.extend([
            "Structured hints for this prompt:",
            "- Use point_fixed for every explicitly specified coordinate.",
            "- Preserve exact numeric coordinates from the prompt; do not approximate or relocate them.",
        ])
        for name, (x, y) in coords.items():
            lines.append(f"- Exact point: {name} = ({x:g}, {y:g})")

    if features["grid"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.extend([
            "- This is a coordinate-plane diagram: set canvas.grid = true and canvas.axes = true.",
            "- Use canvas.grid_step = 1 and canvas.tick_step = 1.",
            "- Set canvas.show_ticks = true, canvas.show_tick_labels = true, and canvas.show_axis_labels = true.",
            "- Choose canvas bounds that include all named points plus a small margin and include the origin.",
            "- If you show coordinates in point labels, keep the point ID unchanged and use LabelPoint.text, for example A\\,(0,0).",
        ])

    if features["perpendicular_bisector"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.extend([
            "- Construct and draw an actual line object for the perpendicular bisector, not a short segment used as a visual proxy.",
            "- Canonical pattern: define segment AB, define midpoint M, define l_perp = line_perp_through(through=M, to_line=l_AB), then draw l_perp with add=[...].",
        ])

    if features["incircle"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.extend([
            "- Build the triangle first, then define the incenter with point_triangle_center(which=\"incenter\").",
            "- Derive tangency points from perpendiculars from the incenter to the triangle sides.",
            "- Draw the incircle as circle_center_point(center=I, through=Ta).",
            "- Include must-checks that tangency points lie on the side lines, the radii to tangency points are perpendicular to those sides, and the inradii are equal.",
            "- Do not rely on a contains(I, T) must-check for the incircle prompt.",
        ])

    if features["circumcircle"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.append(
            "- Prefer circle_through3 or a computed circumcenter over hard-coded center coordinates."
        )

    if features["triangle_centers"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.append(
            "- Prefer point_triangle_center for circumcenter, centroid, orthocenter, and incenter instead of hard-coded coordinates."
        )

    if features["similar_triangles"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.append(
            "- If similarity is part of the prompt, construct triangles so the similarity follows from the coordinates or checks, not only from marks."
        )

    if features["transversal"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.append(
            "- When a transversal intersects named lines, define the intersection points explicitly with point_intersection instead of hand-entered approximations."
        )

    if features["tangent"]:
        if not lines:
            lines.append("Structured hints for this prompt:")
        lines.append(
            "- Use a tangent construction or tangent check when tangency is semantically required; avoid eyeballed tangency."
        )

    return "\n".join(lines)


def augment_structured_prompt(prompt: str) -> str:
    """Append deterministic structured hints to the user prompt when useful."""
    hints = build_structured_hint_text(prompt)
    if not hints:
        return prompt
    return f"{prompt}\n\n{hints}"
