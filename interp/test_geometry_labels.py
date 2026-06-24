"""
Offline tests for ground-truth geometry extraction — no model/GPU, runs the real
geometry pipeline (sympy) on hand-built and catalog constructions.

    interp/.venv/bin/python interp/test_geometry_labels.py
"""
from __future__ import annotations

import math
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.geometry_labels import ground_truth

# self-contained: equilateral triangle + midpoint of AB + perpendicular from C
SELF_CONTAINED = {
    "mode": "abstract",
    "construction": [
        {"op": "triangle", "id": "T", "vertices": ["A", "B", "C"],
         "spec": {"side_AB": 5, "side_BC": 5, "side_CA": 5}},
        {"op": "midpoint", "id": "M", "of": ["A", "B"]},
        {"op": "perpendicular", "id": "L", "to_line": ["A", "B"], "through": "C"},
    ],
}


def test_entity_relations_from_defs():
    gt = ground_truth(SELF_CONTAINED)
    assert gt["ok"], gt["stage"]
    rels = gt["entity_relations"]
    assert rels.get("M") == "midpoint", rels
    assert rels.get("L") == "perpendicular", rels
    print(f"ok  entity_relations {rels}")


def test_point_coords_are_truthful():
    gt = ground_truth(SELF_CONTAINED)
    c = gt["point_coords"]
    for p in ("A", "B", "C", "M"):
        assert p in c, c
    # M must be the exact midpoint of A and B
    mx = (c["A"][0] + c["B"][0]) / 2
    my = (c["A"][1] + c["B"][1]) / 2
    assert math.isclose(c["M"][0], mx, abs_tol=1e-6), c
    assert math.isclose(c["M"][1], my, abs_tol=1e-6), c
    print(f"ok  point_coords M={[round(v,2) for v in c['M']]} = midpoint(A,B)")


def test_failures_degrade_gracefully():
    assert ground_truth(None)["stage"] == "parse"
    assert ground_truth({"not": "a recipe"})["stage"] == "validate"
    # a construction that lowers but references an undefined object -> partial
    bad = {"mode": "abstract", "construction": [
        {"op": "midpoint", "id": "M", "of": ["A", "B"]}]}  # A,B never defined
    gt = ground_truth(bad)
    assert gt["ok"] is False
    print(f"ok  graceful degradation (bad -> stage={gt['stage']})")


def test_catalog_example_coords():
    from recipe.catalog import load_recipe
    gt = ground_truth(load_recipe("cyclic_quadrilateral", catalog="default").example)
    assert gt["ok"], gt["stage"]
    assert len(gt["point_coords"]) >= 4, gt["point_coords"]
    print(f"ok  catalog cyclic_quadrilateral -> {len(gt['point_coords'])} point coords")


if __name__ == "__main__":
    test_entity_relations_from_defs()
    test_point_coords_are_truthful()
    test_failures_degrade_gracefully()
    test_catalog_example_coords()
    print("\nALL GEOMETRY-LABEL TESTS PASSED")
