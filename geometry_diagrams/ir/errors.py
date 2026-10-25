from __future__ import annotations


class IRCompileError(Exception):
    def __init__(self, def_id: str, message: str) -> None:
        self.def_id = def_id
        super().__init__(f"[{def_id}] {message}")


class UndefinedRefError(IRCompileError):
    """A definition referenced an id not yet in the symbol table."""


class IntersectionError(IRCompileError):
    """Intersection of two objects produced no usable points."""


class ExprEvalError(IRCompileError):
    """A string expression could not be evaluated."""


class PickError(IRCompileError):
    """A pick rule could not select a unique candidate."""


class TiltedEllipseUnsupported(IRCompileError):
    """An operation does not support a tilted (rotated) ellipse yet.

    ``def_id`` is the failing definition (or, from a renderer, the ellipse
    itself); the message names the tilted ellipse. Later stages of the
    rotated-ellipses design lift these one by one."""
