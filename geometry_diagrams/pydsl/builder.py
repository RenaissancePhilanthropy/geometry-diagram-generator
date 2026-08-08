# geometry_diagrams/pydsl/builder.py
"""Ambient builder context for the Python DSL surface.

Every public API function in `api.py` records its op against the Builder
returned by `get_builder()`. The contextvar is set fresh per script execution
(see sandbox.py) so that sequential executions never share state.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Iterator

from geometry_diagrams.ir.ir import DefBase, DefStmt, DiagramIR

DEFAULT_OP_CAP = 2000


class OpCapExceededError(RuntimeError):
    """Raised when a script records more ops than the configured cap."""


class Builder:
    def __init__(self, op_cap: int = DEFAULT_OP_CAP) -> None:
        self._defs: list[DefStmt] = []
        self._render: list = []
        self._coord_floats: dict[str, tuple[float, float]] = {}
        self._segment_cache: dict[frozenset, str] = {}
        self._op_cap = op_cap
        self._hidden_id_counter = 0
        self._canvas = None  # set at most once, by canvas(); type is ir.Canvas | None
        self._styles: dict[str, dict] = {}
        self._mark_group_counter = 0
        self._sym: dict = {}
        self._sym_watermark: int = 0

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
        from geometry_diagrams.pydsl.handles import Segment

        key = frozenset((p_id, q_id))
        if key in self._segment_cache:
            return Segment(id=self._segment_cache[key], _builder=self)
        sid = self._fresh_hidden_id("seg")
        self._add(SegmentDef(id=sid, a=p_id, b=q_id))
        self._segment_cache[key] = sid
        return Segment(id=sid, _builder=self)

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
        from random import Random

        import sympy.geometry as spg

        from geometry_diagrams.ir import ir as ir_mod
        from geometry_diagrams.ir.to_sympy import _compile_one

        canvas = self._canvas or ir_mod.Canvas()
        rng = Random(42)  # PointFree/random defs are dead code for pydsl; any seed is fine
        # Iterate a SLICE (a copy) taken once up front -- _pin_intersection
        # appends new hidden PointFixed defs to self._defs mid-loop, which
        # must not be picked up by this iteration (they're compiled and
        # cached inline below instead, and self._sym_watermark accounts
        # for them afterward via len(self._defs)).
        for stmt in self._defs[self._sym_watermark:]:
            obj = _compile_one(stmt, self._sym, {}, canvas, rng, all_def_ids=None)
            self._sym[stmt.id] = obj
            if isinstance(obj, spg.Point):
                self._coord_floats[stmt.id] = (float(obj.x), float(obj.y))
            if isinstance(stmt, ir_mod.PointIntersection) and stmt.pick is None:
                self._pin_intersection(stmt, obj)
        self._sym_watermark = len(self._defs)

    def _pin_intersection(self, stmt, obj) -> None:
        """Rewrite an unpicked PointIntersection's pick to a
        dependency-pure PickClosestTo targeting the just-observed
        coordinates, so a later full recompile-from-scratch reproduces the
        same candidate regardless of what else is in its sym table by
        then. Bypasses self._add() deliberately -- this hidden bookkeeping
        def must not count against the script's op cap."""
        from geometry_diagrams.ir import ir as ir_mod

        hidden_pid = self._fresh_hidden_id("pin")
        self._defs.append(ir_mod.PointFixed(id=hidden_pid, x=float(obj.x), y=float(obj.y)))
        self._sym[hidden_pid] = obj
        self._coord_floats[hidden_pid] = (float(obj.x), float(obj.y))
        stmt.pick = ir_mod.PickClosestTo(p=hidden_pid)


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
