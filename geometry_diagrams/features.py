"""Feature groups: opt-in sets of generation-time capabilities.

A feature group (e.g. ``solids``) is OFF unless named in the enabled set
carried on ``GeometryConfig.features`` (environment variable
``GEOMETRY_FEATURES``, comma-separated). The set gates *generation surfaces*
only -- what a model is told about and allowed to produce:

* prompt fragments tagged with a group (``tagged_fragment``),
* names added to the sandboxed scripting namespace (``pydsl.GROUPED_NAMES``),
* an IR diagram that uses a kind belonging to a disabled group is rejected
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

from typing import Any, Iterable

# Registered groups. A group is added here and tagged onto registry kinds
# (``DerivedConstruction.feature``), prompt fragments and grouped names.
FEATURE_GROUPS: frozenset[str] = frozenset({"solids"})


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


def require_features(diagram: Any, enabled: "frozenset[str] | set[str]") -> None:
    """Reject ``diagram`` if it uses a kind from a feature group that is not
    in ``enabled``. The one post-parse gate, run at generation surfaces only
    (never in compile or render). Raises FeatureNotEnabledError naming the
    first offending kind, its definition id, its group and how to enable it."""
    from .ir.derived import REGISTRY

    for stmt in getattr(diagram, "define", None) or []:
        entry = REGISTRY.get(stmt)
        if entry is None or entry.feature is None or entry.feature in enabled:
            continue
        raise FeatureNotEnabledError(
            f"Definition {getattr(stmt, 'id', '?')!r} uses kind {entry.kind!r}, which belongs "
            f"to the {entry.feature!r} feature group; that group is not enabled. Do not use "
            f"{entry.kind!r}: build the diagram without it. (To allow it, enable the group "
            f"with GEOMETRY_FEATURES={entry.feature} or GeometryConfig(features="
            f"frozenset({{{entry.feature!r}}})).)"
        )
