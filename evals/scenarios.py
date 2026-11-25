"""Scenario YAML loading and validation for eval runner."""
from __future__ import annotations

import logging
from typing import Any, Callable

from geometry_diagrams.features import parse_features

logger = logging.getLogger(__name__)

# Kept in sync with the `match ptype` cases in evals/sympy_checks.py's
# _check_sympy_property BY HAND — the two are not derived from a single
# source of truth. A type listed as "supported" here but unhandled there
# doesn't raise; it just silently no-ops every scenario check of that type
# (see _check_sympy_property's `case _` fallback). This is exactly how
# "angle_equal" went unchecked across dozens of existing scenarios for an
# unknown period — this file called it supported while sympy_checks.py had
# no case for it. When adding a type to one file, add it to the other too.
_PROPERTY_ARG_VALIDATORS: dict[str, Callable[[list, str], None]] = {}
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

# Tolerance dimension of each sympy-evaluated property type: the power of the
# figure's length scale its compared quantity carries, so a ``rel_tol`` (a
# fraction of the figure's size) becomes ``rel_tol * scale ** dimension`` in the
# check's own units. 0 = only an absolute ``tol`` applies: angles (radians) and a
# fraction along a segment are dimensionless, and the side checks use ``tol`` as a
# required margin (raising it makes them stricter), so a figure-scaled slack
# would be meaningless. A type missing from this table
# (prism/stack, rendering-only, unsupported) takes neither field.
PROPERTY_TOL_DIMENSION: dict[str, int] = {
    "midpoint": 1, "equal_lengths": 1, "point_on_line": 1, "point_on_segment": 1,
    "point_on_circle": 1, "tangent": 1, "distance_equals": 1, "intersects": 1,
    "equidistant_from_sides": 1, "centroid": 1,
    "collinear": 2, "parallel": 2, "perpendicular": 2,
    "opposite_side": 0, "same_side": 0,
    "right_angle": 0, "angle_equal": 0, "angle_value": 0, "angle_bisector": 0,
    "not_between": 0,
}


