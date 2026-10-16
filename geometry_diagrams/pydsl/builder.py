# geometry_diagrams/pydsl/builder.py
"""Ambient builder context for the Python DSL surface.

Every public API function in `api.py` records its op against the Builder
returned by `get_builder()`. The contextvar is set fresh per script execution
(see sandbox.py) so that sequential executions never share state.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from random import Random
from typing import Iterator

from geometry_diagrams.ir.ir import DefBase, DefStmt, DiagramIR

DEFAULT_OP_CAP = 2000


class OpCapExceededError(RuntimeError):
    """Raised when a script records more ops than the configured cap."""


class GeometricAssertionError(ValueError):
    """Raised when an assert_* predicate detects a failed geometric invariant."""


class Builder:
    def __init__(self, op_cap: int = DEFAULT_OP_CAP) -> None:
        self._defs: list[DefStmt] = []
        self._render: list = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._segment_cache: dict[frozenset, str] = {}
        # Prism id -> its bits -> corner id map, for segment edge reuse.
        self._prism_corners: dict[str, dict] = {}
        self._op_cap = op_cap
        self._hidden_id_counter = 0
        self._canvas = None  # set at most once, by canvas(); type is ir.Canvas | None
        self._styles: dict[str, dict] = {}
        self._mark_group_counter = 0
        self._sym: dict = {}
        self._sym_watermark: int = 0
        # synthesized id -> owning statement id, for the collision check in
        # _advance_sym (synthesized definitions never enter self._defs).
        self._synthesized_ids: dict[str, str] = {}
        # ONE rng for the whole script, mirroring how compile_defs() threads a
        # single Random(42) through a whole diagram. _advance_sym() compiles
        # the script incrementally, in as many slices as there are mid-script
        # coordinate reads, and an rng-consuming def (PointOn with a
        # PointOnIntent, whose constraints are satisfied by rejection
        # sampling) must see the same stream position it would in the
        # whole-diagram compile. Rebuilding Random(42) per slice rewinds the
        # stream, so a point resolved mid-script would silently disagree with
        # the coordinates the rendered diagram ends up with.
        #
        # Sharing one rng instance closes the rewind, but not the whole
        # divergence by itself: _advance_sym() compiles in INSERTION order,
        # compile_defs() in TOPOLOGICAL order, and those only agree on the
        # relative order of two rng-consuming defs while they sit at the same
        # dependency depth. That residual is closed separately, by
        # _pin_point_on() below: the moment a PointOnIntent def is compiled
        # here, its sampled result is pinned into a dependency-pure
        # PointOnParam (see that method), so no PointOnIntent def is ever
        # left for compile_defs() to re-sample once it has passed through
        # this incremental compiler -- ordering can no longer matter for it,
        # because there is no rng draw left for either compile's order to
        # affect.
        self._rng = Random(42)

    @property
    def op_count(self) -> int:
        return len(self._defs)

    def _add(self, defstmt: DefBase) -> None:
        if len(self._defs) >= self._op_cap:
            raise OpCapExceededError(
                f"script recorded more than {self._op_cap} ops "
                "(this is a size cap, not a security boundary)"
            )
        self._defs.append(defstmt)  # type: ignore[arg-type]

    def _add_render(self, render_op) -> None:
        if len(self._defs) + len(self._render) >= self._op_cap:
            raise OpCapExceededError(
                f"script recorded more than {self._op_cap} ops "
                "(this is a size cap, not a security boundary)"
            )
        self._render.append(render_op)

    def _fresh_hidden_id(self, prefix: str) -> str:
        self._hidden_id_counter += 1
        return f"__pydsl_{prefix}_{self._hidden_id_counter}"

    def _register_style(self, style: dict) -> str:
        """Register a non-empty style dict, returning a fresh key into
        DiagramIR.styles. Always creates a fresh key — no dedup across
        identical style dicts; the number of draw()/fill() calls in a
        real script is small enough that this isn't worth the complexity."""
        key = self._fresh_hidden_id("style")
        self._styles[key] = style
        return key

    def _fresh_mark_group(self, kind: str) -> str:
        """Return a fresh, globally-unique group string prefixed by kind
        (e.g. "parallel_3", "equal_1"). Uniqueness matters (so unrelated
        mark_equal()/mark_parallel() calls never collide into the same
        visual symbol); the "parallel" prefix specifically matters because
        both renderers route purely on group.startswith("parallel") to
        pick the chevron cycle instead of the tick-mark cycle — kind must
        be passed as literally "parallel" for mark_parallel() to render
        correctly."""
        self._mark_group_counter += 1
        return f"{kind}_{self._mark_group_counter}"

    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=self._canvas, styles=dict(self._styles))

    def _get_or_create_segment(self, p_id: str, q_id: str) -> "Segment":
        from geometry_diagrams.ir.ir import Segment as SegmentDef
        from geometry_diagrams.ir.prism import edge_between
        from geometry_diagrams.pydsl.handles import Segment

        for prism_id, corners in self._prism_corners.items():
            edge = edge_between(prism_id, corners, p_id, q_id)
            if edge is not None:
                return Segment(id=edge, _builder=self)
        key = frozenset((p_id, q_id))
        if key in self._segment_cache:
            return Segment(id=self._segment_cache[key], _builder=self)
        sid = self._fresh_hidden_id("seg")
        self._add(SegmentDef(id=sid, a=p_id, b=q_id))
        self._segment_cache[key] = sid
        return Segment(id=sid, _builder=self)

    def _register_prism(self, stmt) -> "Prism":
        """Build the Prism handle for a just-recorded (and compiled)
        RectangularPrism, and record its corners so segment(a, b) between two
        corners of one edge returns the prism's derived edge (never a second,
        duplicate stroke; see _get_or_create_segment). Diagonals and non-edges
        get an ordinary segment."""
        from geometry_diagrams.ir import prism as prism_mod
        from geometry_diagrams.pydsl.handles import Prism

        names = prism_mod.corner_names(stmt)
        self._prism_corners[stmt.id] = dict(names)
        return Prism(
            id=stmt.id, length=stmt.length, width=stmt.width, height=stmt.height,
            _builder=self, _corner_ids=dict(names),
        )

    def _register_stack(self, stmt) -> "Stack":
        """Build the Stack handle for a just-recorded (and compiled) BlockStack,
        reading the cube count and column top-face corner ids from the compiled
        Stack object in the incremental symbol table."""
        from geometry_diagrams.ir.stack import column_tops, lattice_id, top_face_corners
        from geometry_diagrams.pydsl.handles import Stack

        obj = self._sym[stmt.id]
        tops = {
            (x, z): tuple(lattice_id(stmt.id, c) for c in top_face_corners(x, y, z))
            for (x, z), y in column_tops(obj.cubes).items()
        }
        return Stack(id=stmt.id, cube_count=obj.cube_count, _builder=self, _tops=tops)

    def _resolve_point(self, pid: str) -> "tuple[float, float]":
        """Return (x, y) for any point id already recorded in self._defs,
        compiling as many new defs as needed via to_sympy.py's real
        per-statement compiler. Raises whatever to_sympy.py raises
        (IntersectionError, PickError, IRCompileError, a plain SymPy
        ValueError, ...) if a def between the last resolve and pid's
        definition genuinely can't be compiled."""
        if pid in self._coord_floats:
            return self._coord_floats[pid]
        self._advance_sym()
        if pid not in self._coord_floats:
            raise ValueError(f"Point {pid!r} has no known coordinates")
        return self._coord_floats[pid]

    def _advance_sym(self) -> None:
        import sympy.geometry as spg

        from geometry_diagrams.ir import ir as ir_mod
        from geometry_diagrams.ir.derived import REGISTRY as DERIVED_REGISTRY
        from geometry_diagrams.ir.to_sympy import compile_one_attributed

        canvas = self._canvas or ir_mod.Canvas()
        # self._rng, NOT a fresh Random(42): see __init__ for why the stream
        # has to survive across _advance_sym() calls.
        rng = self._rng
        # Iterate a SLICE (a copy) taken once up front -- _pin_intersection
        # appends new hidden PointFixed defs to self._defs mid-loop, which
        # must not be picked up by this iteration (they're compiled and
        # cached inline below instead, and self._sym_watermark accounts
        # for them afterward via len(self._defs)).
        def compile_into_sym(stmt):
            obj = compile_one_attributed(stmt, self._sym, {}, canvas, rng, all_def_ids=None)
            self._sym[stmt.id] = obj
            # Mirror compile_defs()'s post-compile registration of derived
            # entities, via the same registry: without it the incremental
            # table disagrees with the whole-diagram one and defs carrying a
            # derived id fail with UndefinedRefError on a mid-script resolve.
            known = len(self._sym)
            DERIVED_REGISTRY.register_derived(stmt, obj, self._sym)
            for new_id in [stmt.id, *list(self._sym)[known:]]:
                new_obj = self._sym[new_id]
                if isinstance(new_obj, spg.Point):
                    self._coord_floats[new_id] = (float(new_obj.x), float(new_obj.y))
            return obj

        from geometry_diagrams.ir.errors import IRCompileError

        for stmt in self._defs[self._sym_watermark:]:
            # An authored id equal to an already-synthesized one is the same
            # typed error effective_defs() raises for the whole diagram (never
            # a silent overwrite of the synthesized definition).
            if stmt.id in self._synthesized_ids:
                raise IRCompileError(
                    stmt.id,
                    f"definition {stmt.id!r} has the same id as a definition derived from "
                    f"{self._synthesized_ids[stmt.id]!r}; derived ids are reserved, rename {stmt.id!r}",
                )
            obj = compile_into_sym(stmt)
            # Likewise mirror compile_defs()'s effective view: definitions the
            # kind synthesizes (never added to self._defs, so never to the
            # authored IR) are compiled right after their owner, whose
            # derived entities they may reference. A name already in the
            # table is a collision, as in effective_defs().
            for synth in DERIVED_REGISTRY.synthesized(stmt):
                if synth.id in self._sym:
                    raise IRCompileError(
                        synth.id,
                        f"definition {synth.id!r} has the same id as the {synth.kind} derived "
                        f"from {stmt.id!r}; derived ids are reserved, rename {synth.id!r}",
                    )
                self._synthesized_ids[synth.id] = stmt.id
                compile_into_sym(synth)
            if isinstance(stmt, ir_mod.PointIntersection) and stmt.pick is None:
                self._pin_intersection(stmt, obj)
            if isinstance(stmt, ir_mod.PointOn) and isinstance(stmt.how, ir_mod.PointOnIntent):
                self._pin_point_on(stmt, obj)
        self._sym_watermark = len(self._defs)

    def _pin_intersection(self, stmt, obj) -> None:
        """Rewrite an unpicked PointIntersection's pick to a
        dependency-pure PickClosestTo targeting the just-observed
        coordinates, so a later full recompile-from-scratch reproduces the
        same candidate regardless of what else is in its sym table by
        then. Bypasses self._add() deliberately -- this hidden bookkeeping
        def must not count against the script's op cap.

        This observe-then-pin pattern is also the shape _pin_point_on() below
        uses for the analogous PointOnIntent case."""
        from geometry_diagrams.ir import ir as ir_mod

        hidden_pid = self._fresh_hidden_id("pin")
        self._defs.append(ir_mod.PointFixed(id=hidden_pid, x=float(obj.x), y=float(obj.y)))
        self._sym[hidden_pid] = obj
        self._coord_floats[hidden_pid] = (float(obj.x), float(obj.y))
        stmt.pick = ir_mod.PickClosestTo(p=hidden_pid)

    def _pin_point_on(self, stmt, obj) -> None:
        """Rewrite a PointOn(PointOnIntent)'s how to a dependency-pure
        PointOnParam recovering the just-observed coordinates, so a later
        full recompile-from-scratch reproduces the same sampled point
        regardless of what order _advance_sym() and compile_defs() visit
        rng-consuming defs in -- closes the KNOWN RESIDUAL noted in
        __init__. Keeps the def as PointOn (not PointFixed, unlike
        _pin_intersection's hidden helper above) so it still satisfies
        checks._build_linear_pairs' on-object membership. Every
        PointOnIntent def compiled in a slice gets pinned here, not only
        whichever handle's coordinates were actually read -- a later
        cached read of a sibling point must see the same pinned value."""
        from geometry_diagrams.ir import ir as ir_mod
        from geometry_diagrams.ir.to_sympy import _invert_param

        on_obj = self._sym[stmt.on]
        t = _invert_param(on_obj, float(obj.x), float(obj.y), stmt.id)
        stmt.how = ir_mod.PointOnParam(t=t)


_current_builder: contextvars.ContextVar["Builder | None"] = contextvars.ContextVar(
    "pydsl_current_builder", default=None
)


def get_builder() -> Builder:
    builder = _current_builder.get()
    if builder is None:
        raise RuntimeError("no active Builder — call inside new_builder_context()")
    return builder


@contextmanager
def new_builder_context(op_cap: int = DEFAULT_OP_CAP) -> Iterator[Builder]:
    builder = Builder(op_cap=op_cap)
    token = _current_builder.set(builder)
    try:
        yield builder
    finally:
        _current_builder.reset(token)
