"""
Generate example SVG diagrams for the README using the IR pipeline.
Run from the project root: uv run python docs/gen_examples.py
"""
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ir.ir import (
    DiagramIR, Canvas,
    PointFixed, Segment, Triangle, Polygon, PolygonExterior,
    PointTriangleCenter, CircleCenterPoint, CircleThrough3,
    LineThrough, PointMidpoint, PointFoot,
    Draw, DrawPoints, LabelPoint, MarkRightAngles, Fill,
)
from ir.to_sympy import compile_defs
from ir.to_tikz import ir_to_tikz
from util.tikz_renderer import render_tikz

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")


def add_white_background(svg: str) -> str:
    """Insert a white rect covering the full viewBox, for dark-mode readability."""
    m = re.search(r"viewBox='([^']+)'", svg)
    if not m:
        return svg
    x, y, w, h = m.group(1).split()
    rect = f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='white'/>"
    return svg.replace("<g id='page1'>", f"<g id='page1'>{rect}", 1)


def save(name: str, svg: str) -> None:
    svg_path = os.path.join(OUT, f"{name}.svg")
    with open(svg_path, "w") as f:
        f.write(add_white_background(svg))
    print(f"  Saved {svg_path}")


def render(diagram: DiagramIR) -> str:
    sym = compile_defs(diagram)
    tikz = ir_to_tikz(diagram, sym)
    return render_tikz(tikz)


# ── 1. Pythagorean theorem ──────────────────────────────────────────────────
# Right triangle with colored squares on each side
print("Generating: pythagorean_theorem")
pyth = DiagramIR(
    canvas=Canvas(xmin=-1.5, xmax=7, ymin=-4.5, ymax=5),
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
        # Squares on each side, placed exterior to the triangle
        PolygonExterior(id="sq_AB", a="A", b="B", ref="C", sides=4),
        PolygonExterior(id="sq_BC", a="B", b="C", ref="A", sides=4),
        PolygonExterior(id="sq_CA", a="C", b="A", ref="B", sides=4),
    ],
    styles={
        "blue_fill":   {"fill": "blue!30",   "opacity": "0.7"},
        "red_fill":    {"fill": "red!30",    "opacity": "0.7"},
        "green_fill":  {"fill": "green!40",  "opacity": "0.7"},
        "tri_fill":    {"fill": "gray!20",   "opacity": "0.9"},
    },
    render=[
        Fill(obj="sq_AB",  style="blue_fill"),
        Fill(obj="sq_BC",  style="red_fill"),
        Fill(obj="sq_CA",  style="green_fill"),
        Fill(obj="T",      style="tri_fill"),
        Draw(obj="sq_AB"),
        Draw(obj="sq_BC"),
        Draw(obj="sq_CA"),
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        MarkRightAngles(angles=[{"a": "B", "o": "A", "b": "C"}]),
        DrawPoints(points=["A", "B", "C"]),
        LabelPoint(p="A", text="$A$", pos="above right"),
        LabelPoint(p="B", text="$B$", pos="below right"),
        LabelPoint(p="C", text="$C$", pos="above left"),
    ],
)
save("pythagorean_theorem", render(pyth))


# ── 2. Circumscribed + inscribed circles ────────────────────────────────────
print("Generating: triangle_circles")
circles = DiagramIR(
    canvas=Canvas(xmin=-4.5, xmax=5.5, ymin=-4, ymax=5.5),
    define=[
        PointFixed(id="A", x=0,    y=4.5),
        PointFixed(id="B", x=-3.5, y=-1.5),
        PointFixed(id="C", x=4,    y=-1),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        PointTriangleCenter(id="I", tri="T", which="incenter"),
        CircleCenterPoint(id="circumcircle", center="O", through="A"),
        Segment(id="BC_seg", a="B", b="C"),
        PointFoot(id="I_foot", source="I", onto="BC_seg"),
        CircleCenterPoint(id="incircle", center="I", through="I_foot"),
    ],
    styles={
        "tri_fill":      {"fill": "orange!15", "opacity": "1"},
        "circ_style":    {"color": "blue",     "thick": True},
        "incirc_style":  {"color": "red",      "thick": True},
    },
    render=[
        Fill(obj="T", style="tri_fill"),
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        Draw(obj="circumcircle", style="circ_style"),
        Draw(obj="incircle",     style="incirc_style"),
        DrawPoints(points=["A", "B", "C", "O", "I"]),
        LabelPoint(p="A", text="$A$", pos="above"),
        LabelPoint(p="B", text="$B$", pos="below left"),
        LabelPoint(p="C", text="$C$", pos="below right"),
        LabelPoint(p="O", text="$O$", pos="above right"),
        LabelPoint(p="I", text="$I$", pos="above left"),
    ],
)
save("triangle_circles", render(circles))


# ── 3. Euler line ───────────────────────────────────────────────────────────
print("Generating: euler_line")
euler = DiagramIR(
    canvas=Canvas(xmin=-4, xmax=6, ymin=-3, ymax=6.5),
    define=[
        PointFixed(id="A", x=0, y=6),
        PointFixed(id="B", x=-3, y=-1),
        PointFixed(id="C", x=5, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        PointTriangleCenter(id="G", tri="T", which="centroid"),
        PointTriangleCenter(id="H", tri="T", which="orthocenter"),
        CircleCenterPoint(id="circumcircle", center="O", through="A"),
        LineThrough(id="euler", p="O", q="G"),
    ],
    styles={
        "tri_fill":    {"fill": "gray!10",   "opacity": "1"},
        "circ_style":  {"color": "blue!60",  "thick": True},
        "euler_style": {"color": "red",      "thick": True, "dashed": True},
        "O_style":     {"color": "blue"},
        "G_style":     {"color": "teal"},
        "H_style":     {"color": "red"},
    },
    render=[
        Fill(obj="T", style="tri_fill"),
        Draw(obj="circumcircle", style="circ_style"),
        Draw(obj="euler",        style="euler_style"),
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        DrawPoints(points=["A", "B", "C"]),
        DrawPoints(points=["O"], style="O_style"),
        DrawPoints(points=["G"], style="G_style"),
        DrawPoints(points=["H"], style="H_style"),
        LabelPoint(p="A", text="$A$", pos="above"),
        LabelPoint(p="B", text="$B$", pos="below left"),
        LabelPoint(p="C", text="$C$", pos="right"),
        LabelPoint(p="O", text="$O$", pos="above left"),
        LabelPoint(p="G", text="$G$", pos="above right"),
        LabelPoint(p="H", text="$H$", pos="below right"),
    ],
)
save("euler_line", render(euler))

print("Done.")
