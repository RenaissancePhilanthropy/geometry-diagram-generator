"""A label stays attached to what it labels: a point label never covers its dot or floats far
from it, a straight segment's label stays within reach of its line, and the segment-slot score
sees ellipses and tick-label boxes (``_reattach_labels``, ``_label_crowding``)."""
from __future__ import annotations

import asyncio
import math
import re

import pytest

from geometry_diagrams.ir import to_svg as T
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.python_full import _run_from_script

HEAD = """
canvas(x_range=(-4.1, 4.1), y_range=(-3.8, 4.0))
O = point(0, 0)
circ = circle(O, 3)
draw(circ, thick=True)
"""
SCRIPTS = {
    # eight radii: O's eight wedges are all narrow; its label used to be pushed 27 px away
    "star": HEAD + "".join(
        f"p{i} = point_on(circ, {i}*math.pi/4)\ns{i} = segment(O, p{i})\ndraw(s{i})\n" for i in range(8)
    ) + 'O.label("O")\n',
    # two radii, a diameter and a labelled central angle: O's label used to land on its dot
    "three_radii": HEAD + """
A = point_on(circ, 40*math.pi/180); B = point_on(circ, 140*math.pi/180)
D = point_on(circ, 0); E = point_on(circ, math.pi)
rad1 = segment(O, A); rad2 = segment(O, B); diam = segment(D, E)
draw(rad1); draw(rad2); draw(diam)
central = angle(A, O, B); mark_angle(central); central.label("100°")
O.label("O"); diam.label("8 cm")
""",
    "small_wedge": HEAD + """
A = point_on(circ, 10*math.pi/180); B = point_on(circ, 30*math.pi/180)
sa = segment(O, A); sb = segment(O, B); draw(sa); draw(sb)
w = angle(A, O, B); mark_angle(w); w.label("20°")
O.label("O"); A.label("A"); B.label("B")
""",
}
CENTER = re.compile(r'<circle[^>]*data-center="([^"]+)"[^>]*? cx="([\d.-]+)" cy="([\d.-]+)"')
POINT_LABEL = re.compile(r'<text[^>]*data-role="label-point" data-for="([^"]+)" data-bbox="([\d.,-]+)"[^>]*data-label-text="O"')


def _o_label_gap(script: str) -> float:
    """Edge-to-point distance between O's label box and O (the circle's centre)."""
    svg = asyncio.run(_run_from_script(script, SVGRenderer(embed_fonts=False))).svg
    centers = {m.group(1): (float(m.group(2)), float(m.group(3))) for m in CENTER.finditer(svg)}
    pid, bbox = POINT_LABEL.search(svg).groups()
    px, py = centers[pid]
    x0, y0, x1, y1 = map(float, bbox.split(","))
    return T._bbox_gap_to_point((x0, y0, x1, y1), px, py)


@pytest.mark.parametrize("name", list(SCRIPTS))
def test_the_centre_point_label_neither_covers_its_dot_nor_floats_away(name):
    gap = _o_label_gap(SCRIPTS[name])
    assert T._POINT_LABEL_MIN_GAP <= gap <= T._POINT_LABEL_MAX_GAP, gap


# --- the pass itself, on synthetic labels ----------------------------------------------

def _label(text: str, x: float, y: float, anchor: str = "middle", role: str = "label-point") -> T._LabelPlacement:
    return T._make_label_placement(x=x, y=y, text=text, color="black", anchor=anchor, attrs={"data-role": role})


def _obs(**kw) -> T._LabelObstacles:
    return T._LabelObstacles(kw.get("segments", []), kw.get("circles", []), kw.get("ellipses", []),
                             kw.get("boxes", []), kw.get("labels", []))


def _point_label(px: float, py: float, x: float, y: float, anchor: str = "start") -> T._LabelPlacement:
    lp = _label("P", x, y, anchor)
    lp.owner_point = (px, py)
    return lp


def test_a_point_label_on_its_dot_moves_beside_it():
    lp = _point_label(100, 100, 100, 100, "middle")  # centred on the dot
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert T._POINT_LABEL_MIN_GAP <= T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) <= T._POINT_LABEL_MAX_GAP


