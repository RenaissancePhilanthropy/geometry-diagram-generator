"""SymPy-based geometric property validation for eval scenarios.

Used to verify expected_properties from scenario YAML against the compiled
float-coordinate symbol table produced by the structured strategy.
"""
from __future__ import annotations

from evals import check_types
from evals.property_names import NameResolutionError, NameResolver


# Prism property types resolve through query_prism on the FULL compiled symbol
# table (the Prism object), never on the 2D projected float coordinates.
PRISM_PROPERTY_TYPES = check_types.property_type_names("prism")

# Stack property types resolve through query_stack on the full symbol table,
# on their own path (never the prism validator).
STACK_PROPERTY_TYPES = check_types.property_type_names("stack")


def _ids_answering(sym_full: dict, query_type: str) -> list[str]:
    """Ids of the objects the registered kind answering ``query_type``
    ("prism", "stack") compiled (the derived registry's object_type)."""
    from geometry_diagrams.ir.derived import REGISTRY

    out = []
    for k, v in sym_full.items():
        entry = REGISTRY.entry_for_object(v)
        if entry is not None and entry.query_type == query_type:
            out.append(k)
    return out


def _validate_prism_properties(expected_properties: list[dict], sym_full: dict) -> list[dict]:
    """Evaluate the prism-typed expected_properties against the full compiled
    symbol table. Returns list of {name, type, passed, message} dicts.

    prism_volume:     args [prism_id, expected_volume]
    prism_dimensions: args [prism_id, length, width, height]
    prism_id "*" means any prism in the diagram (the model picks the id).
    Comparison is near-exact (the volume_equals check's tolerance): prism
    dimensions are exact, so an off-by-one dimension fails.
    """
    from geometry_diagrams.ir.checks import _near_exact
    from geometry_diagrams.ir.queries import query_prism

    def measures(prop_type: str, q: dict, args: list) -> tuple[bool, str]:
        if prop_type == "prism_volume":
            expected = args[1]
            ok = _near_exact(q["volume"], expected, None)
            return ok, "" if ok else f"volume {q['volume']:.10g} != expected {expected:.10g}"
        got = (q["length"], q["width"], q["height"])
        want = tuple(args[1:4])
        ok = len(want) == 3 and all(_near_exact(g, w, None) for g, w in zip(got, want))
        return ok, "" if ok else f"(length, width, height) {got} != expected {want}"

    results = []
    for prop in expected_properties:
        ptype = prop.get("type", "")
        if ptype not in PRISM_PROPERTY_TYPES:
            continue
        args = prop.get("args", [])
        try:
            prism_id = args[0]
            if prism_id == "*":
                ids = _ids_answering(sym_full, "prism")
                if not ids:
                    raise KeyError("no prism in the diagram")
            else:
                ids = [prism_id]
            outcomes = [measures(ptype, query_prism(sym_full, i), args) for i in ids]
            passed = any(ok for ok, _ in outcomes)
            msg = "" if passed else "; ".join(m for _, m in outcomes)
        except Exception as exc:
            passed, msg = False, f"Error: {exc}"
        results.append({"name": prop.get("name", ""), "type": ptype, "passed": passed, "message": msg})
    return results


def _validate_stack_properties(expected_properties: list[dict], sym_full: dict) -> list[dict]:
    """Evaluate the stack-typed expected_properties against the full compiled
    symbol table. Returns list of {name, type, passed, message} dicts.

    stack_cube_count: args [stack_id, expected_count]; stack_id "*" means any
    stack in the diagram. Integer equality (the cube_count_equals semantics).
    stack_extents: args [stack_id, length, width, height] (integer equality on
    the stack's x/z/y extents). stack_is_height_map: args [stack_id, bool].
    "*" is any-match for all three.
    """
    from geometry_diagrams.ir.queries import query_stack

    results = []
    for prop in expected_properties:
        ptype = prop.get("type", "")
        if ptype not in STACK_PROPERTY_TYPES:
            continue
        args = prop.get("args", [])
        try:
            stack_id = args[0]
            if stack_id == "*":
                ids = _ids_answering(sym_full, "stack")
                if not ids:
                    raise KeyError("no stack in the diagram")
            else:
                ids = [stack_id]
            queries = [query_stack(sym_full, i) for i in ids]
            if ptype == "stack_cube_count":
                actual = [q["cube_count"] for q in queries]
                want, label = args[1], "cube count"
            elif ptype == "stack_extents":
                actual = [(q["length"], q["width"], q["height"]) for q in queries]
                want, label = tuple(args[1:4]), "(length, width, height)"
            else:
                actual = [q["is_height_map"] for q in queries]
                want, label = args[1], "is_height_map"
            passed = any(a == want for a in actual)
            msg = "" if passed else (
                f"{label} {', '.join(str(a) for a in actual)} != expected {want}"
            )
        except Exception as exc:
            passed, msg = False, f"Error: {exc}"
        results.append({"name": prop.get("name", ""), "type": ptype, "passed": passed, "message": msg})
    return results


