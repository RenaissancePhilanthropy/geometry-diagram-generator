"""
Generate example SVG/PNG diagrams for the README using the IR pipeline.
Run from the project root: python docs/gen_examples.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ir.ir import (
    DiagramIR, Canvas,
    PointFixed, Segment, Triangle, CircleThrough3,
    PointTriangleCenter, CircleCenterPoint,
    LineThrough, PointFoot, PointMidpoint,
    PointIntersection, PickClosestTo,
    Draw, DrawPoints, LabelPoint, MarkRightAngles, MarkAngles, LabelAngle,
    Fill,
)
from ir.to_sympy import compile_defs
from ir.to_tikz import ir_to_tikz
from util.tikz_renderer import render_tikz

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")


def add_white_background(svg: str) -> str:
    """Insert a white rect covering the full viewBox, for dark-mode readability."""
    import re
    m = re.search(r"viewBox='([^']+)'", svg)
    if not m:
        return svg
    x, y, w, h = m.group(1).split()
    rect = f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='white'/>"
    # Insert immediately after the opening <g id='page1'> tag
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


# ── 1. Right triangle ──────────────────────────────────────────────────────
print("Generating: right_triangle")
right_triangle = DiagramIR(
    canvas=Canvas(xmin=-1, xmax=5, ymin=-1, ymax=4),
    define=[
        PointFixed(id="A", x=0, y=0),
        PointFixed(id="B", x=4, y=0),
        PointFixed(id="C", x=0, y=3),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
    ],
    render=[
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        DrawPoints(points=["A", "B", "C"]),
        MarkRightAngles(angles=[{"a": "B", "o": "A", "b": "C"}]),
        LabelPoint(p="A", text="$A$", pos="below left"),
        LabelPoint(p="B", text="$B$", pos="below right"),
        LabelPoint(p="C", text="$C$", pos="above left"),
    ],
)
save("right_triangle", render(right_triangle))


# ── 2. Circumscribed circle ─────────────────────────────────────────────────
print("Generating: circumscribed_circle")
circumcircle = DiagramIR(
    canvas=Canvas(xmin=-4, xmax=5, ymin=-4, ymax=5),
    define=[
        PointFixed(id="A", x=0, y=3),
        PointFixed(id="B", x=-2.5, y=-1.5),
        PointFixed(id="C", x=3, y=-1),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        CircleCenterPoint(id="circ", center="O", through="A"),
    ],
    render=[
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        Draw(obj="circ"),
        DrawPoints(points=["A", "B", "C", "O"]),
        LabelPoint(p="A", text="$A$", pos="above"),
        LabelPoint(p="B", text="$B$", pos="below left"),
        LabelPoint(p="C", text="$C$", pos="below right"),
        LabelPoint(p="O", text="$O$", pos="above right"),
    ],
)
save("circumscribed_circle", render(circumcircle))


# ── 3. Euler line ────────────────────────────────────────────────────────────
print("Generating: euler_line")
euler = DiagramIR(
    canvas=Canvas(xmin=-4, xmax=6, ymin=-3, ymax=6),
    define=[
        PointFixed(id="A", x=0, y=5),
        PointFixed(id="B", x=-3, y=-1),
        PointFixed(id="C", x=5, y=0),
        Triangle(id="T", a="A", b="B", c="C"),
        Segment(id="AB", a="A", b="B"),
        Segment(id="BC", a="B", b="C"),
        Segment(id="CA", a="C", b="A"),
        PointTriangleCenter(id="O", tri="T", which="circumcenter"),
        PointTriangleCenter(id="G", tri="T", which="centroid"),
        PointTriangleCenter(id="H", tri="T", which="orthocenter"),
        LineThrough(id="euler", p="O", q="G"),
    ],
    render=[
        Draw(obj="AB"),
        Draw(obj="BC"),
        Draw(obj="CA"),
        Draw(obj="euler"),
        DrawPoints(points=["A", "B", "C", "O", "G", "H"]),
        LabelPoint(p="A", text="$A$", pos="above"),
        LabelPoint(p="B", text="$B$", pos="below left"),
        LabelPoint(p="C", text="$C$", pos="right"),
        LabelPoint(p="O", text="$O$", pos="above right"),
        LabelPoint(p="G", text="$G$", pos="above right"),
        LabelPoint(p="H", text="$H$", pos="below right"),
    ],
)
save("euler_line", render(euler))

print("Done.")
