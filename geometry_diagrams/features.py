"""Feature groups: opt-in sets of generation-time capabilities.

A feature group (e.g. ``solids``) is OFF unless named in the enabled set
carried on ``GeometryConfig.features`` (environment variable
``GEOMETRY_FEATURES``, comma-separated). The set gates *generation surfaces*
only -- what a model is told about and allowed to produce:

* prompt fragments tagged with a group (``tagged_fragment``),
* names added to the sandboxed scripting namespace (``pydsl.GROUPED_NAMES``),
* an IR diagram that uses a kind belonging to a disabled group, or sets a
  field a group owns on an ungated kind (``FIELD_RULES``: a nonzero
  ``rotation_deg`` on an ellipse belongs to ``tilted_ellipses``), is rejected
  after parsing (``require_features``), with an error the retry loops feed
  back to the model.

CONTRACT: any strategy that produces a DiagramIR must call
``require_features(diagram, self.features)`` after parsing/lowering and before
the shared pipeline (``run_ir_pipeline``), reusing its existing retry-error
path; ``tests/test_feature_gating.py`` has a parametrized regression test over
the IR-producing strategies. It never gates compilation or rendering: every registered kind always
compiles and renders, so stored diagrams stay portable regardless of the
setting. The structured and recipe strategies expose static schemas
(``DiagramIR`` / the recipe DSL) that cannot be filtered per request, so the
kind stays visible to those models even with its group off; the
``require_features`` rejection is the gate for both.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

# Registered groups. A group is added here and tagged onto registry kinds
# (``DerivedConstruction.feature``), field rules (``FIELD_RULES``), prompt
# fragments and grouped names.
FEATURE_GROUPS: frozenset[str] = frozenset({"solids", "tilted_ellipses"})


def _tilted_rotation(stmt: Any) -> "str | None":
    """``"rotation_deg"`` when the statement's rotation is not a literal 0.
    A string expression counts as tilted unless it is exactly ``"0"``: this
    runs before compile, so it cannot evaluate the expression."""
    value = getattr(stmt, "rotation_deg", 0)
    if isinstance(value, str):
        return None if value == "0" else "rotation_deg"
    return None if value == 0 else "rotation_deg"


# Field-level rules for kinds that are not gated as a whole (ellipses are not
# registry kinds): kind -> (predicate returning the offending field name or
# None, group). Consulted by ``require_features`` next to the registry.
FIELD_RULES: "dict[str, tuple[Callable[[Any], str | None], str]]" = {
    "ellipse_center_axes": (_tilted_rotation, "tilted_ellipses"),
    "ellipse_center_eccentricity": (_tilted_rotation, "tilted_ellipses"),
}


class FeatureNotEnabledError(RuntimeError):
    """A generated diagram uses a kind from a feature group that is not
    enabled. A RuntimeError so every strategy's existing retry path feeds
    the message back to the model."""


def parse_features(value: "str | Iterable[str] | None") -> frozenset[str]:
    """Normalize a comma-separated string (or iterable) of group names into a
    frozenset. Blank entries are ignored; unknown names raise ValueError."""
    if value is None:
        return frozenset()
    items = value.split(",") if isinstance(value, str) else list(value)
    names = frozenset(s.strip() for s in items if s and s.strip())
    unknown = sorted(names - FEATURE_GROUPS)
    if unknown:
        raise ValueError(
            f"unknown feature group(s) {unknown}; registered groups: {sorted(FEATURE_GROUPS)}"
        )
    return names


def tagged_fragment(group: str, text: str, enabled: "frozenset[str] | set[str]") -> str:
    """``text`` when ``group`` is enabled, else the empty string. Use to tag a
    prompt fragment by group when assembling a prompt."""
    return text if group in enabled else ""


def tagged_insertions(
    group: str,
    text: str,
    insertions: "Iterable[tuple[str, str]]",
    enabled: "frozenset[str] | set[str]",
) -> str:
    """``text`` unchanged when ``group`` is off; when on, each ``(anchor,
    lines)`` inserts ``lines`` right after the first line of ``text``
    containing ``anchor``, in order. For gating parts of an existing text
    (e.g. a tool description) so it stays byte-identical with the group off.
    A missing anchor raises ValueError whether or not the group is on, so an
    edit to the base text cannot silently drop a gated insertion."""
    out = text.split("\n")
    for anchor, lines in insertions:
        at = next((i for i, line in enumerate(out) if anchor in line), None)
        if at is None:
            raise ValueError(f"tagged_insertions: anchor {anchor!r} not found")
        if group in enabled:
            out[at + 1:at + 1] = lines.split("\n")
    return "\n".join(out)


def require_features(diagram: Any, enabled: "frozenset[str] | set[str]") -> None:
    """Reject ``diagram`` if it uses a kind, or a field (``FIELD_RULES``),
    from a feature group that is not in ``enabled``. The one post-parse gate,
    run at generation surfaces only (never in compile or render). Raises
    FeatureNotEnabledError naming the first offending kind or field, its
    definition id, its group and how to enable it."""
    from .ir.derived import REGISTRY

    for stmt in getattr(diagram, "define", None) or []:
        sid = getattr(stmt, "id", "?")
        entry = REGISTRY.get(stmt)
        if entry is not None and entry.feature is not None and entry.feature not in enabled:
            raise FeatureNotEnabledError(
                f"Definition {sid!r} uses kind {entry.kind!r}, which belongs "
                f"to the {entry.feature!r} feature group; that group is not enabled. Do not use "
                f"{entry.kind!r}: build the diagram without it. {_how_to_enable(entry.feature)}"
            )
        rule = FIELD_RULES.get(getattr(stmt, "kind", None))
        if rule is None or rule[1] in enabled:
            continue
        field = rule[0](stmt)
        if field is not None:
            raise FeatureNotEnabledError(
                f"Definition {sid!r} ({stmt.kind}) sets {field}={getattr(stmt, field)!r}, which "
                f"belongs to the {rule[1]!r} feature group; that group is not enabled. Leave "
                f"{field} at 0 (an axis-aligned ellipse). {_how_to_enable(rule[1])}"
            )


def _how_to_enable(group: str) -> str:
    return (
        f"(To allow it, enable the group with GEOMETRY_FEATURES={group} or "
        f"GeometryConfig(features=frozenset({{{group!r}}})).)"
    )
