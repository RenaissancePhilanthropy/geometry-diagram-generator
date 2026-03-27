"""
Scenario-level validation checks for TikZ diagrams.

Higher-level validators that compose extraction and geometry functions to check
labels, canvas features, expected point positions, and required draw entities.
"""
from __future__ import annotations

from typing import Any

from .tikz_extraction import extract_labels, extract_canvas_features, extract_draw_commands


def validate_required_labels(tikz: str, required: list[str]) -> dict[str, Any]:
    """
    Check that all required point labels appear in the TikZ source.
    Returns {"passed": bool, "missing": list[str]}.
    """
    labeled: set[str] = set()
    for label in extract_labels(tikz):
        if label["type"] == "label_points":
            labeled.update(label["points"])
        elif label["type"] == "label_point":
            labeled.add(label["point"])
    missing = [name for name in required if name not in labeled]
    return {"passed": len(missing) == 0, "missing": missing}


def validate_required_canvas(tikz: str, required_canvas: dict[str, bool]) -> dict[str, Any]:
    """
    Check that required visible canvas features are present.

    Returns {"passed": bool, "missing": list[str], "features": dict[str, bool]}.
    """
    features = extract_canvas_features(tikz)
    missing = [
        feature
        for feature, required in required_canvas.items()
        if required and not features.get(feature, False)
    ]
    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "features": features,
    }


def validate_expected_points(
    coords: dict[str, tuple[float, float]],
    expected_points: dict[str, list[float] | tuple[float, float]],
    tolerance: float = 1e-4,
) -> dict[str, Any]:
    """
    Check that named points resolve to the expected coordinates.

    Returns:
      {"passed": bool, "missing": list[str], "mismatches": {name: {...}}}
    """
    missing: list[str] = []
    mismatches: dict[str, dict[str, list[float]]] = {}

    for name, expected in expected_points.items():
        if name not in coords:
            missing.append(name)
            continue
        expected_xy = (float(expected[0]), float(expected[1]))
        actual_xy = coords[name]
        if (
            abs(actual_xy[0] - expected_xy[0]) > tolerance
            or abs(actual_xy[1] - expected_xy[1]) > tolerance
        ):
            mismatches[name] = {
                "expected": [expected_xy[0], expected_xy[1]],
                "actual": [actual_xy[0], actual_xy[1]],
            }

    return {
        "passed": len(missing) == 0 and len(mismatches) == 0,
        "missing": missing,
        "mismatches": mismatches,
    }


def validate_required_entities(tikz: str, required: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Check that all required draw entities appear in the TikZ source.

    Each entry in `required` is a dict with at least "type" (matching
    extract_draw_commands types: polygon, segment, line, circle), and
    optionally "args" — a dict of key-value pairs that must match the
    extracted command dict.

    Returns {"passed": bool, "missing": list[dict]}.
    """
    commands = extract_draw_commands(tikz)
    missing: list[dict[str, Any]] = []
    for entity in required:
        entity_type = entity.get("type")
        entity_args = entity.get("args", {})
        found = any(
            cmd["type"] == entity_type
            and all(cmd.get(k) == v for k, v in entity_args.items())
            for cmd in commands
        )
        if not found:
            missing.append(entity)
    return {"passed": len(missing) == 0, "missing": missing}