def test_a_point_label_far_from_its_point_comes_back():
    lp = _point_label(100, 100, 160, 100)
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) <= T._POINT_LABEL_MAX_GAP


def test_a_point_label_in_range_is_left_exactly_where_it_is():
    lp = _point_label(100, 100, 112, 100)  # a normal offset, start-anchored
    before = (lp.x, lp.y, lp.anchor)
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert (lp.x, lp.y, lp.anchor) == before


def test_a_re_seated_point_label_takes_the_least_crowded_slot():
    lp = _point_label(100, 100, 100, 100, "middle")
    lines = [(100.0, 100.0, 180.0, 100.0), (100.0, 100.0, 20.0, 100.0), (100.0, 100.0, 100.0, 20.0)]  # east, west, north
    other = _label("Q", 100, 112, "middle")  # sits where the south slot would be
    obs = _obs(segments=lines, labels=[lp, other])
    slots = []
    for dist in T._POINT_LABEL_RINGS:
        for k in range(8):
            angle = k * math.pi / 4
            ox, oy = T._angle_to_offset(angle, dist)
            slots.append(T._label_crowding(lp, 100 + ox, 100 + oy, obs, anchor=T._angle_to_anchor(angle)))
    T._reattach_labels([lp], obs)
    assert T._POINT_LABEL_MIN_GAP <= T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) <= T._POINT_LABEL_MAX_GAP
    assert T._label_crowding(lp, lp.x, lp.y, obs) == pytest.approx(min(slots))
    assert not T._bboxes_overlap(T._label_bbox(lp), T._label_bbox(other))


def test_a_re_seated_tall_label_stands_clear_of_its_dot():
    lp = _point_label(100, 100, 100, 100, "middle")
    lp.height_est = 20.0  # a tall mathtext glyph: at the plain offset its box would touch the dot
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) >= T._POINT_LABEL_MIN_GAP + 1 - 1e-6


def test_the_rings_setting_is_what_a_re_seated_label_is_tried_at(monkeypatch):
    near = _point_label(100, 100, 100, 100, "middle")
    T._reattach_labels([near], _obs(labels=[near]))
    monkeypatch.setattr(T, "_POINT_LABEL_RINGS", (T._LABEL_OFFSET * 1.5,))
    farther = _point_label(100, 100, 100, 100, "middle")
    T._reattach_labels([farther], _obs(labels=[farther]))
    assert T._bbox_gap_to_point(T._label_bbox(farther), 100, 100) > T._bbox_gap_to_point(T._label_bbox(near), 100, 100)


def test_a_label_a_little_far_in_clear_space_stays_rather_than_overlap_its_neighbours():
    lp = _point_label(100, 100, 100 + 30 + 4, 100)  # ~30 px from the point, nothing near it
    blockers = []
    for k in range(8):  # every slot around the point, on both rings, holds another label
        for dist in T._POINT_LABEL_RINGS:
            ox, oy = T._angle_to_offset(k * math.pi / 4, dist)
            blockers.append(_label("a", 100 + ox, 100 + oy, T._angle_to_anchor(k * math.pi / 4)))
    before = (lp.x, lp.y, lp.anchor)
    assert 20 < T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) <= T._POINT_LABEL_HARD_GAP
    T._reattach_labels([lp], _obs(labels=[lp, *blockers]))
    assert (lp.x, lp.y, lp.anchor) == before
    far = _point_label(100, 100, 100 + 70, 100)  # but a label beyond the hard gap always comes back
    T._reattach_labels([far], _obs(labels=[far, *blockers]))
    assert T._bbox_gap_to_point(T._label_bbox(far), 100, 100) <= T._POINT_LABEL_MAX_GAP


def test_a_re_seated_point_label_is_clear_when_a_clear_slot_exists():
    lp = _point_label(100, 100, 100, 100, "middle")
    lines = [(100.0, 100.0, 180.0, 100.0), (100.0, 100.0, 20.0, 100.0)]  # a horizontal line through the point
    T._reattach_labels([lp], _obs(segments=lines, labels=[lp]))
    assert T._label_crowding(lp, lp.x, lp.y, _obs(segments=lines, labels=[lp])) == 0


