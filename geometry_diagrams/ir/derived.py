"""
Derived-entity registry: constructions that own extra entities.

Some definition kinds (PolygonExterior, PolygonOnEdge, CircleTangentAt)
produce more than the one object stored under their own id: they also make
addressable derived entities (polygon vertices, a tangent circle's center)
that later definitions may reference by name. A kind declares that here, in
one place: which derived ids it owns and how it registers them into the
symbol table after compile. The compiler's dependency ordering, post-compile
registration and dependents tracking all consult this registry instead of
per-kind branches.

A kind may also *synthesize* ordinary definitions (e.g. a solid's edge
segments and face polygons). Those are never written into the authored IR:
``effective_defs`` computes the view "authored definitions plus synthesized
ones" as a pure function of the authored definitions, and only the consumers
that need the derived geometry read it (compile, both renderers, bounds and
helpers, linear-pair resolution, the entity manifest). Consumers that must see
only what was authored (auto-checks, edit and eval IR diagnostics, dependents
tracking) keep reading ``diagram.define``; dependents tracking still reaches
synthesized ids through ``owner_map``, which attributes them to their owner.

Extension points for later hooks (render lowering, feature group) are further
fields on ``DerivedConstruction``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import sympy.geometry as spg

from . import ir


@dataclass(frozen=True)
class DerivedConstruction:
    """How one definition kind declares and registers its derived entities.

    kind: the DefStmt ``kind`` discriminator this entry applies to.
    id_forms: templates describing the synthesized id shapes the kind may
        produce (e.g. ``"{id}_v{i}"``). Two kinds may not claim the same form.
    owned_ids: the derived ids this statement owns, regardless of whether a
        real definition of the same name exists (callers filter those out).
        Used for dependency ordering and dependents tracking.
    register: after the statement compiles to ``obj``, add its derived
        entities to ``sym``. Never overwrites a name already in ``sym``.
    """

    kind: str
    id_forms: tuple[str, ...]
    owned_ids: Callable[[Any], list[str]]
    register: Callable[[Any, Any, dict[str, Any]], None]
    # Optional hooks (None = the kind does not participate):
    # position: compiled object -> (x, y), or None when the object is not one
    #     this kind produced. Used for label centroids, the entity manifest
    #     and edit diagnostics; lets a registered object that is not a SymPy
    #     shape (so has no .vertices) supply its own representative point.
    position: Callable[[Any], "tuple[float, float] | None"] | None = None
    # vertex_ids: ordered vertex point ids of the polygon the statement makes.
    vertex_ids: Callable[[Any], list[str]] | None = None
    # center_id: id of the named center point of the circle the statement makes.
    center_id: Callable[[Any], str] | None = None
    # synthesize: statement -> the ordinary definitions it contributes to the
    #     effective definition set (never to the authored IR). Must be a pure
    #     function of the statement alone: compile and render each recompute
    #     the view independently and must agree. Synthesized ids count as
    #     owned (see owner_map); a synthesized definition is not itself
    #     expanded further (one level).
    synthesize: Callable[[Any], list[Any]] | None = None


class DerivedRegistry:
    def __init__(self) -> None:
        self._by_kind: dict[str, DerivedConstruction] = {}
        self._form_owner: dict[str, str] = {}

    def register(self, construction: DerivedConstruction) -> None:
        if construction.kind in self._by_kind:
            raise ValueError(f"derived construction for kind {construction.kind!r} already registered")
        for form in construction.id_forms:
            other = self._form_owner.get(form)
            if other is not None:
                raise ValueError(
                    f"derived id form {form!r} claimed by both {other!r} and {construction.kind!r}"
                )
        self._by_kind[construction.kind] = construction
        for form in construction.id_forms:
            self._form_owner[form] = construction.kind

    def get(self, stmt: Any) -> DerivedConstruction | None:
        return self._by_kind.get(getattr(stmt, "kind", None))

    def owner_map(self, stmts: list[Any]) -> dict[str, str]:
        """derived id -> id of the owning statement, covering both owned ids
        and the ids of synthesized definitions. Derived names that are also
        real definitions in ``stmts`` are skipped (the real definition wins),
        so over the effective view synthesized ids resolve to themselves."""
        real_ids = {s.id for s in stmts}
        owners: dict[str, str] = {}
        for stmt in stmts:
            entry = self.get(stmt)
            if entry is None:
                continue
            for did in entry.owned_ids(stmt):
                if did not in real_ids:
                    owners[did] = stmt.id
            for synth in self.synthesized(stmt):
                if synth.id not in real_ids:
                    owners[synth.id] = stmt.id
        return owners

    def synthesized(self, stmt: Any) -> list[Any]:
        """The definitions ``stmt``'s kind synthesizes (empty for most kinds)."""
        entry = self.get(stmt)
        if entry is None or entry.synthesize is None:
            return []
        return list(entry.synthesize(stmt))

    def effective_defs(self, stmts: list[Any]) -> list[Any]:
        """Authored statements, each followed by the definitions its kind
        synthesizes. A synthesized definition whose id is already taken (by
        an authored definition or an earlier synthesized one) is dropped:
        the authored definition wins, as in ``owner_map`` and ``register``.
        Always a new list; ``stmts`` is never modified. Idempotent."""
        taken = {s.id for s in stmts}
        view: list[Any] = []
        for stmt in stmts:
            view.append(stmt)
            for synth in self.synthesized(stmt):
                if synth.id not in taken:
                    taken.add(synth.id)
                    view.append(synth)
        return view

    def position_of(self, obj: Any) -> "tuple[float, float] | None":
        """Position supplied by the first registered kind that recognizes
        ``obj``; None when no kind claims it."""
        for entry in self._by_kind.values():
            if entry.position is not None:
                pos = entry.position(obj)
                if pos is not None:
                    return pos
        return None

    def vertex_ids(self, stmt: Any) -> list[str] | None:
        entry = self.get(stmt)
        if entry is None or entry.vertex_ids is None:
            return None
        return entry.vertex_ids(stmt)

    def center_id(self, stmt: Any) -> str | None:
        entry = self.get(stmt)
        if entry is None or entry.center_id is None:
            return None
        return entry.center_id(stmt)

    def register_derived(self, stmt: Any, obj: Any, sym: dict[str, Any]) -> None:
        entry = self.get(stmt)
        if entry is not None:
            entry.register(stmt, obj, sym)


