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

A kind may also *lower* a draw of its id (``lower_draw``): ``lower_render``
is the lowering point both renderers' entry functions (``ir_to_svg``,
``ir_to_tikz``) call right after computing the effective view. It replaces
each such draw, in place, by the ordered render operations the hook returns.
Before lowering it rejects render operations that name a kind's id where it
cannot work (``render_ref_error``; compile_defs runs the same check) and
collects the kinds' non-fatal ``render_warnings``.

The full hook set (fields of ``DerivedConstruction``; all but the first four
optional) and who consumes each:

- ``kind``, ``id_forms``, ``owned_ids``, ``register``: dependency ordering,
  dependents tracking and post-compile registration (to_sympy, refs).
- ``position``: label centroids, the entity manifest, edit diagnostics
  (render_util); also derives pydsl's ``label_text(centroid_of=...)``
  acceptance of a handle (``has_position``).
- ``vertex_ids``, ``center_id``: drawing a constructed polygon / naming a
  tangent circle's center (renderers, recipe lowering).
- ``synthesize``: the effective definition view (compile, renderers).
- ``lower_draw``, ``render_ref_error``, ``render_warnings``: the render
  lowering point (``lower_render``) and compile's render-ref check.
- ``lower_labels``: the render lowering point too: once per DRAWN authored
  statement of the kind (``drawn_ids``: the overlap advisory's rule),
  ``lower_render`` appends the label operations the hook returns (a prism's
  dimension and base-area label fields). It does not replace ``lower_draw``,
  which still lowers each draw of the kind's own id; it exists because a
  kind's own labels must appear exactly once however the solid is drawn
  (through its id, only through its faces, or drawn twice), and need the
  compiled object, which ``lower_draw`` never sees.
- ``exclusive``: owned-id uniqueness (``check_exclusive_ids``).
- ``feature``: the generation-surface gate (features.require_features).
- ``index``: every compiled statement, e.g. a prism's corner-segment index.

Solid hooks, for a kind whose compiled object is not a SymPy shape (today
``rectangular_prism`` and ``block_stack``):

- ``compile``: to_sympy's single-statement compiler, before its own dispatch.
- ``object_type``: recognizes the compiled object (``entry_for_object``):
  the query type check, ``trusted_faces``, evals' "any solid" ids.
- ``query_type`` + ``query``: the agent query tools' dispatch
  (``structured.dispatch_query`` via ``queries.query_registered``).
- ``true_length``: the extra ``true_length`` of the ``length`` query.
- ``evaluate_checks``: check kinds the kind owns (``volume_equals``,
  ``true_length_equals``, ``cube_count_equals``), evaluated by run_checks.
- ``check_warnings``: run_checks' warnings collector (a prism's projection
  warning on a generic 2D length check).
- ``label_away_from``: both renderers' segment-label placement (a prism
  dimension label goes on the side away from the prism's center).
- ``pipeline_warnings``: run_ir_pipeline's warnings (a prism dimension label
  contradicting the true length).
- ``canvas_extent``: the recipe lowerer's auto canvas fit (``_Lowerer._add``).
- ``screen_bounds``: a compiled solid's axis-aligned screen box, from its
  projected corners / lattice. ``DerivedRegistry.overlap_warnings`` (the one
  kind-agnostic place, called from ``pipeline_warnings``) compares the boxes
  of every pair of DRAWN authored solids (``drawn_ids``: a ``draw``/``fill``
  render op names the id or one of its faces/edges/top faces) and warns
  once per positively-overlapping pair: solids are not depth sorted, so
  overlapping ones paint in draw order. Touching boxes do not warn.
