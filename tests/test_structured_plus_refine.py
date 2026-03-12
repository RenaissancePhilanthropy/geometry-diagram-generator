from __future__ import annotations

import asyncio

from strategies.structured import StructureStrategy, StructuredRunResult
from strategies.structured_plus_refine import (
    StructuredPlusRefineStrategy,
    _refinement_constraints_satisfied,
)


_ORIGINAL_TIKZ = r"""
\tkzInit[xmin=-1,xmax=5,ymin=-1,ymax=5]
\draw[gray!35,thin,step=1] (-1,-1) grid (5,5);
\draw[->,thick] (-1,0) -- (5,0) node[right] {$x$};
\draw[->,thick] (0,-1) -- (0,5) node[above] {$y$};
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzDrawPolygon(A,B,C)
\tkzLabelPoint[left](A){$A$}
\tkzLabelPoint[right](B){$B$}
\tkzLabelPoint[above](C){$C$}
"""

_REFINED_TIKZ = r"""
\tkzInit[xmin=-1,xmax=5,ymin=-1,ymax=5]
\draw[gray!35,thin,step=1] (-1,-1) grid (5,5);
\draw[->,thick] (-1,0) -- (5,0) node[right] {$x$};
\draw[->,thick] (0,-1) -- (0,5) node[above] {$y$};
\tkzDefPoint(0,0){A}
\tkzDefPoint(4,0){B}
\tkzDefPoint(0,3){C}
\tkzDrawPolygon[thick](A,B,C)
\tkzMarkRightAngle(B,A,C)
\tkzLabelPoint[below left](A){$A$}
\tkzLabelPoint[below right](B){$B$}
\tkzLabelPoint[above](C){$C$}
"""


def test_refinement_constraints_accept_preserved_geometry():
    assert _refinement_constraints_satisfied(_ORIGINAL_TIKZ, _REFINED_TIKZ) is True


def test_refinement_constraints_reject_moved_point():
    moved = _REFINED_TIKZ.replace(r"\tkzDefPoint(4,0){B}", r"\tkzDefPoint(5,0){B}")
    assert _refinement_constraints_satisfied(_ORIGINAL_TIKZ, moved) is False


def test_refinement_constraints_reject_removed_grid():
    no_grid = _REFINED_TIKZ.replace("\\draw[gray!35,thin,step=1] (-1,-1) grid (5,5);\n", "")
    assert _refinement_constraints_satisfied(_ORIGINAL_TIKZ, no_grid) is False


def test_refinement_constraints_reject_removed_axes():
    no_axes = _REFINED_TIKZ.replace("\\draw[->,thick] (0,-1) -- (0,5) node[above] {$y$};\n", "")
    assert _refinement_constraints_satisfied(_ORIGINAL_TIKZ, no_axes) is False


def test_strategy_falls_back_when_refinement_breaks_constraints(monkeypatch):
    base = StructuredRunResult(diagram_ir=None, tikz=_ORIGINAL_TIKZ, svg="<svg>base</svg>")

    async def fake_structured_run(self, prompt: str, model: str):
        return base

    async def fake_refine(self, prompt: str, tikz: str, model: str):
        moved = _REFINED_TIKZ.replace(r"\tkzDefPoint(4,0){B}", r"\tkzDefPoint(5,0){B}")
        return moved, "<svg>refined</svg>"

    monkeypatch.setattr(StructureStrategy, "run", fake_structured_run)
    monkeypatch.setattr(StructuredPlusRefineStrategy, "_run_refinement", fake_refine)

    result = asyncio.run(StructuredPlusRefineStrategy().run("prompt"))
    assert result.tikz == _ORIGINAL_TIKZ
    assert result.svg == "<svg>base</svg>"


def test_strategy_accepts_safe_refinement(monkeypatch):
    base = StructuredRunResult(diagram_ir=None, tikz=_ORIGINAL_TIKZ, svg="<svg>base</svg>")

    async def fake_structured_run(self, prompt: str, model: str):
        return base

    async def fake_refine(self, prompt: str, tikz: str, model: str):
        return _REFINED_TIKZ, "<svg>refined</svg>"

    monkeypatch.setattr(StructureStrategy, "run", fake_structured_run)
    monkeypatch.setattr(StructuredPlusRefineStrategy, "_run_refinement", fake_refine)

    result = asyncio.run(StructuredPlusRefineStrategy().run("prompt"))
    assert result.tikz == _REFINED_TIKZ
    assert result.svg == "<svg>refined</svg>"


def test_strategy_falls_back_when_refinement_returns_none(monkeypatch):
    base = StructuredRunResult(diagram_ir=None, tikz=_ORIGINAL_TIKZ, svg="<svg>base</svg>")

    async def fake_structured_run(self, prompt: str, model: str):
        return base

    async def fake_refine(self, prompt: str, tikz: str, model: str):
        return None

    monkeypatch.setattr(StructureStrategy, "run", fake_structured_run)
    monkeypatch.setattr(StructuredPlusRefineStrategy, "_run_refinement", fake_refine)

    result = asyncio.run(StructuredPlusRefineStrategy().run("prompt"))
    assert result.tikz == _ORIGINAL_TIKZ
    assert result.svg == "<svg>base</svg>"
