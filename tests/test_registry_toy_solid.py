"""Acceptance test of the derived-entity registry's solid hooks.

A test-only toy solid (``toy_box``: a square "box" whose compiled object is
a plain non-SymPy ``ToyBox``) is registered here, through the registry
alone, without editing any consumer module. Each test then shows one
consumer reaching the toy through its hook:

- compile (``compile``) and the toy's derived points/edges/faces,
- the query tool's dispatch (``query_type`` + ``query``) and the extra
  ``true_length`` of a segment query (``true_length``),
- a check kind the toy owns (``evaluate_checks``) and its check-time warning
  (``check_warnings``),
- the edge-label placement of both renderers (``label_away_from``),
- run_ir_pipeline's warnings list (``pipeline_warnings``),
- the SymPy-validation bypass and the angle-mark pass skip for its faces
  (``trusted_faces``),
- pydsl ``label_text(centroid_of=...)`` (derived from ``position``),
- the recipe lowerer's auto canvas fit (``canvas_extent``).

The registry is global state: the ``toy`` fixture registers the toy and
always unregisters it, and asserts nothing of it is left behind.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from typing import Any, Literal

import pytest
import sympy as sp
import sympy.geometry as spg

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import check_render_angles, run_checks
from geometry_diagrams.ir.derived import REGISTRY, DerivedConstruction
from geometry_diagrams.ir.queries import query_length
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.ir.to_svg import ir_to_svg
from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.ir.to_tikz import ir_to_tikz
from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
from geometry_diagrams.strategies.structured import dispatch_query


# --- the toy kind -----------------------------------------------------------------

class ToyBoxDef(ir.DefBase):
    """A square of side ``size`` with its bottom-left corner at ``origin``."""
    kind: Literal["toy_box"] = "toy_box"
    origin: str
    size: float


class ToyBoxCheck(ir.CheckBase):
    kind: Literal["toy_size_equals"] = "toy_size_equals"
    box: str
    expected: float


class ToyBox:
    """The toy's compiled object: deliberately not a SymPy shape."""

    def __init__(self, origin: spg.Point, size: sp.Expr) -> None:
        self.origin, self.size = origin, size

    @property
    def center(self) -> tuple[float, float]:
        return (float(self.origin.x + self.size / 2), float(self.origin.y + self.size / 2))


def _corner_ids(stmt: ToyBoxDef) -> dict[str, str]:
    return {name: f"{stmt.id}_{name}" for name in ("c1", "c2", "c3", "mid")}


def _register(stmt: ToyBoxDef, obj: Any, sym: dict[str, Any]) -> None:
    if type(obj) is not ToyBox:
        return
    o, s = obj.origin, obj.size
    pts = {"c1": (s, 0), "c2": (s, s), "c3": (0, s), "mid": (s / 2, 0)}
    for name, cid in _corner_ids(stmt).items():
        dx, dy = pts[name]
        sym.setdefault(cid, spg.Point(o.x + dx, o.y + dy))


def _synthesize(stmt: ToyBoxDef) -> list[Any]:
    c = _corner_ids(stmt)
    return [
        ir.Segment(id=f"{stmt.id}_base", a=stmt.origin, b=c["c1"]),
        ir.Segment(id=f"{stmt.id}_top", a=c["c3"], b=c["c2"]),
        ir.Segment(id=f"{stmt.id}_diag", a=stmt.origin, b=c["c2"]),
        # ``mid`` is collinear with its neighbours: SymPy's validating
        # Polygon constructor would drop it (a compile error); a trusted face
        # keeps all five vertices.
        ir.Polygon(id=f"{stmt.id}_face", points=[stmt.origin, c["mid"], c["c1"], c["c2"], c["c3"]]),
    ]


def _toy_of_segment(sym: dict[str, Any], seg_id: str, suffix: str) -> ToyBox | None:
    if not seg_id.endswith(suffix):
        return None
    obj = sym.get(seg_id[: -len(suffix)])
    return obj if type(obj) is ToyBox else None


