"""Scenario YAML loading and validation for eval runner."""
from __future__ import annotations

from typing import Any

_SUPPORTED_PROPERTY_TYPES = {
    "right_angle",
    "midpoint",
    "collinear",
    "equal_lengths",
    "parallel",
    "perpendicular",
    "point_on_line",
    "point_on_segment",
    "point_on_circle",
    "tangent",
    "angle_equal",
    "angle_bisector",
    "intersects",
    "label_present",
    "mark_present",
    "equidistant_from_sides",
    "centroid",
    "opposite_side",
    "same_side",
    "not_between",
}

_CANVAS_FEATURES = {"grid", "axes"}

# Default tolerance for expected_points coordinate matching
_DEFAULT_POINT_TOLERANCE = 1e-4


def _validate_scenarios(raw_scenarios: Any) -> list[dict[str, Any]]:
    """Validate scenario YAML shape and return normalized list of scenarios."""
    if not isinstance(raw_scenarios, list):
        raise ValueError("Scenario file must be a YAML list of scenario objects")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, raw in enumerate(raw_scenarios, start=1):
        where = f"scenario #{idx}"
        if not isinstance(raw, dict):
            raise ValueError(f"{where}: expected mapping/object, got {type(raw).__name__}")

        scenario_id = raw.get("id")
        prompt = raw.get("prompt")

        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError(f"{where}: 'id' must be a non-empty string")
        if scenario_id in seen_ids:
            raise ValueError(f"{where}: duplicate id '{scenario_id}'")
        seen_ids.add(scenario_id)

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{where} ({scenario_id}): 'prompt' must be a non-empty string")

        expected_properties = raw.get("expected_properties", [])
        if expected_properties is None:
            expected_properties = []
        if not isinstance(expected_properties, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'expected_properties' must be a list when provided"
            )

        normalized_props: list[dict[str, Any]] = []
        for pidx, prop in enumerate(expected_properties, start=1):
            prop_where = f"{where} ({scenario_id}) expected_properties[{pidx}]"
            if not isinstance(prop, dict):
                raise ValueError(f"{prop_where}: expected mapping/object")

            name = prop.get("name")
            prop_type = prop.get("type")
            args = prop.get("args")

            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{prop_where}: 'name' must be a non-empty string")
            if not isinstance(prop_type, str) or prop_type not in _SUPPORTED_PROPERTY_TYPES:
                supported = ", ".join(sorted(_SUPPORTED_PROPERTY_TYPES))
                raise ValueError(
                    f"{prop_where}: unsupported 'type'={prop_type!r}; supported: {supported}"
                )
            if not isinstance(args, list):
                raise ValueError(f"{prop_where}: 'args' must be a list")

            normalized_props.append(
                {
                    "name": name,
                    "type": prop_type,
                    "args": args,
                }
            )

        # required_labels
        required_labels = raw.get("required_labels", [])
        if required_labels is None:
            required_labels = []
        if not isinstance(required_labels, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_labels' must be a list when provided"
            )
        for i, label in enumerate(required_labels, start=1):
            if not isinstance(label, str) or not label.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) required_labels[{i}]: must be a non-empty string"
                )

        # required_entities
        required_entities = raw.get("required_entities", [])
        if required_entities is None:
            required_entities = []
        if not isinstance(required_entities, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_entities' must be a list when provided"
            )
        for i, entity in enumerate(required_entities, start=1):
            if not isinstance(entity, dict):
                raise ValueError(
                    f"{where} ({scenario_id}) required_entities[{i}]: expected mapping/object"
                )
            if "type" not in entity or not isinstance(entity["type"], str):
                raise ValueError(
                    f"{where} ({scenario_id}) required_entities[{i}]: 'type' must be a string"
                )

        tags = raw.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            raise ValueError(f"{where} ({scenario_id}): 'tags' must be a list when provided")
        for i, tag in enumerate(tags, start=1):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) tags[{i}]: must be a non-empty string"
                )

        required_canvas = raw.get("required_canvas", {})
        if required_canvas is None:
            required_canvas = {}
        if not isinstance(required_canvas, dict):
            raise ValueError(
                f"{where} ({scenario_id}): 'required_canvas' must be an object when provided"
            )
        normalized_canvas: dict[str, bool] = {}
        for key, value in required_canvas.items():
            if key not in _CANVAS_FEATURES:
                supported = ", ".join(sorted(_CANVAS_FEATURES))
                raise ValueError(
                    f"{where} ({scenario_id}): unsupported required_canvas key {key!r}; "
                    f"supported: {supported}"
                )
            if not isinstance(value, bool):
                raise ValueError(
                    f"{where} ({scenario_id}) required_canvas[{key!r}]: must be a boolean"
                )
            normalized_canvas[key] = value

        expected_points = raw.get("expected_points", {})
        if expected_points is None:
            expected_points = {}
        if not isinstance(expected_points, dict):
            raise ValueError(
                f"{where} ({scenario_id}): 'expected_points' must be an object when provided"
            )
        normalized_points: dict[str, list[float]] = {}
        for name, coords in expected_points.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) expected_points: point names must be non-empty strings"
                )
            if (
                not isinstance(coords, list)
                or len(coords) != 2
                or not all(isinstance(v, (int, float)) for v in coords)
            ):
                raise ValueError(
                    f"{where} ({scenario_id}) expected_points[{name!r}]: "
                    "must be a 2-item numeric list"
                )
            normalized_points[name] = [float(coords[0]), float(coords[1])]

        coordinate_tolerance = raw.get("coordinate_tolerance", _DEFAULT_POINT_TOLERANCE)
        if not isinstance(coordinate_tolerance, (int, float)) or coordinate_tolerance <= 0:
            raise ValueError(
                f"{where} ({scenario_id}): 'coordinate_tolerance' must be a positive number"
            )

        # structural_checks: check structural properties of IR/TikZ (e.g. polygon count)
        structural_checks = raw.get("structural_checks", [])
        if structural_checks is None:
            structural_checks = []
        if not isinstance(structural_checks, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'structural_checks' must be a list when provided"
            )
        normalized_structural: list[dict[str, Any]] = []
        for sidx, sc in enumerate(structural_checks, start=1):
            sc_where = f"{where} ({scenario_id}) structural_checks[{sidx}]"
            if not isinstance(sc, dict):
                raise ValueError(f"{sc_where}: expected mapping/object")
            sc_name = sc.get("name")
            sc_type = sc.get("type")
            sc_args = sc.get("args", {})
            if not isinstance(sc_name, str) or not sc_name.strip():
                raise ValueError(f"{sc_where}: 'name' must be a non-empty string")
            if sc_type not in ("polygon_count",):
                raise ValueError(
                    f"{sc_where}: unsupported 'type'={sc_type!r}; supported: polygon_count"
                )
            if not isinstance(sc_args, dict):
                raise ValueError(f"{sc_where}: 'args' must be an object")
            normalized_structural.append({"name": sc_name, "type": sc_type, "args": sc_args})

        # queries: optional list of follow-up questions for query_diagram eval
        queries = raw.get("queries", [])
        if queries is None:
            queries = []
        if not isinstance(queries, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'queries' must be a list when provided"
            )
        normalized_queries: list[dict[str, Any]] = []
        for qidx, q in enumerate(queries, start=1):
            q_where = f"{where} ({scenario_id}) queries[{qidx}]"
            if not isinstance(q, dict):
                raise ValueError(f"{q_where}: expected mapping/object")

            question = q.get("question")
            if not isinstance(question, str) or not question.strip():
                raise ValueError(f"{q_where}: 'question' must be a non-empty string")

            normalized_queries.append({
                "question": question,
                "expected_tool_call": q.get("expected_tool_call"),
                "expected_answer": q.get("expected_answer"),
            })

        tier = raw.get("tier")
        if tier is not None and (not isinstance(tier, int) or tier < 1):
            raise ValueError(f"{where} ({scenario_id}): 'tier' must be a positive integer")
        normalized.append(
            {
                "id": scenario_id,
                "tier": tier,
                "tags": list(tags),
                "prompt": prompt,
                "expected_properties": normalized_props,
                "structural_checks": normalized_structural,
                "required_labels": list(required_labels),
                "required_entities": list(required_entities),
                "required_canvas": normalized_canvas,
                "expected_points": normalized_points,
                "coordinate_tolerance": float(coordinate_tolerance),
                "queries": normalized_queries,
            }
        )

    return normalized


def load_scenarios(path: str) -> list[dict]:
    """Load and validate scenarios from a YAML file path."""
    import yaml
    from pathlib import Path
    with Path(path).open() as f:
        raw = yaml.safe_load(f)
    return _validate_scenarios(raw)
