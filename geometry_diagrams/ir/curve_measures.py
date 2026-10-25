"""Length of curves in the circle/ellipse family.

One shared answer to "how long is this curve?" for circles, ellipses, circular
arcs/sectors and elliptical arcs/sectors, so length checks and query tools do
not each re-derive it. A sector's length is its curved edge only (its straight
radii are not included).

Circular answers are closed forms (radius times sweep). Elliptical answers use
the incomplete elliptic integral of the second kind via ``mpmath.ellipe``
(``mpmath`` ships with sympy), evaluated at 30 digits.

Public surface: ``curve_length`` and ``CurveMeasureError``.
"""

from __future__ import annotations

import math
from typing import Any

import mpmath
import sympy.geometry as spg

from geometry_diagrams.ir.to_sympy import (
    Arc,
    EllipticalArc,
    EllipticalSector,
    Sector,
    _arc_param_frame,
)

_DPS = 30


class CurveMeasureError(ValueError):
    """The object is not a measurable curve (wrong type, or zero/degenerate radius).

    A ``ValueError`` (the input value is unusable) rather than the checks
    module's ``TypeError``-based ``UnsupportedOperand``, so this module stays
    independent of ``checks``; callers there can translate it.
    """


def curve_length(obj: Any) -> float:
    """Curved-edge length of an arc/sector, or the circumference/perimeter of a
    full circle/ellipse.

    Arcs follow the same sweep as the rest of the code: counter-clockwise from
    start to end, flipped by ``reflex``, in parametric angle for elliptical arcs.
    """
    if isinstance(obj, (Arc, Sector, EllipticalArc, EllipticalSector)):
        _require_positive(obj, *_radii(obj))
        _, _, hr, vr, s, e = _arc_param_frame(obj)
        return _ellipse_arc_length(hr, vr, s, e)
    if isinstance(obj, spg.Ellipse):  # Circle subclasses Ellipse
        hr, vr = _radii(obj)
        _require_positive(obj, hr, vr)
        return _ellipse_arc_length(hr, vr, 0.0, 2 * math.pi)
    raise CurveMeasureError(
        f"cannot measure the length of a {type(obj).__name__}: not a circle, ellipse, arc or sector"
    )


def _radii(obj: Any) -> tuple[float, float]:
    if isinstance(obj, (Arc, Sector)):
        r = float(obj.radius.evalf())
        return r, r
    return float(obj.hradius.evalf()), float(obj.vradius.evalf())


def _require_positive(obj: Any, hr: float, vr: float) -> None:
    if not (math.isfinite(hr) and math.isfinite(vr) and hr > 0 and vr > 0):
        raise CurveMeasureError(f"{type(obj).__name__} has a degenerate radius (hradius={hr}, vradius={vr})")


def _ellipse_arc_length(hr: float, vr: float, start: float, end: float) -> float:
    """Arc length over the parametric sweep [start, end] of x = hr cos t, y = vr sin t."""
    if hr == vr:
        return hr * (end - start)
    with mpmath.workdps(_DPS):
        if hr > vr:
            # speed = hr * sqrt(1 - m cos^2 t) = hr * sqrt(1 - m sin^2(t + pi/2))
            scale, shift = mpmath.mpf(hr), mpmath.pi / 2
            m = 1 - (mpmath.mpf(vr) / hr) ** 2
        else:
            scale, shift = mpmath.mpf(vr), mpmath.mpf(0)
            m = 1 - (mpmath.mpf(hr) / vr) ** 2
        return float(scale * (mpmath.ellipe(end + shift, m) - mpmath.ellipe(start + shift, m)))
