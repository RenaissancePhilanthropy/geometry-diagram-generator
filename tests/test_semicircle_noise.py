"""A diameter chord gives two 180-degree arcs; float noise in the endpoint
angles must not decide which one is "minor". Within ~1e-9 of 180 the sweep is
exactly a semicircle, so the same arc is picked at every integer angle and in
every copy of the sweep logic."""
from __future__ import annotations

import math

import pytest

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.render_util import arc_params, elliptical_arc_params
from geometry_diagrams.ir.to_sympy import arc_param_frame, arc_sweep_degrees, compile_defs

R, HR, VR = 3.0, 3.0, 2.0


def _compile(angle_deg: int):
    """One diagram per angle holding all four arcs: circular and elliptical,
    reflex False (A, EA) and True (B, EB), over a diameter chord."""
    t = math.radians(angle_deg)
    s = (R * math.cos(t), R * math.sin(t))
    es = (HR * math.cos(t), VR * math.sin(t))
    arcs = []
    for aid, reflex in (("A", False), ("B", True)):
        arcs.append({"id": aid, "kind": "arc_center_start_end", "center": "O",
                     "start": "S", "end": "E", "reflex": reflex})
    for aid, reflex in (("EA", False), ("EB", True)):
        arcs.append({"id": aid, "kind": "elliptical_arc_center_start_end", "center": "O",
                     "hradius": HR, "vradius": VR, "start": "ES", "end": "EE", "reflex": reflex})
    d = ir.DiagramIR.model_validate({
        "canvas": {"xmin": -8, "xmax": 8, "ymin": -8, "ymax": 8},
        "define": [
            {"id": "O", "kind": "point_fixed", "x": 0, "y": 0},
            {"id": "S", "kind": "point_fixed", "x": s[0], "y": s[1]},
            {"id": "E", "kind": "point_fixed", "x": -s[0], "y": -s[1]},
            {"id": "ES", "kind": "point_fixed", "x": es[0], "y": es[1]},
            {"id": "EE", "kind": "point_fixed", "x": -es[0], "y": -es[1]},
            *arcs,
        ],
    })
    return compile_defs(d)


def _wrap(a: float, ref: float, period: float) -> float:
    """Signed difference a - ref folded into [-period/2, period/2)."""
    return (a - ref + period / 2) % period - period / 2


# 0..179: the other half of the turn is the same chord with its endpoints
# swapped, covered by the reflex arc of each diagram.
@pytest.mark.parametrize("angle", range(0, 180))
def test_semicircle_is_stable(angle):
    sym = _compile(angle)
    for aid, reflex in (("A", False), ("B", True)):
        want = angle if not reflex else angle + 180
        _, _, s_deg, e_deg = arc_sweep_degrees(sym[aid])
        assert abs(_wrap(s_deg, want, 360.0)) < 1e-6
        assert e_deg - s_deg == pytest.approx(180.0, abs=1e-6)
        _, _, _, rs, re_, _, _ = arc_params(aid, sym)
        assert abs(_wrap(rs, want, 360.0)) < 1e-6
        assert re_ - rs == pytest.approx(180.0, abs=1e-6)
        _, _, _, _, ps, pe = arc_param_frame(sym[aid])
        assert abs(_wrap(math.degrees(ps), want, 360.0)) < 1e-6
        assert math.degrees(pe - ps) == pytest.approx(180.0, abs=1e-6)
    for aid, reflex in (("EA", False), ("EB", True)):
        want = angle if not reflex else angle + 180
        _, _, _, _, rs, re_, _, _ = elliptical_arc_params(aid, sym)
        assert abs(_wrap(rs, want, 360.0)) < 1e-6
        assert re_ - rs == pytest.approx(180.0, abs=1e-6)
        _, _, _, _, ps, pe = arc_param_frame(sym[aid])
        assert abs(_wrap(math.degrees(ps), want, 360.0)) < 1e-6
        assert math.degrees(pe - ps) == pytest.approx(180.0, abs=1e-6)