- ``trusted_faces``: compile builds the kind's synthesized polygons without
  SymPy's validating constructor, and the angle-mark check skips their sides
  (a block stack's hundreds of top faces).

Deliberately left OUT of the registry (each a kind's own authoring surface,
not a consumer of compiled geometry): the IR schema classes and their union
(ir.py: ``RectangularPrism``, ``BlockStack`` and the solid check kinds), the
recipe DSL ops and their lowering (recipe/dsl.py, ``_Lowerer._lower_prism`` /
``_lower_stack``, including a ``segment`` op reusing a prism edge), the pydsl
``prism()``/``stack()`` functions, their handles and the builder's prism-edge
reuse for ``segment()``, the per-kind prompt and DSL documentation text and
the hand-written solids lines of the query-tool descriptions (each strategy
words them in its own layout; they stay byte-identical, see
``structured.QUERY_TOOL_SOLIDS_INSERTIONS``), the eval vocabulary
(``prism_*``/``stack_*`` property types, ``solid_count``) and the pydsl
``assert_volume``/``assert_cube_count``/``assert_true_length`` wrappers.
Adding a new solid kind still means adding those surfaces; the consumers of
compiled geometry above need no edit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import sympy.geometry as spg

from . import ir
from . import prism as _prism
from . import stack as _stack
from .errors import IRCompileError


_VIEW_DUMP_MESSAGE = (
    "lowered and effective diagrams are internal render-time views and cannot "
    "be serialized: dump the authored DiagramIR instead"
)


class RenderTimeDiagram(ir.DiagramIR):
    """A ``DiagramIR`` that is an internal render-time view (the effective
    diagram, or a lowered one that may hold ``ir.OrderedPolygon``), never an
    authored diagram. It exists only to refuse serialization: the view is not
    a valid ``DiagramIR`` document (``OrderedPolygon`` is outside the
    ``RenderOp`` union, and the effective view's ``_synthesized_by`` markers do
    not survive a round-trip). Everything else (attribute access, ``model_copy``)
    behaves like ``DiagramIR``. Built by ``render_view``."""

    def model_dump(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(_VIEW_DUMP_MESSAGE)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(_VIEW_DUMP_MESSAGE)


def render_view(diagram: Any, update: dict[str, Any]) -> Any:
    """A shallow ``RenderTimeDiagram`` copy of ``diagram`` with ``update``
    applied (no validation, like ``model_copy``). A ``diagram``
    that is not a ``DiagramIR`` is rejected: a view of anything else would
    be unguarded."""
    if not isinstance(diagram, ir.DiagramIR):
        raise TypeError(f"render_view needs a DiagramIR, got {type(diagram).__name__}")
    fields = {name: getattr(diagram, name) for name in ir.DiagramIR.model_fields}
    fields.update(update)
    return RenderTimeDiagram.model_construct(
        _fields_set=set(diagram.model_fields_set) | set(update), **fields
    )


@dataclass(frozen=True)
class Lowering:
    """What a ``lower_draw`` hook returns for one draw of its kind's id.

    ops: render operations, IN ORDER, that replace the draw at its position
        in the render list. Any render-operation object is allowed, not only
        today's ``ir.RenderOp`` union; in particular a kind may emit an ordered
        sequence of ``ir.OrderedPolygon`` (opaque fill + own stroke) for block
        stacks. The lowering point passes the sequence through unchanged and in
        order.

        WARNING: ``OrderedPolygon`` is deliberately outside the validated
        ``RenderOp`` union, so a lowered diagram is one of the **internal
        render-time views**: it is built without validation, cannot be
        re-validated (``ordered_polygon`` is not a ``RenderOp`` kind), and
        dumping it emits serialization warnings. Never dump, persist or
        re-validate one: ``lower_render`` returns a ``RenderTimeDiagram`` whose
        ``model_dump`` / ``model_dump_json`` raise ``TypeError``. Dump the
        authored ``DiagramIR`` instead.

        Both renderers sort operations by kind (all fills, then all
        strokes; a stable sort), but ``ordered_polygon`` shares the draw layer,
        so it keeps its list position among draws and marks.
    styles: extra named styles the ops reference (merged into the diagram's
        ``styles`` for the renderer only). Names should be reserved
        (double-underscore); reusing an existing name with a different value
        is an error.
    """

    ops: list[Any]
    styles: dict[str, dict[str, Any]] = field(default_factory=dict)


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
    #     expanded further (one level). Must stay cheap: the view is
    #     recomputed several times per pipeline run (compile, owner map, each
    #     renderer entry, helper synthesis, angle checks, entity manifest).
    synthesize: Callable[[Any], list[Any]] | None = None
    # lower_draw: (statement, the ir.Draw of its id, the diagram's styles) ->
    #     Lowering. Called by lower_render from both renderers' entry
    #     functions. Must be a pure function of its arguments.
    lower_draw: Callable[[Any, Any, dict[str, Any]], Lowering] | None = None
    # lower_labels: (authored statement, its compiled object) -> render
    #     operations (labels) appended once, after every other operation, by
    #     lower_render when the statement is drawn (``drawn_ids``). Must be a
    #     pure function of its arguments; empty when the statement has no
    #     labels to add.
    lower_labels: Callable[[Any, Any], list[Any]] | None = None
    # exclusive: the kind's owned ids must be unique names. An owned id equal
    #     to an authored definition id, or to an id another construction owns,
    #     is a compile error (see check_exclusive_ids) instead of the default
    #     "the real definition wins" -- a silent merge would misplace points.
    exclusive: bool = False
    # feature: the feature group (see geometry_diagrams/features.py) this kind
    #     belongs to, or None for an always-available kind. Consulted only by
    #     the generation-surface gate ``require_features``; compile and render
    #     accept every registered kind whatever the enabled set.
    feature: str | None = None
    # index: (any compiled statement, its object, the symbol table) -> None.
    #     Called after EVERY statement compiles, whatever its kind (via
    #     register_derived, so the whole-diagram compile and the incremental
    #     builder both run it), so a kind can index other definitions that
    #     refer to its derived entities -- e.g. a prism records each segment
    #     joining two of its corners. Must only add to objects already in the
    #     table; never adds or overwrites table entries.
    index: Callable[[Any, Any, dict[str, Any]], None] | None = None
    # render_ref_error: (statement, render op kind, slot) -> error message, or
    #     None when the statement's id is valid in that slot of a render
    #     operation (slots: see ``render_refs``). Lets a kind whose compiled
    #     object is not a SymPy shape reject uses the renderers would silently
    #     skip or crash on (check_render_refs raises the message).
    render_ref_error: Callable[[Any, str, str], "str | None"] | None = None
    # render_warnings: (statement, diagram) -> non-fatal render warnings,
    #     appended to the renderer's ``warnings`` list by lower_render.
    render_warnings: Callable[[Any, Any], list[str]] | None = None
    # --- solid hooks: a kind whose compiled object is not a SymPy shape ---
    # compile: (statement, ref, ev) -> the compiled object. ``ref`` resolves a
    #     referenced id in the symbol table, ``ev`` evaluates an expression
    #     field. compile_one calls it before its own per-kind dispatch.
    compile: Callable[[Any, Callable[[str], Any], Callable[[Any], Any]], Any] | None = None
    # object_type: the exact class of the compiled object (``entry_for_object``
    #     recognizes a symbol-table object by it; its name appears in the
    #     query's wrong-type error). Unique across kinds.
    object_type: type | None = None
    # query_type / query: the agent query tools' ``query_type`` name (unique
    #     across kinds) and compiled object -> JSON-able result dict. The
    #     dispatch takes the id from params[query_type], "id" or "object" and
    #     raises a TypeError for an object of another type (needs object_type).
    query_type: str | None = None
    query: Callable[[Any], dict] | None = None
    # true_length: (symbol table, segment id) -> exact true (3D) length of a
    #     segment that belongs to one of this kind's objects, or None. The
    #     ``length`` query adds it as ``true_length``.
    true_length: Callable[[dict[str, Any], str], Any] | None = None
    # evaluate_checks: check kind -> (check, symbol table, default tolerance)
    #     -> (passed, failure message). For check kinds that only make sense
    #     on this kind's objects (a check kind is owned by one kind). May raise
    #     checks.UnsupportedOperand for a deliberate operand rejection.
    evaluate_checks: Mapping[str, Callable[[Any, dict[str, Any], float], "tuple[bool, str]"]] = field(
        default_factory=dict
    )
    # check_warnings: (any check, symbol table) -> non-fatal warnings about
    #     how a generic check measured this kind's geometry (run_checks
    #     appends them to its ``warnings`` collector; results never change).
    check_warnings: Callable[[Any, dict[str, Any]], list[str]] | None = None
    # label_away_from: (symbol table, segment id) -> a point (x, y) the
    #     segment's label must be placed AWAY from (both renderers put the
    #     label on the far side of the segment's line), or None for a segment
    #     the kind has no rule for.
    label_away_from: Callable[[dict[str, Any], str], "tuple[float, float] | None"] | None = None
    # pipeline_warnings: (diagram, symbol table) -> non-fatal warnings that
    #     need both the render operations and the compiled geometry (e.g. a
    #     label text contradicting a measure). Called once per kind by
    #     run_ir_pipeline after the checks.
    pipeline_warnings: Callable[[Any, dict[str, Any]], list[str]] | None = None
    # canvas_extent: (statement, point_xy) -> points (x, y) the recipe
    #     lowerer's auto canvas must contain for this statement; ``point_xy``
    #     maps a point id to its lowering-time (x, y) or None. Empty when the
    #     extent is unknown (e.g. expression dimensions).
    canvas_extent: Callable[[Any, Callable[[str], Any]], list[tuple[float, float]]] | None = None
    # trusted_faces: the polygons this kind synthesizes are valid by
    #     construction and are faces of a solid, not 2D figures: compile
    #     builds them without SymPy's validating (vertex-pruning) constructor,
    #     and the angle-mark check does not treat their sides as lines a
    #     point lies on. Both are speed-ups for kinds with many faces.
    trusted_faces: bool = False
    # screen_bounds: compiled object -> (xmin, ymin, xmax, ymax), the
    #     axis-aligned box of its projected geometry in drawing coordinates.
    #     Used only by ``overlap_warnings`` (needs ``object_type``).
    screen_bounds: Callable[[Any], "tuple[float, float, float, float]"] | None = None


def render_refs(op: Any) -> list[tuple[str, str]]:
    """(slot, object id) for every object a render operation names. Slots:
    ``draw`` (Draw.obj), ``fill`` / ``fill_hole`` (Fill.obj / Fill.holes),
    ``point`` (DrawPoints, LabelPoint and the three points of every angle),
    ``segment`` (MarkSegments, LabelSegment), ``arc`` (MarkArcs,
    LabelAlongArc) and ``centroid`` (LabelFreeText.centroid_of)."""
    match op:
        case ir.Draw(obj=obj):
            return [("draw", obj)]
        case ir.Fill(obj=obj, holes=holes):
            return [("fill", obj), *(("fill_hole", h) for h in holes)]
        case ir.DrawPoints(points=points):
            return [("point", p) for p in points]
        case ir.LabelPoint(p=p):
            return [("point", p)]
        case ir.MarkAngles(angles=angles) | ir.MarkRightAngles(angles=angles):
            return [("point", pid) for a in angles for pid in (a.a, a.o, a.b)]
        case ir.LabelAngle(angle=a):
            return [("point", pid) for pid in (a.a, a.o, a.b)]
        case ir.MarkSegments(segs=segs):
            return [("segment", s) for s in segs]
        case ir.LabelSegment(seg=seg):
            return [("segment", seg)]
        case ir.MarkArcs(arcs=arcs):
            return [("arc", a) for a in arcs]
        case ir.LabelAlongArc(arc=arc):
            return [("arc", arc)]
        case ir.LabelFreeText(centroid_of=cof) if cof is not None:
            return [("centroid", cof)]
    return []


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
        for entry in self._by_kind.values():
            claims = (
                ("object type", construction.object_type, entry.object_type),
                ("query type", construction.query_type, entry.query_type),
            )
            for what, mine, theirs in claims:
                if mine is not None and mine == theirs:
                    raise ValueError(
                        f"{what} {mine!r} claimed by both {entry.kind!r} and {construction.kind!r}"
                    )
            for check_kind in construction.evaluate_checks:
                if check_kind in entry.evaluate_checks:
                    raise ValueError(
                        f"check kind {check_kind!r} claimed by both {entry.kind!r} and "
                        f"{construction.kind!r}"
                    )
        if construction.query is not None and construction.object_type is None:
            raise ValueError(f"{construction.kind!r}: a query hook needs object_type")
        self._by_kind[construction.kind] = construction
        for form in construction.id_forms:
            self._form_owner[form] = construction.kind

    def unregister(self, kind: str) -> None:
        """Remove a registered kind and free its id forms (for tests that
        register a temporary kind; the default kinds stay registered)."""
        self._by_kind.pop(kind)
        self._form_owner = {f: k for f, k in self._form_owner.items() if k != kind}

    def get(self, stmt: Any) -> DerivedConstruction | None:
        return self._by_kind.get(getattr(stmt, "kind", None))

    # --- solid-hook lookups (see the hook fields on DerivedConstruction) ---

    def entry_for_object(self, obj: Any) -> DerivedConstruction | None:
        """The kind whose compiled objects have exactly ``obj``'s type."""
        for entry in self._by_kind.values():
            if entry.object_type is not None and type(obj) is entry.object_type:
                return entry
        return None

    def query_entry(self, query_type: str) -> DerivedConstruction | None:
        """The kind that answers the ``query_type`` agent query, if any."""
        for entry in self._by_kind.values():
            if entry.query is not None and entry.query_type == query_type:
                return entry
        return None

    def true_length(self, sym: dict[str, Any], segment_id: str) -> Any:
        """The first true length a kind gives for the segment; None if none does."""
        for entry in self._by_kind.values():
            if entry.true_length is not None:
                true = entry.true_length(sym, segment_id)
                if true is not None:
                    return true
        return None

    def check_evaluator(self, check_kind: str) -> Callable[..., "tuple[bool, str]"] | None:
        for entry in self._by_kind.values():
            evaluate = entry.evaluate_checks.get(check_kind)
            if evaluate is not None:
                return evaluate
        return None

    def check_warnings(self, check: Any, sym: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for entry in self._by_kind.values():
            if entry.check_warnings is not None:
                out.extend(entry.check_warnings(check, sym))
        return out

    def label_away_from(self, sym: dict[str, Any], segment_id: str) -> "tuple[float, float] | None":
        for entry in self._by_kind.values():
            if entry.label_away_from is not None:
                point = entry.label_away_from(sym, segment_id)
                if point is not None:
                    return point
        return None

    def screen_bounds(self, obj: Any) -> "tuple[float, float, float, float] | None":
        """The screen box of a compiled solid; None for any other object."""
        entry = self.entry_for_object(obj)
        if entry is None or entry.screen_bounds is None:
            return None
        return entry.screen_bounds(obj)

    def drawn_ids(self, diagram: Any) -> set[str]:
        """Ids of the statements a ``draw`` or ``fill`` render operation
        draws: the named id itself, or its owner when the id is owned by an
        authored statement (a solid's faces, edges or column top faces;
        ``owner_map``), so a shaded solid drawn only through its face ids
        counts as drawn. Labels and centroid targets do not count. Works on
        the authored diagram and on the effective view alike: ownership is
        computed from the authored statements only (over the effective view
        ``owner_map`` would resolve synthesized ids to themselves). The one
        "drawn" rule of ``overlap_warnings`` and ``lower_render``'s
        ``lower_labels`` pass."""
        owners = self.owner_map([s for s in diagram.define if not is_synthesized(s)])
        drawn: set[str] = set()
        for op in diagram.render:
            for slot, rid in render_refs(op):
                if slot in ("draw", "fill"):
                    drawn.add(owners.get(rid, rid))
        return drawn

    def overlap_warnings(self, diagram: Any, sym: dict[str, Any]) -> list[str]:
        """The kind-agnostic solid-overlap advisory: solids are not depth
        sorted against each other, so two AUTHORED solids (any kinds with a
        ``screen_bounds`` hook) whose screen boxes overlap paint in draw order.
        One warning per overlapping pair, in authored definition order
        (``a`` is the earlier-defined). A solid is DRAWN when a ``draw`` or
        ``fill`` render operation names its own id or any id it owns (its
        faces, edges, column top faces: ``owner_map``), since a shaded solid
        is drawn through its face ids, never its own; labels and centroid
        targets do not count (``drawn_ids``). An undrawn solid does not
        participate. Boxes that only touch (zero-area intersection, within
        1e-9) do not overlap."""
        drawn = self.drawn_ids(diagram)
        boxes: list[tuple[str, tuple[float, float, float, float]]] = []
        for stmt in diagram.define:
            if stmt.id not in drawn or stmt.id not in sym:
                continue
            box = self.screen_bounds(sym[stmt.id])
            if box is not None:
                boxes.append((stmt.id, box))
        eps = 1e-9
        out: list[str] = []
        for i, (a, (ax0, ay0, ax1, ay1)) in enumerate(boxes):
            for b, (bx0, by0, bx1, by1) in boxes[i + 1:]:
                if ax0 < bx1 - eps and bx0 < ax1 - eps and ay0 < by1 - eps and by0 < ay1 - eps:
                    out.append(f"draw order is not depth order; solids '{a}' and '{b}' overlap on screen")
        return out

    def pipeline_warnings(self, diagram: Any, sym: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for entry in self._by_kind.values():
            if entry.pipeline_warnings is not None:
                out.extend(entry.pipeline_warnings(diagram, sym))
        out.extend(self.overlap_warnings(diagram, sym))
        return out

    def canvas_extent(self, stmt: Any, point_xy: Callable[[str], Any]) -> list[tuple[float, float]]:
        entry = self.get(stmt)
        if entry is None or entry.canvas_extent is None:
            return []
        return entry.canvas_extent(stmt, point_xy)

    def is_trusted_face(self, stmt: Any, sym: dict[str, Any]) -> bool:
        """True for a polygon synthesized by a ``trusted_faces`` kind whose
        owner has compiled (its owner's object is in ``sym``)."""
        owner = getattr(stmt, "_synthesized_by", None)
        if owner is None or getattr(stmt, "kind", None) != "polygon":
            return False
        entry = self.entry_for_object(sym.get(owner))
        return entry is not None and entry.trusted_faces

    def has_position(self, stmt: Any) -> bool:
        """True when ``stmt``'s kind supplies a position for its compiled
        object (a centroid anchor for free text, e.g. pydsl's
        ``label_text(centroid_of=...)``)."""
        entry = self.get(stmt)
        return entry is not None and entry.position is not None

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

    def check_exclusive_ids(self, stmts: list[Any]) -> None:
        """Raise IRCompileError (naming the later statement) when an owned id
        of an ``exclusive`` kind is also an authored definition id in
        ``stmts``, or is owned by another statement. Pairs where neither kind
        is exclusive keep their existing behavior. Synthesized ids count as
        owned here (as in ``owner_map``). Only authored statements form the
        set of real ids, so the check is idempotent on an already-effective
        list (a statement's own synthesized definitions are not collisions),
        as in ``effective_defs``. A kind's own invariants about its derived
        names (e.g. not reusing its own id) are its compile step's job."""
        real_ids = {s.id for s in stmts if not is_synthesized(s)}
        claimed: dict[str, tuple[str, bool]] = {}
        for stmt in stmts:
            entry = self.get(stmt)
            if entry is None:
                continue
            synth_ids = [s.id for s in self.synthesized(stmt)]
            for did in dict.fromkeys([*entry.owned_ids(stmt), *synth_ids]):
                if entry.exclusive and did != stmt.id and did in real_ids:
                    raise IRCompileError(
                        stmt.id,
                        f"derived name {did!r} collides with the definition {did!r}; "
                        f"rename one of them",
                    )
                prev = claimed.get(did)
                if prev is not None and prev[0] != stmt.id and (entry.exclusive or prev[1]):
                    raise IRCompileError(
                        stmt.id,
                        f"derived name {did!r} is already derived from {prev[0]!r}; "
                        f"derived names must be unique",
                    )
                claimed.setdefault(did, (stmt.id, entry.exclusive))

    def synthesized(self, stmt: Any) -> list[Any]:
        """The definitions ``stmt``'s kind synthesizes (empty for most kinds),
        each marked as synthesized by ``stmt`` (see ``is_synthesized``)."""
        entry = self.get(stmt)
        if entry is None or entry.synthesize is None or is_synthesized(stmt):
            return []
        out = list(entry.synthesize(stmt))
        for synth in out:
            synth._synthesized_by = stmt.id
        return out

    def effective_defs(self, stmts: list[Any]) -> list[Any]:
        """Authored statements, each followed by the definitions its kind
        synthesizes. Always a new list; ``stmts`` is never modified.

        The single place authored and synthesized ids meet: a synthesized id
        equal to an authored definition id, or to another synthesized id, is
        an IRCompileError (naming the definition to rename), never a silent
        shadow. Statements that are themselves synthesized (the input is an
        already-effective view, e.g. a renderer's helper pass) are skipped
        and recomputed from their owners, so the view is idempotent whatever
        kinds are registered."""
        authored = [s for s in stmts if not is_synthesized(s)]
        taken: dict[str, str | None] = {s.id: None for s in authored}
        view: list[Any] = []
        for stmt in authored:
            view.append(stmt)
            for synth in self.synthesized(stmt):
                if synth.id in taken:
                    other = taken[synth.id]
                    if other is None:
                        raise IRCompileError(
                            synth.id,
                            f"definition {synth.id!r} has the same id as the {synth.kind} "
                            f"derived from {stmt.kind} {stmt.id!r}; derived ids are reserved, "
                            f"rename {synth.id!r}",
                        )
                    raise IRCompileError(
                        stmt.id,
                        f"derived id {synth.id!r} is produced by both {other!r} and "
                        f"{stmt.id!r}; rename one of them",
                    )
                taken[synth.id] = stmt.id
                view.append(synth)
        return view

    def check_render_refs(self, diagram: Any) -> None:
        """Raise IRCompileError (naming the statement) for the first render
        operation that names a registered kind's id in a slot its
        ``render_ref_error`` hook rejects. Called by compile_defs and by
        lower_render, so the error reaches the retry loops from compile and
        from either renderer's entry function."""
        stmts = {s.id: s for s in diagram.define}
        for op in diagram.render:
            for slot, oid in render_refs(op):
                stmt = stmts.get(oid)
                entry = self.get(stmt) if stmt is not None else None
                if entry is None or entry.render_ref_error is None:
                    continue
                message = entry.render_ref_error(stmt, op.kind, slot)
                if message is not None:
                    raise IRCompileError(stmt.id, message)

    def lower_render(self, diagram: Any, sym: dict[str, Any], warnings: list[str] | None = None) -> Any:
        """``diagram`` with every draw of a lowering kind's id replaced, in
        place, by the hook's ordered operations (see ``Lowering``), and the
        hook's styles merged into ``styles``; then, once per drawn authored
        statement of a kind with a ``lower_labels`` hook (``drawn_ids``), the
        hook's label operations for ``sym[stmt.id]`` (``sym`` is the compiled
        symbol table) appended after all other operations. ``diagram`` itself
        when nothing lowers; otherwise a shallow ``RenderTimeDiagram`` copy
        local to the caller: an internal render-time view that refuses
        ``model_dump`` / ``model_dump_json`` (never dump, persist or
        re-validate it).

        First rejects render operations misusing a registered kind's id
        (``check_render_refs``) and appends each kind's ``render_warnings``
        to ``warnings`` (when given)."""
        self.check_render_refs(diagram)
        if warnings is not None:
            for stmt in diagram.define:
                entry = self.get(stmt)
                if entry is not None and entry.render_warnings is not None and not is_synthesized(stmt):
                    warnings.extend(entry.render_warnings(stmt, diagram))
        stmts = {s.id: s for s in diagram.define}
        ops: list[Any] = []
        styles = dict(diagram.styles)
        lowered = False
        for op in diagram.render:
            stmt = stmts.get(getattr(op, "obj", None)) if getattr(op, "kind", None) == "draw" else None
            entry = self.get(stmt) if stmt is not None else None
            if entry is None or entry.lower_draw is None:
                ops.append(op)
                continue
            result = entry.lower_draw(stmt, op, diagram.styles)
            for name, style in result.styles.items():
                if name in styles and styles[name] != style:
                    raise IRCompileError(
                        stmt.id,
                        f"drawing {stmt.id!r} needs the reserved style {name!r}, but the "
                        f"diagram already defines a style with that name and a different "
                        f"value; rename that style",
                    )
                styles[name] = style
            ops.extend(result.ops)
            lowered = True
        drawn: set[str] | None = None
        for stmt in diagram.define:
            entry = self.get(stmt)
            if entry is None or entry.lower_labels is None or is_synthesized(stmt):
                continue
            if drawn is None:
                drawn = self.drawn_ids(diagram)
            if stmt.id not in drawn or stmt.id not in sym:
                continue
            labels = entry.lower_labels(stmt, sym[stmt.id])
            if labels:
                ops.extend(labels)
                lowered = True
        if not lowered:
            return diagram
        return render_view(diagram, {"render": ops, "styles": styles})

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
        """Post-compile step for one statement: its own kind registers its
        derived entities, then every kind with an ``index`` hook sees it."""
        entry = self.get(stmt)
        if entry is not None:
            entry.register(stmt, obj, sym)
        for kind_entry in self._by_kind.values():
            if kind_entry.index is not None:
                kind_entry.index(stmt, obj, sym)


# --- registered constructions ------------------------------------------------

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
    reg.register(DerivedConstruction(
        "rectangular_prism", (
            "{id}_v{abc}", "{id}_e_{abc}_{abc}", "{id}_{face}", "__{id}_gp{n}", "__{id}_g{n}",
        ),
        lambda stmt: list(_prism.corner_names(stmt).values()),
        _prism.register_corners,
        position=_prism.prism_position,
        synthesize=_prism.synthesize_edges_and_faces,
        lower_draw=_prism.lower_draw,
        exclusive=True,
        feature="solids",
        index=_prism.index_corner_segment,
        render_ref_error=_prism.render_ref_error,
        render_warnings=_prism.render_warnings,
        compile=_prism.compile_statement,
        object_type=_prism.Prism,
        query_type="prism",
        query=_prism.query,
        true_length=_prism.true_length,
        evaluate_checks=_prism.EVALUATE_CHECKS,
        check_warnings=_prism.projection_check_warnings,
        label_away_from=_prism.corner_segment_center,
        lower_labels=_prism.lower_labels,
        pipeline_warnings=_prism.label_dimension_warnings,
        canvas_extent=_prism.canvas_extent,
        screen_bounds=_prism.screen_bounds,
    ))
    reg.register(DerivedConstruction(
        "block_stack", ("{id}_top_{x}_{z}", "__{id}_l{x}_{y}_{z}"),
        lambda stmt: list(_stack.lattice_names(stmt).values()),
        _stack.register_lattice,
        position=_stack.stack_position,
        synthesize=_stack.synthesize_top_faces,
        lower_draw=_stack.lower_draw,
        lower_labels=_stack.lower_labels,
        exclusive=True,
        feature="solids",
        render_ref_error=_stack.render_ref_error,
        render_warnings=_stack.render_warnings,
        compile=_stack.compile_statement,
        object_type=_stack.Stack,
        query_type="stack",
        query=_stack.query,
        evaluate_checks=_stack.EVALUATE_CHECKS,
        canvas_extent=_stack.canvas_extent,
        screen_bounds=_stack.screen_bounds,
        trusted_faces=True,
    ))
    return reg


REGISTRY = _build_default_registry()


def is_synthesized(stmt: Any) -> bool:
    """True for a definition the registry synthesized (never authored)."""
    return getattr(stmt, "_synthesized_by", None) is not None


def lower_render(diagram: Any, sym: dict[str, Any], warnings: list[str] | None = None) -> Any:
    """The render lowering point: see ``DerivedRegistry.lower_render``. Both
    renderers' entry functions call it right after ``effective_diagram``,
    with the compiled symbol table ``sym``.

    Its result is one of the internal render-time views: never dump, persist
    or re-validate it (``OrderedPolygon`` is outside the ``RenderOp`` union);
    it raises ``TypeError`` if you try."""
    return REGISTRY.lower_render(diagram, sym, warnings)


def effective_defs(diagram: Any) -> list[Any]:
    """The effective definition set of ``diagram``: its authored definitions
    plus every definition a registered kind synthesizes. A pure function of
    ``diagram.define`` alone (never of a symbol table or a random stream)."""
    return REGISTRY.effective_defs(diagram.define)


def effective_diagram(diagram: Any) -> Any:
    """``diagram`` itself when nothing is synthesized, else a shallow copy
    whose ``define`` is the effective view (a ``RenderTimeDiagram``: an
    internal render-time view that refuses serialization, because its
    synthesized definitions lose their ``_synthesized_by`` marker on a
    round-trip). The copy is local to the caller (a renderer's entry
    function); the authored IR is never rewritten."""
    view = effective_defs(diagram)
    if len(view) == len(diagram.define):
        return diagram
    return render_view(diagram, {"define": view})
