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

    def build(self) -> DiagramIR:
        return DiagramIR(define=list(self._defs), render=list(self._render), canvas=None)

    def _get_or_create_segment(self, p_id: str, q_id: str) -> "Segment":
        from geometry_diagrams.ir.ir import Segment as SegmentDef
        from geometry_diagrams.pydsl.handles import Segment

        key = frozenset((p_id, q_id))
        if key in self._segment_cache:
            return Segment(id=self._segment_cache[key])
        sid = self._fresh_hidden_id("seg")
        self._add(SegmentDef(id=sid, a=p_id, b=q_id))
        self._segment_cache[key] = sid
        return Segment(id=sid)


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