def _figure_scale(sym_float: dict) -> float:
    """The figure's length scale: the diagonal of the bounding box of its
    points (1.0 when there are fewer than two distinct ones)."""
    import math
    pts = [p for p in sym_float.values() if isinstance(p, tuple) and len(p) == 2]
    if len(pts) < 2:
        return 1.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0


def property_tolerance(prop: dict, default: float, scale: float) -> float:
    """The tolerance for one expected property, in its check's own units.

    ``tol`` is absolute, ``rel_tol`` a fraction of the figure's size
    (``rel_tol * scale ** dimension``, see evals/check_types.py); with both
    the larger wins (like ``math.isclose``), with neither it is ``default``."""
    tol, rel_tol = prop.get("tol"), prop.get("rel_tol")
    if tol is None and rel_tol is None:
        return default
    candidates = [tol or 0.0]
    if rel_tol is not None:
        dimension = check_types.tolerance_dimension(prop.get("type"))
        candidates.append(rel_tol * scale ** (1 if dimension is None else dimension))
    return max(candidates)


def _validate_properties_sympy(
    expected_properties: list[dict],
    sym_float: dict,
    tol: float = 5e-3,
    resolver: NameResolver | None = None,
) -> list[dict]:
    """Validate scenario expected_properties against a float-coords symbol table.
    sym_float maps point_id -> (x, y) float tuples. ``tol`` is the default
    tolerance; a property's own ``tol``/``rel_tol`` override it. With a
    ``resolver`` the scenario's point names are resolved to ids first (see
    evals/property_names.py); a name it cannot resolve fails the property with
    ``resolution`` set to ``"unresolved"``/``"ambiguous"``, kept apart from a
    geometry failure.
    Returns list of {name, type, passed, message} dicts (plus ``tol``, the
    tolerance used, when the property set its own, and ``resolved_names``, the
    names that needed resolving).
    """
    results = []
    scale = _figure_scale(sym_float)
    for prop in expected_properties:
        if prop.get("type") in PRISM_PROPERTY_TYPES | STACK_PROPERTY_TYPES:
            continue  # evaluated on the full symbol table by the prism/stack validators
        name = prop.get("name", "")
        ptype = prop.get("type", "")
        args = prop.get("args", [])
        used = tol
        resolution = None
        if resolver is not None:
            resolver.resolved = {}
        try:
            used = property_tolerance(prop, tol, scale)
            if resolver is not None and check_types.tolerance_dimension(ptype) is not None:
                args = resolver.resolve_args(args)  # geometry types only: others take text args
            passed, msg = _check_sympy_property(ptype, args, sym_float, used)
        except NameResolutionError as exc:
            passed, msg, resolution = False, f"Error: {exc}", exc.kind
        except Exception as exc:
            passed, msg = False, f"Error: {exc}"
        result = {"name": name, "type": ptype, "passed": passed, "message": msg}
        if resolution is not None:
            result["resolution"] = resolution
        if resolver is not None and resolver.resolved:
            result["resolved_names"] = dict(resolver.resolved)
            if passed is False:  # the message names ids, not the scenario's names
                result["message"] += " [names: " + ", ".join(f"{k} -> {v}" for k, v in resolver.resolved.items()) + "]"
        if used != tol:
            result["tol"] = used
        results.append(result)
    return results


def _check_sympy_property(ptype: str, args: list, sym_float: dict, tol: float) -> tuple[bool | None, str]:
    """Evaluate one geometry or rendering-only property through the check-type registry
    (evals/check_types.py). A type that is not registered, or that is evaluated elsewhere
    (prism, stack), is skipped: ``(None, message)``, never a pass."""
    known = check_types.property_type(ptype)
    if known is None or known.evaluate is None:
        return None, f"(skipped: unsupported type {ptype!r})"
    if known.family == "render":
        return known.evaluate(args, None)
    return known.evaluate(args, check_types.GeometryContext(sym_float, tol))
