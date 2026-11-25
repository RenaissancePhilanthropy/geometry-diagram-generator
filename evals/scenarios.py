"""Scenario YAML loading and validation for eval runner."""
from __future__ import annotations

import logging
from typing import Any

from evals import check_types as _check_types
from geometry_diagrams.features import parse_features

logger = logging.getLogger(__name__)

# The check types (property and structural), their argument validators, tolerance
# dimensions and evaluators are one registry: evals/check_types.py. A type nobody
# registered loads as ``unsupported`` and runs as skipped (``strict`` makes it an error).
register_property_type = _check_types.register_property_type
register_structural_type = _check_types.register_structural_type


def _validate_property_tolerances(prop: dict, prop_type: str, where: str) -> dict[str, float]:
    """The optional ``tol`` (absolute, in the check's units; radians for an angle
    check) and ``rel_tol`` (a fraction of the figure's size) of one property:
    positive finite numbers, ``rel_tol`` only where the compared quantity
    scales with the figure (see evals/check_types.py). Returns just the fields
    that were given."""
    import math
    known = _check_types.property_type(prop_type)
    out: dict[str, float] = {}
    for key in ("tol", "rel_tol"):
        if key not in prop:
            continue
        value = prop[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) \
                or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{where}: '{key}' must be a positive finite number")
        if known is not None and known.family != "geometry":
            raise ValueError(f"{where}: '{key}' is not supported for type {prop_type!r}")
        if key == "rel_tol" and _check_types.tolerance_dimension(prop_type) == 0:
            raise ValueError(
                f"{where}: 'rel_tol' does not apply to {prop_type!r} (an angle, a fraction "
                "or a required margin does not scale with the figure); use 'tol'"
            )
        out[key] = float(value)
    return out


_CANVAS_FEATURES = {"grid", "axes"}

# Default tolerance for expected_points coordinate matching
_DEFAULT_POINT_TOLERANCE = 1e-4


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


def count_unsupported_checks(scenarios: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    """(kind, type) -> how many checks of that unsupported type the scenarios carry
    (kind is ``property`` or ``structural``): the checks that will run as skipped."""
    counts: dict[tuple[str, str], int] = {}
    for sc in scenarios:
        for kind, key in (("property", "expected_properties"), ("structural", "structural_checks")):
            for check in sc.get(key) or []:
                if check.get("unsupported"):
                    counts[(kind, check["type"])] = counts.get((kind, check["type"]), 0) + 1
    return counts


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
            known_property = _check_types.property_type(prop_type)
            unsupported = known_property is None
            tolerances = _validate_property_tolerances(prop, prop_type, prop_where)
            if unsupported:
                _note_unsupported_check_type("property", prop_type, prop_where, strict, unknown_seen)
            elif known_property.validate_args is not None:
                known_property.validate_args(args, prop_where)

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
            known_structural = _check_types.structural_type(sc_type)
            sc_unsupported = known_structural is None
            if sc_unsupported:
                _note_unsupported_check_type("structural", sc_type, sc_where, strict, unknown_seen)
            elif known_structural.validate_args is not None:
                known_structural.validate_args(sc_args, sc_where)
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
