"""Scenario YAML loading and validation for eval runner."""
from __future__ import annotations

from typing import Any

from geometry_diagrams.features import parse_features

# Kept in sync with the `match ptype` cases in evals/sympy_checks.py's
# _check_sympy_property BY HAND — the two are not derived from a single
# source of truth. A type listed as "supported" here but unhandled there
# doesn't raise; it just silently no-ops every scenario check of that type
# (see _check_sympy_property's `case _` fallback). This is exactly how
# "angle_equal" went unchecked across dozens of existing scenarios for an
# unknown period — this file called it supported while sympy_checks.py had
# no case for it. When adding a type to one file, add it to the other too.
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
    "angle_value",
    "distance_equals",
    "angle_bisector",
    "intersects",
    "label_present",
    "mark_present",
    "equidistant_from_sides",
    "centroid",
    "opposite_side",
    "same_side",
    "not_between",
    # Prism properties: evaluated on the full compiled symbol table through
    # query_prism (evals/sympy_checks.py _validate_prism_properties), never on
    # the 2D float coordinates.
    "prism_volume",
    "prism_dimensions",
    # Stack property: evaluated through query_stack on the full symbol table
    # (evals/sympy_checks.py _validate_stack_properties); args [stack_id|"*", count].
    "stack_cube_count",
    # args [stack_id|"*", length, width, height] (ints) / [stack_id|"*", bool].
    "stack_extents",
    "stack_is_height_map",
}

# Structural check types and what each one counts. polygon_count counts
# authored 2D plane polygons only (prisms never count); solid_count counts
# authored solids (e.g. rectangular_prism).
_SUPPORTED_STRUCTURAL_TYPES = ("polygon_count", "solid_count")

_CANVAS_FEATURES = {"grid", "axes"}

# Default tolerance for expected_points coordinate matching
_DEFAULT_POINT_TOLERANCE = 1e-4


def _validate_solid_count_args(args: dict[str, Any], where: str) -> None:
    """solid_count args: optional kind (str), min (int >= 0), optional
    literal dimensions length/width/height (numbers) and, for block_stack,
    a literal cube_count (int >= 0)."""
    unknown = sorted(set(args) - {"kind", "min", "length", "width", "height", "cube_count"})
    if unknown:
        raise ValueError(f"{where}: unknown solid_count arg(s) {unknown}")
    if "kind" in args and not (isinstance(args["kind"], str) and args["kind"].strip()):
        raise ValueError(f"{where}: solid_count 'kind' must be a non-empty string")
    if "min" in args and (
        isinstance(args["min"], bool) or not isinstance(args["min"], int) or args["min"] < 0
    ):
        raise ValueError(f"{where}: solid_count 'min' must be a non-negative integer")
    for dim in ("length", "width", "height"):
        if dim in args and (
            isinstance(args[dim], bool) or not isinstance(args[dim], (int, float))
        ):
            raise ValueError(f"{where}: solid_count {dim!r} must be a literal number")


    if "cube_count" in args and (
        isinstance(args["cube_count"], bool)
        or not isinstance(args["cube_count"], int)
        or args["cube_count"] < 0
    ):
        raise ValueError(f"{where}: solid_count 'cube_count' must be a non-negative integer")


def _validate_stack_cube_count_args(args: list, where: str) -> None:
    """stack_cube_count args: [stack id or "*", expected count (int >= 0)]."""
    ok = (
        len(args) == 2
        and isinstance(args[0], str) and args[0].strip()
        and isinstance(args[1], int) and not isinstance(args[1], bool) and args[1] >= 0
    )
    if not ok:
        raise ValueError(
            f"{where}: stack_cube_count args must be [stack id or \"*\", "
            "non-negative integer count]"
        )


def _is_stack_id(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _validate_stack_extents_args(args: list, where: str) -> None:
    """stack_extents args: [stack id or "*", length, width, height] (ints >= 0)."""
    ok = (
        len(args) == 4
        and _is_stack_id(args[0])
        and all(isinstance(a, int) and not isinstance(a, bool) and a >= 0 for a in args[1:])
    )
    if not ok:
        raise ValueError(
            f"{where}: stack_extents args must be [stack id or \"*\", "
            "length, width, height] (non-negative integers)"
        )


def _validate_stack_is_height_map_args(args: list, where: str) -> None:
    """stack_is_height_map args: [stack id or "*", true/false]."""
    if not (len(args) == 2 and _is_stack_id(args[0]) and isinstance(args[1], bool)):
        raise ValueError(
            f"{where}: stack_is_height_map args must be [stack id or \"*\", true/false]"
        )


def split_by_required_features(
    scenarios: list[dict[str, Any]], enabled: "frozenset[str] | set[str]"
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Partition scenarios into (runnable, skipped). A scenario runs only when
    every group in its ``requires_features`` is enabled; otherwise it is
    skipped, reported as ``(scenario_id, reason)`` -- never a failure."""
    runnable: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    for sc in scenarios:
        missing = [g for g in sc.get("requires_features", []) if g not in enabled]
        if missing:
            skipped.append((
                sc["id"],
                "requires feature group(s) not enabled: " + ", ".join(missing),
            ))
        else:
            runnable.append(sc)
    return runnable, skipped


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
            if prop_type == "stack_cube_count":
                _validate_stack_cube_count_args(args, prop_where)
            elif prop_type == "stack_extents":
                _validate_stack_extents_args(args, prop_where)
            elif prop_type == "stack_is_height_map":
                _validate_stack_is_height_map_args(args, prop_where)

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

        # fail_on_warnings
        fail_on_warnings = raw.get("fail_on_warnings", [])
        if fail_on_warnings is None:
            fail_on_warnings = []
        if not isinstance(fail_on_warnings, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'fail_on_warnings' must be a list when provided"
            )
        for i, sub in enumerate(fail_on_warnings, start=1):
            if not isinstance(sub, str) or not sub:
                raise ValueError(
                    f"{where} ({scenario_id}) fail_on_warnings[{i}]: must be a non-empty string"
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
            if sc_type not in _SUPPORTED_STRUCTURAL_TYPES:
                raise ValueError(
                    f"{sc_where}: unsupported 'type'={sc_type!r}; supported: "
                    "polygon_count (authored 2D plane polygons only; prisms never "
                    "count), solid_count"
                )
            if not isinstance(sc_args, dict):
                raise ValueError(f"{sc_where}: 'args' must be an object")
            if sc_type == "solid_count":
                _validate_solid_count_args(sc_args, sc_where)
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

        requires_features = raw.get("requires_features", [])
        if requires_features is None:
            requires_features = []
        if not isinstance(requires_features, list) or not all(
            isinstance(g, str) for g in requires_features
        ):
            raise ValueError(
                f"{where} ({scenario_id}): 'requires_features' must be a list of "
                "feature group names when provided"
            )
        try:
            parse_features(requires_features)
        except ValueError as exc:
            raise ValueError(f"{where} ({scenario_id}) requires_features: {exc}") from exc

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
                "fail_on_warnings": list(fail_on_warnings),
                "required_entities": list(required_entities),
                "required_canvas": normalized_canvas,
                "expected_points": normalized_points,
                "coordinate_tolerance": float(coordinate_tolerance),
                "queries": normalized_queries,
                "requires_features": list(requires_features),
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