def _validate_property_tolerances(prop: dict, prop_type: str, where: str) -> dict[str, float]:
    """The optional ``tol`` (absolute, in the check's units; radians for an angle
    check) and ``rel_tol`` (a fraction of the figure's size) of one property:
    positive finite numbers, ``rel_tol`` only where the compared quantity
    scales with the figure. Returns just the fields that were given."""
    import math
    out: dict[str, float] = {}
    for key in ("tol", "rel_tol"):
        if key not in prop:
            continue
        value = prop[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{where}: '{key}' must be a positive finite number")
        if prop_type in _SUPPORTED_PROPERTY_TYPES and prop_type not in PROPERTY_TOL_DIMENSION:
            raise ValueError(f"{where}: '{key}' is not supported for type {prop_type!r}")
        if key == "rel_tol" and PROPERTY_TOL_DIMENSION.get(prop_type) == 0:
            raise ValueError(
                f"{where}: 'rel_tol' does not apply to {prop_type!r} (an angle, a fraction "
                "or a required margin does not scale with the figure); use 'tol'"
            )
        out[key] = float(value)
    return out


# Structural check types and what each one counts. polygon_count counts
# authored 2D plane polygons only (prisms never count); solid_count counts
# authored solids (e.g. rectangular_prism). Each maps to an optional
# ``validate_args(args, where)`` run at load time; the evaluators live in
# evals/run.py (_STRUCTURAL_EVALUATORS), and tests/test_eval_check_types.py
# fails if the two sides drift. Add a type with register_structural_type.
_STRUCTURAL_ARG_VALIDATORS: dict[str, Callable[[dict, str], None] | None] = {}


def register_structural_type(
    name: str, validate_args: Callable[[dict, str], None] | None = None
) -> None:
    """Make ``name`` a loadable structural check type. ``validate_args(args,
    where)`` raises ValueError for malformed args (optional)."""
    _STRUCTURAL_ARG_VALIDATORS[name] = validate_args


def register_property_type(name: str) -> None:
    """Make ``name`` a loadable expected_properties type (its evaluator must be
    added to evals/sympy_checks.py by hand; see the note above)."""
    _SUPPORTED_PROPERTY_TYPES.add(name)


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


def _is_name(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _distinct_names(items: Any, count: int | None, where: str, what: str) -> None:
    if not isinstance(items, list) or not all(_is_name(i) for i in items):
        raise ValueError(f"{where}: {what} must be a list of point names, got {items!r}")
    if (count is not None and len(items) != count) or len(set(items)) != len(items):
        need = f"{count} " if count is not None else ""
        raise ValueError(f"{where}: {what} must be {need}distinct points, got {items!r}")


def _validate_angle_args(args: list, where: str) -> None:
    """right_angle [a, o, b]; angle_value [a, o, b, degrees]: three distinct points."""
    _distinct_names(args[:3], 3, where, "the angle's points [a, o, b]")


def _validate_angle_pair_args(args: list, where: str) -> None:
    """angle_equal [[a1, o1, b1], [a2, o2, b2]]: two angles of three distinct points each
    (an angle named by a number, "angle 1", is not a point triple)."""
    if len(args) != 2:
        raise ValueError(f"{where}: needs two angles [[a, o, b], [a, o, b]], got {len(args)} argument(s)")
    for triple in args:
        _distinct_names(triple, 3, where, "an angle [a, o, b]")


def _validate_segment_args(args: list, where: str) -> None:
    """equal_lengths / parallel / perpendicular [[p, q], ...]: segments of two distinct points."""
    if not args or not all(isinstance(seg, list) for seg in args):
        raise ValueError(f"{where}: needs a list of segments [[p, q], ...], got {args!r}")
    for seg in args:
        _distinct_names(seg, 2, where, "a segment [p, q]")


def _validate_distinct_points_args(count: int | None, minimum: int = 0):
    def validate(args: list, where: str) -> None:
        _distinct_names(args[:count] if count else args, count, where, "the points")
        if len(args) < minimum:
            raise ValueError(f"{where}: needs at least {minimum} points, got {len(args)}")
    return validate


for _ptype, _validator in (
    ("right_angle", _validate_angle_args),
    ("angle_value", _validate_angle_args),
    ("angle_equal", _validate_angle_pair_args),
    ("equal_lengths", _validate_segment_args),
    ("parallel", _validate_segment_args),
    ("perpendicular", _validate_segment_args),
    ("collinear", _validate_distinct_points_args(None, 3)),
    ("midpoint", _validate_distinct_points_args(3)),
):
    _PROPERTY_ARG_VALIDATORS[_ptype] = _validator

register_structural_type("polygon_count")
register_structural_type("solid_count", _validate_solid_count_args)
for _ptype, _validator in (
    ("stack_cube_count", _validate_stack_cube_count_args),
    ("stack_extents", _validate_stack_extents_args),
    ("stack_is_height_map", _validate_stack_is_height_map_args),
):
    _PROPERTY_ARG_VALIDATORS[_ptype] = _validator


def _note_unsupported_check_type(kind: str, name: str, where: str, strict: bool, seen: set) -> None:
    """A check ``type`` this build does not know (e.g. one added on another
    branch): an error when ``strict``, else one warning per distinct type. The
    check still loads, marked ``unsupported``, and runs as skipped."""
    if strict:
        raise ValueError(f"{where}: unsupported {kind} 'type'={name!r}")
    if (kind, name) not in seen:
        seen.add((kind, name))
        logger.warning(
            "%s: unknown %s type %r; it will be skipped (not counted as passed or failed)",
            where, kind, name,
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


def _validate_scenarios(raw_scenarios: Any, strict: bool = False) -> list[dict[str, Any]]:
    """Validate scenario YAML shape and return normalized list of scenarios.

    A check whose ``type`` is not registered does not fail the file: it loads
    with ``"unsupported": True`` (the runner skips it) and a warning is logged.
    ``strict`` makes it a ValueError instead."""
    unknown_seen: set[tuple[str, str]] = set()
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
            if not isinstance(prop_type, str) or not prop_type.strip():
                raise ValueError(f"{prop_where}: 'type' must be a non-empty string")
            if not isinstance(args, list):
                raise ValueError(f"{prop_where}: 'args' must be a list")
            unsupported = prop_type not in _SUPPORTED_PROPERTY_TYPES
            tolerances = _validate_property_tolerances(prop, prop_type, prop_where)
            if unsupported:
                _note_unsupported_check_type("property", prop_type, prop_where, strict, unknown_seen)
            elif prop_type in _PROPERTY_ARG_VALIDATORS:
                _PROPERTY_ARG_VALIDATORS[prop_type](args, prop_where)

            normalized_props.append(
                {
                    "name": name,
                    "type": prop_type,
                    "args": args,
                    **tolerances,
                    **({"unsupported": True} if unsupported else {}),
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

        # forbidden_labels
        forbidden_labels = raw.get("forbidden_labels", [])
        if forbidden_labels is None:
            forbidden_labels = []
        if not isinstance(forbidden_labels, list):
            raise ValueError(
                f"{where} ({scenario_id}): 'forbidden_labels' must be a list when provided"
            )
        for i, label in enumerate(forbidden_labels, start=1):
            if not isinstance(label, str) or not label.strip():
                raise ValueError(
                    f"{where} ({scenario_id}) forbidden_labels[{i}]: must be a non-empty string"
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
            if not isinstance(sc_type, str) or not sc_type.strip():
                raise ValueError(f"{sc_where}: 'type' must be a non-empty string")
            if not isinstance(sc_args, dict):
                raise ValueError(f"{sc_where}: 'args' must be an object")
            sc_unsupported = sc_type not in _STRUCTURAL_ARG_VALIDATORS
            if sc_unsupported:
                _note_unsupported_check_type("structural", sc_type, sc_where, strict, unknown_seen)
            elif _STRUCTURAL_ARG_VALIDATORS[sc_type] is not None:
                _STRUCTURAL_ARG_VALIDATORS[sc_type](sc_args, sc_where)
            normalized_structural.append({
                "name": sc_name, "type": sc_type, "args": sc_args,
                **({"unsupported": True} if sc_unsupported else {}),
            })

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
                "forbidden_labels": list(forbidden_labels),
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


def load_scenarios(path: str, strict: bool = False) -> list[dict]:
    """Load and validate scenarios from a YAML file path (``strict``: an
    unregistered check type is an error, see ``_validate_scenarios``)."""
    import yaml
    from pathlib import Path
    with Path(path).open() as f:
        raw = yaml.safe_load(f)
    return _validate_scenarios(raw, strict=strict)