def _true_length(sym: dict[str, Any], seg_id: str) -> sp.Expr | None:
    box = _toy_of_segment(sym, seg_id, "_diag")
    return None if box is None else box.size * sp.sqrt(3)


def _evaluate_size(check: ToyBoxCheck, sym: dict[str, Any], tol: float) -> tuple[bool, str]:
    size = float(sym[check.box].size)
    ok = abs(size - check.expected) <= tol
    return ok, "" if ok else f"toy box {check.box!r} size {size:g} != {check.expected:g}"


def _check_warnings(check: Any, sym: dict[str, Any]) -> list[str]:
    seg = getattr(check, "seg", None)
    if check.kind == "distance_equals" and _toy_of_segment(sym, seg, "_diag") is not None:
        return [f"toy check warning: {seg!r} measured flat"]
    return []


def _label_away_from(sym: dict[str, Any], seg_id: str) -> tuple[float, float] | None:
    box = _toy_of_segment(sym, seg_id, "_top")
    return None if box is None else box.center


def _pipeline_warnings(diagram: Any, sym: dict[str, Any]) -> list[str]:
    return [f"toy pipeline warning: {k}" for k, v in sym.items() if type(v) is ToyBox]


def _canvas_extent(stmt: ToyBoxDef, point_xy: Any) -> list[tuple[float, float]]:
    origin = point_xy(stmt.origin)
    if origin is None:
        return []
    # Deliberately far out, so the test can see the canvas reach it.
    return [(origin[0] + 10 * stmt.size, origin[1] + 10 * stmt.size)]


TOY_ENTRY = DerivedConstruction(
    "toy_box", ("{id}_c{i}", "{id}_mid", "{id}_base", "{id}_top", "{id}_diag", "{id}_face"),
    lambda stmt: list(_corner_ids(stmt).values()),
    _register,
    compile=lambda stmt, ref, ev: ToyBox(ref(stmt.origin), sp.S(stmt.size)),
    object_type=ToyBox,
    position=lambda obj: obj.center if type(obj) is ToyBox else None,
    synthesize=_synthesize,
    query_type="toy_box",
    query=lambda obj: {"size": float(obj.size), "area": float(obj.size ** 2)},
    true_length=_true_length,
    evaluate_checks={"toy_size_equals": _evaluate_size},
    check_warnings=_check_warnings,
    label_away_from=_label_away_from,
    pipeline_warnings=_pipeline_warnings,
    canvas_extent=_canvas_extent,
    trusted_faces=True,
)


@pytest.fixture
def toy():
    REGISTRY.register(TOY_ENTRY)
    try:
        yield TOY_ENTRY
    finally:
        REGISTRY.unregister("toy_box")
        assert REGISTRY.get(ToyBoxDef(id="T", origin="O", size=1)) is None
        assert REGISTRY.query_entry("toy_box") is None
        assert REGISTRY.check_evaluator("toy_size_equals") is None


def _diagram(render: list[Any] = (), checks: list[Any] = (), extra: list[Any] = ()) -> ir.DiagramIR:
    """O at (1, 1) and a toy box T of size 2 (spans x 1..3, y 1..3). The toy
    definition is appended after validation: it is not in the DefStmt union
    (adding it would mean editing ir.py), and nothing downstream re-validates."""
    diagram = ir.DiagramIR(
        define=[ir.PointFixed(id="O", x=1, y=1), *extra],
        render=list(render),
        canvas=ir.Canvas(xmin=-2, xmax=6, ymin=-2, ymax=6),
    )
    diagram.define.insert(1, ToyBoxDef(id="T", origin="O", size=2))
    diagram.checks.extend(checks)
    return diagram


# --- tests ------------------------------------------------------------------------

def test_registry_is_clean_without_the_fixture():
    assert REGISTRY.get(ToyBoxDef(id="T", origin="O", size=1)) is None
    assert REGISTRY.query_entry("toy_box") is None


