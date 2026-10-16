"""Gated solids guidance must name SILHOUETTE edges for the manual dimension labels.

The rule is derived from the projection's hidden corner h (never per view):
length (0,0,0)-(1,0,0); height (h0,0,0)-(h0,1,0); width (1-h0,0,0)-(1-h0,0,1).
Each of the three gated texts (recipe, structured, python_full) must state, for
side right and side left, exactly those edges (and so never the hidden
``e_000_001`` as the side-right width edge).
"""
from __future__ import annotations

import re

import pytest

from geometry_diagrams.ir.prism import projection_for
from geometry_diagrams.recipe.catalog import dsl_docs_for
from geometry_diagrams.strategies import instructions_python_full as ipf
from geometry_diagrams.strategies.instructions_structured import build_structured_instructions
from tests.test_prism_shading_labels import _silhouette_edges

SOLIDS = frozenset({"solids"})
VIEWS = ("oblique", "isometric")
SIDES = ("right", "left")


def _bits(b) -> str:
    return "".join(str(i) for i in b)


def _rule(side: str, view: str = "oblique") -> dict[str, tuple[str, str]]:
    h = projection_for(view, side).hidden_corner
    return {
        "length": ("000", "100"),
        "height": (f"{h[0]}00", f"{h[0]}10"),
        "width": (f"{1 - h[0]}00", f"{1 - h[0]}01"),
    }


def _silhouette(view: str, side: str) -> set[tuple[str, str]]:
    proj = projection_for(view, side)
    h = _bits(proj.hidden_corner)
    corners = {}
    for l in (0, 1):
        for ht in (0, 1):
            for w in (0, 1):
                key = f"{l}{ht}{w}"
                if key != h:
                    x, y = proj.offset(l, ht, w)
                    corners[key] = (float(x), float(y))
    return set(_silhouette_edges(corners))


@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("side", SIDES)
def test_rule_yields_silhouette_edges(view, side):
    sil = _silhouette(view, side)
    for dim, edge in _rule(side, view).items():
        assert tuple(sorted(edge)) in {tuple(sorted(e)) for e in sil}, (dim, edge, view, side)


def _edge_text(text, side):
    """(height, width) edge ids stated for ``side`` in a guidance text."""
    eid = r"e_([01]{3})_([01]{3})"
    m = re.search(rf"side {side}[^:]*: height `?P_{eid}`?, width `?P_{eid}`?", text)
    assert m, f"no 'side {side}: height ..., width ...' statement"
    return (m[1], m[2]), (m[3], m[4])


def _corner_text(text, side):
    c = r"corner\(\s*([01])\s*,\s*([01])\s*,\s*([01])\s*\)"
    m = re.search(rf"side {side}[^:]*: height {c}-{c}, width {c}-{c}", text)
    assert m, f"no 'side {side}: height ..., width ...' corner statement"
    g = m.groups()
    return tuple(("".join(g[i:i + 3]), "".join(g[i + 3:i + 6])) for i in (0, 6))


def _python_full_text():
    text = ipf.build_python_full_instructions(features=SOLIDS)
    return re.sub(r"\s+", " ", text)


def _flat(text):
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("side", SIDES)
def test_gated_texts_name_the_silhouette_height_and_width_edges(side):
    rule = _rule(side)
    want = (rule["height"], rule["width"])
    assert _edge_text(_flat(dsl_docs_for(SOLIDS)), side) == want
    assert _edge_text(_flat(build_structured_instructions(SOLIDS)), side) == want
    assert _corner_text(_python_full_text(), side) == want


def test_gated_texts_state_the_length_edge_and_never_offer_the_hidden_width_edge():
    for text in (_flat(dsl_docs_for(SOLIDS)), _flat(build_structured_instructions(SOLIDS))):
        assert "P_e_000_100" in text
        # e_000_001 may only be the side-left width edge
        for m in re.finditer(r"e_000_001", text):
            assert "side left" in text[max(0, m.start() - 80):m.start()]
    py = _python_full_text()
    assert "corner(0, 0, 0), box.corner(1, 0, 0))` is the length edge" in py
