"""
Offline tests for the cross-format transfer pipeline (no model needed).

Run:  interp/.venv/bin/python interp/transfer/test_transfer.py
"""
from __future__ import annotations

import json
import pathlib
import random
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.transfer.build_corpus import (  # noqa: E402
    FORMATS, TEMPLATES, build_figure, render_english)
from interp.transfer.capture_reading import spans_to_positions  # noqa: E402
from interp.transfer.probe_transfer import (  # noqa: E402
    LABELERS, _id_positions_spans, split_figures)

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "ok" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def test_templates_produce_valid_figures():
    print("templates produce valid figures with exact spans:")
    rng = random.Random(7)
    for tname in TEMPLATES:
        rec = None
        for _ in range(8):
            rec = build_figure(tname, rng)
            if rec:
                break
        check(f"{tname}: valid figure", rec is not None)
        if not rec:
            continue
        rels = rec["ground_truth"]["entity_relations"]
        check(f"{tname}: has relation entities", len(rels) >= 1, str(rels))
        for fmt in FORMATS:
            text, spans = rec["formats"][fmt]
            exact = all(text[s:e] == eid
                        for eid, sp in spans.items() for s, e in sp)
            check(f"{tname}/{fmt}: spans exact", exact)
        # relation-bearing entities must be findable in recipe + english
        for fmt in ("recipe", "english"):
            _, spans = rec["formats"][fmt]
            covered = [e for e in rels if spans.get(e)]
            check(f"{tname}/{fmt}: relation entities covered",
                  len(covered) == len(rels),
                  f"{sorted(rels)} vs {covered}")


def test_svg_spans_avoid_path_commands():
    print("svg spans only inside <text> elements (path M/L/C/A immune):")
    rng = random.Random(3)
    rec = None
    for _ in range(8):
        rec = build_figure("midsegment", rng)
        if rec:
            break
    assert rec
    text, spans = rec["formats"]["svg"]
    ok = True
    for eid, sp in spans.items():
        for s, e in sp:
            # every span must be inside a text element, not a path d= attr
            before = text.rfind("<text", 0, s)
            close = text.find("</text>", s)
            openpath = text.rfind("<path", 0, s)
            if before == -1 or close == -1 or openpath > before:
                ok = False
    check("all svg spans inside <text>", ok)


def test_spans_to_positions():
    print("spans_to_positions:")
    #        0123456789
    # text: "Let M be."   token offsets: [0,3],[3,5],[5,8],[8,9]
    offsets = [[0, 3], [3, 5], [5, 8], [8, 9]]
    pos = spans_to_positions({"M": [[4, 5]]}, offsets)
    check("token covering span found", pos == [1], str(pos))
    pos = spans_to_positions({"X": []}, offsets)
    check("empty spans -> no positions", pos == [])
    # zero-width offsets skipped
    pos = spans_to_positions({"M": [[4, 5]]}, [[0, 3], [4, 4], [3, 5]])
    check("zero-width tokens skipped", pos == [2], str(pos))


def _fake_record():
    text = 'the point "Q" and vertex "Z"'
    # tokens: crude 4-char split with offsets
    offsets = [[i, min(i + 4, len(text))] for i in range(0, len(text), 4)]
    return {
        "pid": "fig_0001",
        "offsets": offsets,
        "tokens": ["t"] * len(offsets),
        "meta": {
            "id_spans": {"Q": [[11, 12]], "Z": [[26, 27]]},
            "is_special": [0] * len(offsets),
            "ground_truth": {
                "entity_relations": {"Q": "midpoint"},
                "point_coords": {"Q": [0.0, 0.0], "Z": [2.0, 4.0]},
                "vertex_angles": {"Z": 63.0},
            },
        },
    }


def test_labelers():
    print("span-based labelers:")
    rec = _fake_record()
    pos_q = _id_positions_spans(rec, "Q")
    check("id positions from spans", pos_q == [2], str(pos_q))
    rel, _ = LABELERS["entity_relation"]
    labels = rel(rec)
    check("entity_relation labels", labels == {2: "midpoint"}, str(labels))
    coord, _ = LABELERS["point_coord"]
    labels = coord(rec)
    check("point_coord normalized to bbox",
          labels.get(2) == [0.0, 0.0] and 6 in labels, str(labels))
    ang, _ = LABELERS["angle"]
    labels = ang(rec)
    check("angle labels", labels == {6: [63.0]}, str(labels))


def test_split_is_figure_level():
    print("figure-level split:")
    groups = [f"fig_{i}" for i in range(50)] * 3   # 3 records per figure
    tr, te = split_figures(groups, 0.3, seed=1)
    check("disjoint", not (tr & te))
    check("sizes ~70/30", len(te) == 15 and len(tr) == 35,
          f"{len(tr)}/{len(te)}")
    tr2, te2 = split_figures(groups, 0.3, seed=1)
    check("deterministic per seed", tr == tr2 and te == te2)
    tr3, _ = split_figures(groups, 0.3, seed=2)
    check("varies across seeds", tr != tr3)


if __name__ == "__main__":
    test_templates_produce_valid_figures()
    test_svg_spans_avoid_path_commands()
    test_spans_to_positions()
    test_labelers()
    test_split_is_figure_level()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
