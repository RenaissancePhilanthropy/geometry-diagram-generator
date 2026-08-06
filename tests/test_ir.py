"""Tests for IR schema (geometry_diagrams/ir/ir.py)."""


def test_elliptical_arc_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalArcCenterStartEnd, DiagramIR

    stmt = EllipticalArcCenterStartEnd(
        id="ea1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=False,
    )
    assert stmt.kind == "elliptical_arc_center_start_end"
    assert stmt.hradius == 4 and stmt.vradius == 1


def test_elliptical_sector_center_start_end_round_trips():
    from geometry_diagrams.ir.ir import EllipticalSectorCenterStartEnd

    stmt = EllipticalSectorCenterStartEnd(
        id="es1", center="c", hradius=4, vradius=1, start="s", end="e", reflex=True,
    )
    assert stmt.kind == "elliptical_sector_center_start_end"
    assert stmt.reflex is True