def _segment_label(x: float, y: float, slots=(0.5, 0.35, 0.65, 0.25, 0.75)) -> T._LabelPlacement:
    lp = _label("8 cm", x, y, role="label-segment")
    lp.attach_segment, lp.attach_normal, lp.attach_slots = (0.0, 0.0, 200.0, 0.0), (0.0, -1.0), slots
    return lp


def test_a_segment_label_far_from_its_line_comes_back_within_reach():
    lp = _segment_label(100, -40)  # 40 px above a horizontal segment
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert abs(T._bbox_center(lp)[1]) <= T._SEGMENT_LABEL_MAX_DRIFT


def test_a_segment_label_past_the_end_of_its_segment_comes_back():
    lp = _segment_label(260, -12)  # beside the line, but 30% past its end
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert 0.0 <= T._bbox_center(lp)[0] / 200.0 <= 1.0


def test_a_segment_label_within_reach_is_not_moved():
    lp = _segment_label(100, -12)
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert (lp.x, lp.y) == (100, -12)


def test_a_re_seated_segment_label_takes_the_free_side_and_slot():
    lp = _segment_label(100, -45)
    blocker = _label("100°", 100, -12, role="label-angle")  # fills the mid slot above the line
    T._reattach_labels([lp], _obs(labels=[lp, blocker]))
    assert not T._bboxes_overlap(T._label_bbox(lp), T._label_bbox(blocker))
    assert abs(T._bbox_center(lp)[1]) <= T._SEGMENT_LABEL_MAX_DRIFT


def test_an_explicit_pos_is_the_only_slot_a_re_seated_label_uses():
    lp = _segment_label(100, -45, slots=(0.25,))
    T._reattach_labels([lp], _obs(labels=[lp]))
    assert T._bbox_center(lp)[0] == pytest.approx(50.0)


# --- the crowding score sees ellipses and tick-label boxes -------------------------------

def test_crowding_counts_an_ellipse_a_tick_box_and_other_labels():
    lp = _label("x", 100, 100)
    assert T._label_crowding(lp, 100, 100, _obs()) == 0
    ellipse = (100.0, 100.0, 40.0, 25.0)  # (cx, cy, hr, vr); the label sits at the centre, 25 px from the ring
    assert T._label_crowding(lp, 100, 125, _obs(ellipses=[ellipse])) > 0  # on the boundary
    assert T._label_crowding(lp, 100, 100, _obs(ellipses=[ellipse])) == 0
    tick = (95.0, 95.0, 120.0, 110.0)
    assert T._label_crowding(lp, 100, 100, _obs(boxes=[tick])) > 0
    other = _label("y", 102, 100)
    assert T._label_crowding(lp, 100, 100, _obs(labels=[lp, other])) > 0
    assert (lp.x, lp.y, lp.anchor) == (100, 100, "middle")  # scoring leaves the label where it was


def test_crowding_ignores_the_labels_own_segment():
    lp = _label("8 cm", 100, -12, role="label-segment")
    seg = (0.0, 0.0, 200.0, 0.0)
    assert T._label_crowding(lp, 100, 0, _obs(segments=[seg])) > 0       # on the line: obstructed
    assert T._label_crowding(lp, 100, 0, _obs(segments=[seg]), skip_segment=seg) == 0


def test_a_label_a_little_far_is_pulled_back_when_only_lines_crowd_beside_its_point():
    """Lines do not hold a label away from its point (the star figure): only other labels do."""
    lp = _point_label(100, 100, 100 + 30 + 4, 100)
    spokes = [(100.0, 100.0, 100 + 90 * math.cos(k * math.pi / 4), 100 - 90 * math.sin(k * math.pi / 4)) for k in range(8)]
    T._reattach_labels([lp], _obs(segments=spokes, labels=[lp]))
    assert T._bbox_gap_to_point(T._label_bbox(lp), 100, 100) <= T._POINT_LABEL_MAX_GAP