def test_toy_compiles_through_its_hook_with_derived_entities(toy):
    sym = compile_defs(_diagram())
    assert type(sym["T"]) is ToyBox
    assert sym["T_c2"] == spg.Point(3, 3)
    assert isinstance(sym["T_base"], spg.Segment)
    assert REGISTRY.entry_for_object(sym["T"]) is toy


def test_trusted_face_skips_sympy_validation(toy):
    sym = compile_defs(_diagram())
    # The collinear ``mid`` vertex survives: the face was not built by
    # SymPy's validating constructor (which would have dropped it).
    assert len(sym["T_face"].vertices) == 5


def test_query_dispatch_reaches_the_toy_query(toy):
    sym = compile_defs(_diagram())
    assert json.loads(dispatch_query(sym, "toy_box", {"toy_box": "T"})) == {"size": 2.0, "area": 4.0}
    assert json.loads(dispatch_query(sym, "toy_box", {"id": "T"}))["size"] == 2.0
    assert json.loads(dispatch_query(sym, "toy_box", {"id": "O"})) == {
        "error": "'O' is not a ToyBox (got Point2D)"
    }


def test_length_query_gains_the_toy_true_length(toy):
    sym = compile_defs(_diagram())
    out = query_length(sym, "T_diag")
    assert out["true_length"] == pytest.approx(2 * 3 ** 0.5)
    assert "true_length" not in query_length(sym, "T_base")


def test_toy_check_kind_and_check_warning(toy):
    sym = compile_defs(_diagram())
    warnings: list[str] = []
    results = run_checks(
        [ToyBoxCheck(box="T", expected=2), ToyBoxCheck(box="T", expected=3),
         ir.DistanceEquals(seg="T_diag", expected=2)],
        sym, warnings=warnings,
    )
    assert [r.passed for r in results[:2]] == [True, False]
    assert results[1].message == "toy box 'T' size 2 != 3"
    assert warnings == ["toy check warning: 'T_diag' measured flat"]


def test_pipeline_warnings_reach_run_ir_pipeline(toy):
    diagram = _diagram(
        render=[ir.Draw(obj="T_face")],
        checks=[ir.DistanceEquals(seg="T_diag", expected=2 * 2 ** 0.5)],
    )
    result = asyncio.run(run_ir_pipeline(diagram, SVGRenderer()))
    assert "toy pipeline warning: T" in result.warnings
    assert "toy check warning: 'T_diag' measured flat" in result.warnings


def _top_label(entry: DerivedConstruction) -> tuple[tuple[float, float], float, str]:
    """Render a label on the toy's top edge with ``entry`` registered (and
    always unregistered again): (SVG label bbox top and bottom y, SVG line
    y, the TikZ line drawing the label)."""
    REGISTRY.register(entry)
    try:
        # Five points above the top edge (the box contributes three below
        # it), so the default fewer-points rule picks the side BELOW.
        crowd = [ir.PointFixed(id=f"X{i}", x=1.2 + 0.4 * i, y=4) for i in range(5)]
        diagram = _diagram(
            render=[ir.Draw(obj="T_top"), ir.LabelSegment(seg="T_top", text="t")], extra=crowd,
        )
        sym = compile_defs(diagram)
        svg = ir_to_svg(diagram, sym, [])
        tikz = ir_to_tikz(diagram, sym, warnings=[])
    finally:
        REGISTRY.unregister("toy_box")
    text = re.search(r'<text[^>]*data-for="T_top"[^>]*>', svg)
    assert text is not None, svg
    _, top, _, bottom = map(float, re.search(r'data-bbox="([^"]+)"', text.group()).group(1).split(","))
    line = re.search(r'<line[^>]*data-ir-id="T_top"[^>]*>', svg)
    assert line is not None, svg
    line_y = float(re.search(r' y1="([-0-9.]+)"', line.group()).group(1))
    tikz_line = next(row for row in tikz.splitlines() if "{t}" in row or "$t$" in row)
    return (top, bottom), line_y, tikz_line