# --- the three existing constructions --------------------------------------

def _exterior_names(stmt: ir.PolygonExterior) -> list[str]:
    return stmt.vertex_names or [f"{stmt.id}_v{i}" for i in range(stmt.sides)]


def _exterior_owned(stmt: ir.PolygonExterior) -> list[str]:
    # Base vertices (names[0], names[1]) are inputs from a prior statement;
    # owning them would overwrite the parent polygon's ownership.
    return _exterior_names(stmt)[2:]


def _exterior_register(stmt: ir.PolygonExterior, obj: Any, sym: dict[str, Any]) -> None:
    if not isinstance(obj, spg.Polygon):
        return
    names = _exterior_names(stmt)
    for i, vertex in enumerate(obj.vertices):
        sub_id = names[i] if i < len(names) else f"{stmt.id}_v{i}"
        if sub_id not in sym:
            sym[sub_id] = vertex


def _exterior_vertex_ids(stmt: ir.PolygonExterior) -> list[str]:
    # Drawing addresses the base vertices by their input ids (a, b), not by
    # the aliases registered for them.
    if stmt.vertex_names:
        return list(stmt.vertex_names)
    return [stmt.a, stmt.b, *_exterior_names(stmt)[2:]]


def _on_edge_owned(stmt: ir.PolygonOnEdge) -> list[str]:
    return list(stmt.vertex_names[2:])


def _on_edge_register(stmt: ir.PolygonOnEdge, obj: Any, sym: dict[str, Any]) -> None:
    if not isinstance(obj, spg.Polygon):
        return
    for i, vname in enumerate(stmt.vertex_names):
        if vname not in sym:
            sym[vname] = obj.vertices[i]


def _tangent_owned(stmt: ir.CircleTangentAt) -> list[str]:
    return [ir.tangent_circle_center_id(stmt.id)]


def _tangent_owned_center(stmt: ir.CircleTangentAt) -> str:
    return ir.tangent_circle_center_id(stmt.id)


def _tangent_register(stmt: ir.CircleTangentAt, obj: Any, sym: dict[str, Any]) -> None:
    if not isinstance(obj, spg.Circle):
        return
    center_id = ir.tangent_circle_center_id(stmt.id)
    if center_id not in sym:
        sym[center_id] = obj.center


def _build_default_registry() -> DerivedRegistry:
    reg = DerivedRegistry()
    reg.register(DerivedConstruction(
        "polygon_exterior", ("{id}_v{i}",), _exterior_owned, _exterior_register,
        vertex_ids=_exterior_vertex_ids,
    ))
    reg.register(DerivedConstruction("polygon_on_edge", (), _on_edge_owned, _on_edge_register))
    reg.register(DerivedConstruction(
        "circle_tangent_at", ("{id}_center",), _tangent_owned, _tangent_register,
        center_id=_tangent_owned_center,
    ))
    return reg


REGISTRY = _build_default_registry()


def effective_defs(diagram: Any) -> list[Any]:
    """The effective definition set of ``diagram``: its authored definitions
    plus every definition a registered kind synthesizes. A pure function of
    ``diagram.define`` alone (never of a symbol table or a random stream)."""
    return REGISTRY.effective_defs(diagram.define)


def effective_diagram(diagram: Any) -> Any:
    """``diagram`` itself when nothing is synthesized, else a shallow copy
    whose ``define`` is the effective view. The copy is local to the caller
    (a renderer's entry function); the authored IR is never rewritten."""
    view = effective_defs(diagram)
    if len(view) == len(diagram.define):
        return diagram
    return diagram.model_copy(update={"define": view})