def test_edge_label_is_placed_by_the_toy_hook():
    # The top edge runs along y = 3 with the box below it and a crowd of
    # points above it. The default rule (the side with fewer points) puts the
    # label below the line, inside the box; the toy's label_away_from hook
    # names the box center, so the label goes above the line instead. Compared against the same toy with
    # only that hook removed, each label box lies wholly on its own side of
    # the line (SVG y grows downward), so no overlap nudge can fake it.
    with_hook = _top_label(TOY_ENTRY)
    without_hook = _top_label(dataclasses.replace(TOY_ENTRY, label_away_from=None))
    (top, bottom), line_y, tikz_with = with_hook
    assert bottom < line_y, with_hook
    (top_default, _), line_y_default, tikz_without = without_hook
    assert line_y_default == line_y and top_default > line_y, without_hook
    # Label centers are more than 1.5 label heights apart (measured: about
    # 25 px for a 14 px label), far beyond a sub-pixel nudge.
    assert top_default - top > 1.5 * (bottom - top)
    assert "above" in tikz_with and "above" not in tikz_without


def _angle_diagram(face: Any) -> ir.DiagramIR:
    # M lies on the face's bottom side, Q on its left side; neither is a face
    # vertex, so only the geometric side pass can connect them to O.
    diagram = _diagram(
        render=[ir.MarkAngles(angles=[ir.AngleSpec(a="M", o="O", b="Q")])],
        extra=[ir.PointFixed(id="M", x=1.5, y=1), ir.PointFixed(id="Q", x=1, y=1.5), *face],
    )
    return diagram


def test_angle_pass_skips_trusted_faces(toy):
    diagram = _angle_diagram([])
    assert check_render_angles(diagram, compile_defs(diagram)) != []


def test_angle_pass_still_uses_an_ordinary_polygon(toy):
    diagram = _angle_diagram([
        ir.PointFixed(id="A1", x=3, y=1), ir.PointFixed(id="A2", x=3, y=3),
        ir.PointFixed(id="A3", x=1, y=3), ir.Polygon(id="sq", points=["O", "A1", "A2", "A3"]),
    ])
    assert check_render_angles(diagram, compile_defs(diagram)) == []


def test_pydsl_label_text_accepts_a_registered_handle(toy):
    from dataclasses import dataclass

    from geometry_diagrams.pydsl.api import label_text, point
    from geometry_diagrams.pydsl.builder import new_builder_context

    @dataclass
    class ToyHandle:  # a minimal test-only handle: just the id
        id: str

    with new_builder_context() as builder:
        o = point(1, 1)
        builder._add(ToyBoxDef(id="T", origin=o.id, size=2))
        label_text("V", centroid_of=ToyHandle("T"))
        # An id naming an ordinary (unregistered) kind is still rejected.
        with pytest.raises(ValueError, match="not supported for centroid_of"):
            label_text("W", centroid_of=ToyHandle(o.id))
        # (builder.build() would re-validate the toy definition against the
        # DefStmt union, so read the recorded render operations directly.)
        recorded = list(builder._render)
    assert [op.centroid_of for op in recorded if op.kind == "label_free_text"] == ["T"]


def test_canvas_extent_feeds_the_recipe_canvas_fit(toy):
    from geometry_diagrams.recipe.dsl import PointOp
    from geometry_diagrams.recipe.lower import _Lowerer

    def canvas(with_toy: bool) -> ir.Canvas:
        lw = _Lowerer()
        lw._lower_op(PointOp(id="O", coords=[1, 1]))
        if with_toy:
            lw._add(ToyBoxDef(id="T", origin="O", size=2))
        return lw._auto_canvas()

    assert canvas(False).xmax == 2.0
    fitted = canvas(True)
    assert (fitted.xmax, fitted.ymax) == (22.0, 22.0)
