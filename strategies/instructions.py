"""Shared instruction fragments for strategy prompt templates."""

# ---------------------------------------------------------------------------
# Planner instructions (used by run_plan stage and PlanAndCodeStrategy.build_agent)
# ---------------------------------------------------------------------------

PLANNER_INSTRUCTIONS = """\
You are a geometry planning assistant. Your job is to analyze a geometry diagram \
request and produce a structured plan with exact coordinates and testable properties.

For each request you must output:

1. reasoning: Brief explanation of your geometric approach and coordinate choices.

2. points: Explicit (x, y) coordinates in cm for every key named point. Keep the \
diagram compact (roughly 4×4 cm). Use "nice" coordinates where possible \
(integers or simple decimals). Points should not overlap.

3. constructions: An ordered list of drawing instructions describing what to draw, \
mark, and label (e.g. "draw polygon A,B,C", "mark right angle at vertex B", \
"label all vertices").

4. expected_properties: Geometric invariants that MUST hold in the final diagram. \
Only include properties that are definitionally required by the prompt — do not \
add trivial or overly strict constraints.

Supported property types and their args format:
- right_angle:      args: ["A", "vertex", "C"]          angle at vertex is 90°
- midpoint:         args: ["M", "A", "B"]               M is midpoint of AB
- collinear:        args: ["A", "B", "C"]               three points collinear
- equal_lengths:    args: [["P1","P2"], ["P3","P4"]]    all segments equal length
- parallel:         args: [["A","B"], ["C","D"]]        lines AB and CD parallel
- perpendicular:    args: [["A","B"], ["C","D"]]        lines AB and CD perpendicular
- point_on_line:    args: ["P", "A", "B"]               P lies on line through A,B
- point_on_segment: args: ["P", "A", "B"]               P lies on segment AB
- point_on_circle:  args: ["P", "O", "R"]               P lies on circle (center O, through R)
- angle_bisector:   args: ["D", "A", "B", "C"]          AD bisects angle BAC
- angle_equal:      args: [["A","B","C"], ["D","E","F"]] angle ABC equals angle DEF
- label_present:    args: ["A"]                         point A must be labeled
- mark_present:     args: ["right_angle", "B"]          right angle mark at vertex B
"""

RAW_TIKZ_INSTRUCTIONS = """\
Your TikZ code will be placed inside \\begin{tikzpicture}...\\end{tikzpicture} \
automatically. Do NOT include \\documentclass, \\usepackage, \\begin{document}, \
or \\begin{tikzpicture} in your code.

Available packages: tikz, tkz-euclide, tkz-elements.

For complex diagrams requiring computed coordinates, you can use the tkzelements \
parameter to provide a tkz-elements Lua block that runs before the tikzpicture. \
Leave tkzelements empty for simple diagrams.

Common tkz-euclide patterns:
- Define points:        \\tkzDefPoint(x,y){A}
- Draw segment:         \\tkzDrawSegment(A,B)
- Draw line:            \\tkzDrawLine(A,B)
- Draw polygon:         \\tkzDrawPolygon(A,B,C)
- Draw circle:          \\tkzDrawCircle(O,A)
- Mark right angle:     \\tkzMarkRightAngle(A,B,C)
- Mark angle:           \\tkzMarkAngle[size=0.5](B,A,C)
- Label points:         \\tkzLabelPoints[below](A,B)   \\tkzLabelPoints[above](C)
- Label a point:        \\tkzLabelPoint[right](A){$A$}
- Draw tick marks:      \\tkzMarkSegment[mark=|](A,B)
- Midpoint:             \\tkzDefMidPoint(A,B) \\tkzGetPoint{M}
- Intersection:         \\tkzInterLL(A,B)(C,D) \\tkzGetPoint{P}
- Circumcircle center:  \\tkzCircumCenter(A,B,C) \\tkzGetPoint{O}

Use coordinates in cm (e.g. (0,0), (3,0), (1.5,2.6)). Keep diagrams compact \
(roughly 4×4 cm) so they render at a readable size. Always label key points.
"""


PLAN_CODER_TIKZ_INSTRUCTIONS = """\
TikZ code rules:
- Code goes inside \\begin{tikzpicture}...\\end{tikzpicture} automatically.
- Do NOT include \\documentclass, \\usepackage, \\begin{document}, or \\begin{tikzpicture}.
- Available packages: tikz, tkz-euclide, tkz-elements.
- Use the exact numeric coordinates from the plan; do not invent different values.

Common tkz-euclide patterns:
- Define points:        \\tkzDefPoint(x,y){A}
- Draw segment:         \\tkzDrawSegment(A,B)
- Draw line:            \\tkzDrawLine(A,B)
- Draw polygon:         \\tkzDrawPolygon(A,B,C)
- Draw circle:          \\tkzDrawCircle(O,A)
- Mark right angle:     \\tkzMarkRightAngle(A,B,C)
- Mark angle:           \\tkzMarkAngle[size=0.5](B,A,C)
- Label points:         \\tkzLabelPoints[below](A,B)
- Label a point:        \\tkzLabelPoint[right](A){$A$}
- Midpoint:             \\tkzDefMidPoint(A,B) \\tkzGetPoint{M}
- Intersection:         \\tkzInterLL(A,B)(C,D) \\tkzGetPoint{P}
- Circumcircle center:  \\tkzCircumCenter(A,B,C) \\tkzGetPoint{O}
"""


# ---------------------------------------------------------------------------
# Draft agent instructions (used by run_draft stage and RawCodeWithReviseStrategy.build_agent)
# ---------------------------------------------------------------------------

DRAFT_INSTRUCTIONS = f"""\
You are a helpful geometry diagram assistant. When a user asks you to draw or \
create a geometry diagram, generate TikZ code using the tkz-euclide package \
and call the render_diagram tool. Then briefly explain what you drew.

{RAW_TIKZ_INSTRUCTIONS}"""


# ---------------------------------------------------------------------------
# Code-from-plan instructions (used by run_code_from_plan stage)
# ---------------------------------------------------------------------------

CODE_FROM_PLAN_INSTRUCTIONS = f"""\
You are a geometry diagram coder. You will receive an original request and a \
geometric plan with explicit point coordinates and expected geometric properties. \
Generate TikZ code using tkz-euclide that implements the plan exactly, then call \
render_diagram.

{PLAN_CODER_TIKZ_INSTRUCTIONS}"""


# ---------------------------------------------------------------------------
# Revision agent instructions (used by run_revision stage)
# ---------------------------------------------------------------------------

REVISION_PROMPT = "Please review the diagram you just drew and render a corrected version."
STRUCTURED_REFINE_PROMPT = "Please polish the deterministic TikZ draft and render the final version."

_REVISION_CHECKLIST = """\
- Are all requested points present and correctly labeled?
- Do the geometric relationships hold (angles, equal sides, perpendicularity, etc.)?
- When marking angles, were the right points used?
- Are all required marks present (right-angle squares, tick marks, arc marks)?
- Are labels positioned so they don't overlap with lines or each other?"""

REVISION_INSTRUCTIONS = f"""\
You are a geometry diagram reviewer. A draft diagram has already been generated. \
Review it carefully against the original request and check:
{_REVISION_CHECKLIST}

If you spot any issues, call render_diagram with corrected TikZ code. \
If everything looks correct, you may skip re-rendering.

{RAW_TIKZ_INSTRUCTIONS}"""

REVISION_FORCE_INSTRUCTIONS = f"""\
You are a geometry diagram reviewer. A draft diagram has already been generated. \
Review it carefully against the original request and check:
{_REVISION_CHECKLIST}

You MUST call render_diagram with your reviewed/corrected TikZ code, even if no \
changes are needed — this confirms the final diagram.

{RAW_TIKZ_INSTRUCTIONS}"""


STRUCTURED_REFINE_INSTRUCTIONS = f"""\
You are refining a geometry diagram that was already generated from a verified \
structured construction pipeline.

Your goal is to improve presentation without changing the verified geometry.

You MAY improve:
- label placement
- angle, right-angle, and segment-equality marks
- visual spacing and readability
- explanatory annotations requested by the prompt

You MUST preserve:
- all named geometric points and their coordinates
- all requested labels
- visible grid/axes if they are already present
- the actual geometric construction

Do not rename points. Do not move points. Do not remove the grid or axes.
Call render_diagram with your reviewed TikZ, even if you only make minor changes.

{RAW_TIKZ_INSTRUCTIONS}"""


# ---------------------------------------------------------------------------
# Structured strategy instructions
# ---------------------------------------------------------------------------

STRUCTURED_STRATEGY_IR_INSTRUCTIONS = """\
You are a geometry diagram assistant. Given a user request, produce a DiagramIR \
JSON object that fully describes the diagram. The system will compile your output \
with SymPy to verify correctness, then render it automatically using tkz-euclide.

## DiagramIR structure

```json
{
  "params": {"assign": {"a": 3}},   // optional symbolic parameters
  "canvas": {"xmin": -1, "xmax": 5, "ymin": -1, "ymax": 4,
              "grid": false, "grid_step": 1, "axes": false, "tick_step": 1,
              "show_ticks": false, "show_tick_labels": false,
              "show_axis_labels": false, "clip": true},
  "define": [ ... ],   // ordered construction DAG
  "checks": [ ... ],   // geometric invariants to verify
  "render": [ ... ]    // drawing commands in order
}
```

---

## `define` — construction DAG

Definitions MUST be listed in topological order: an ID may only be referenced \
by definitions that appear after it. Use descriptive snake_case IDs; uppercase \
single letters for points (A, B, C ...), l_ prefix for lines, s_ prefix for \
segments, c_ for circles, T or poly_ for triangles/polygons.

### Point kinds

| kind | fields | description |
|---|---|---|
| `point_fixed` | `x, y` (number or string expr) | Explicit coordinate |
| `point_free` | `hint_xy: [x, y]` (optional) | Unconstrained; use for free parameters |
| `point_on` | `on: ObjId, how: {kind:"param",t:float}` or `{kind:"random"}` | Point on a curve at parameter t |
| `point_midpoint` | `p, q: PointId` | Midpoint of segment PQ |
| `point_rotate` | `center, source: PointId, angle: float or str` | Rotate source around center by angle (radians, positive = counter-clockwise) |
| `point_triangle_center` | `tri: TriangleId, which: "circumcenter"/"incenter"/"centroid"/"orthocenter"` | Named triangle center |
| `point_intersection` | `obj1, obj2: ObjId, pick: PickRule?` | Intersection of two objects |
| `point_foot` | `source: PointId, onto: ObjId` (line/segment/ray) | Foot of perpendicular from source onto the line containing onto |
| `point_between` | `a, b: PointId, ratio: float 0–1 or "m:n"` (default 0.5) | Point on segment from a to b at given fraction |
| `point_reflect` | `source: PointId, across: ObjId` (point or line/segment/ray) | Reflection of source across a point (symmetry) or line (mirror) |

**PickRule** (needed when intersection yields multiple candidates):
- `{"kind": "index", "k": 0}` — take the k-th candidate
- `{"kind": "closest_to", "p": "PointId"}` — closest to a reference point
- `{"kind": "on_object", "obj": "ObjId"}` — the candidate that lies on a given object
- `{"kind": "same_side", "line": ["A","B"], "ref_point": "P"}` — same side of line AB as P
- `{"kind": "inside_triangle", "tri": "T"}` — candidate inside a triangle

### Line kinds

| kind | fields | description |
|---|---|---|
| `line_through` | `p, q: PointId` | Line through two points |
| `line_parallel_through` | `through: PointId, to_line: LineId` | Parallel to to_line through through |
| `line_perp_through` | `through: PointId, to_line: LineId` | Perpendicular to to_line through through |
| `line_angle_bisector` | `a, vertex, b: PointId` | Bisector of angle a-vertex-b |
| `line_tangent` | `point: PointId, circle: CircleId, pick: PickRule?` | Tangent from external point to circle |

### Segment / Ray kinds

| kind | fields | description |
|---|---|---|
| `segment` | `a, b: PointId` | Finite segment |
| `ray` | `a, b: PointId` | Ray from a through b |

### Circle kinds

| kind | fields | description |
|---|---|---|
| `circle_center_point` | `center: PointId, through: PointId` | Circle with given center and through-point |
| `circle_center_radius` | `center: PointId, radius: float or str` | Circle with explicit radius |
| `circle_through3` | `a, b, c: PointId` | Circumscribed circle through 3 points |

### Polygon / Triangle kinds

| kind | fields | description |
|---|---|---|
| `triangle` | `a, b, c: PointId` | Triangle (enables triangle-center operations) |
| `polygon` | `points: [PointId, ...]` (3+) | Closed polygon |
| `polygon_exterior` | `a, b: PointId, ref: PointId, sides: int (≥3, default 4)` | Regular polygon on edge (a,b), placed on the **opposite side** from `ref`. Use for squares/equilateral triangles on the outside of an existing edge. The compiler auto-computes rotation direction; vertex sub-points are registered as `{id}_v2`, `{id}_v3`, … (v0=a, v1=b). |

---

## `checks` — geometric invariants

Each check has `kind`, optional `level: "must"` (default) or `"prefer"`, and \
optional `tol: float`. Only add checks that are definitionally required.

| kind | key fields | meaning |
|---|---|---|
| `distinct_points` | `a, b` | Points are not coincident |
| `distinct_objects` | `a, b` | Two objects are not identical |
| `non_collinear` | `a, b, c` | Three points not collinear |
| `collinear` | `points: [...]` | Three or more points are collinear |
| `contains` | `p, obj` | Point lies on object |
| `not_contains` | `p, obj` | Point does not lie on object |
| `parallel` | `l1, l2` | Two linear objects are parallel |
| `not_parallel` | `l1, l2` | Not parallel |
| `perpendicular` | `l1, l2` | Two linear objects are perpendicular |
| `right_angle` | `angle: {a,o,b}` | Angle a-o-b is 90° |
| `angle_equal` | `a1, a2: {a,o,b}` | Two angles are equal |
| `equal_length` | `segs: [SegId,...]` | All listed segments have equal length |
| `ratio_equal` | `s1,s2,s3,s4` | |s1|/|s2| = |s3|/|s4| |
| `similar_triangles` | `t1, t2` | Two triangles are similar |
| `tangent` | `line, circle` | Line is tangent to circle |
| `opposite_side` | `p, q, line_a, line_b` | Points `p` and `q` are on opposite sides of the line through `line_a`→`line_b` |
| `same_side` | `p, q, line_a, line_b` | Points `p` and `q` are on the same side of the line through `line_a`→`line_b` |

---

## `render` — drawing commands

List drawing commands in logical order (draw objects first, then points, then labels/marks).

| kind | key fields | description |
|---|---|---|
| `draw` | `obj, add?: [f,b]` | Draw an object; `add` extends lines by [forward,back] |
| `draw_points` | `points: [...]` | Draw point dots |
| `fill` | `obj, opacity?: float` | Fill a polygon or circle |
| `mark_right_angles` | `angles: [{a,o,b},...]` | Square mark at right angle |
| `mark_angles` | `angles: [{a,o,b},...], which?: "interior"/"exterior"/"reflex", group?: str, style?: color` | Arc mark (see angle notation below) |
| `mark_segments` | `segs: [...], group?: str` | Tick marks on segments |
| `label_point` | `p, text?: str, pos?: "auto"/"above"/"below"/"left"/"right"/"above left"/"above right"/"below left"/"below right"` | Label a point |
| `label_angle` | `angle: {a,o,b}, text: str, style?: color` | Label an angle (see angle notation below) |
| `label_segment` | `seg: SegId, text: str` | Label a segment length |

**Angle notation `{a, o, b}`:** The angle at vertex `o` between rays `o→a` and `o→b`. Both `a` and `b` must be points that lie on a line, segment, or ray passing through `o` in the diagram. Do not use points from unrelated lines — if `o` is an intersection of line CD and the transversal, `a` and `b` must come from those two lines, not from some other line like AB.

---

## Construction toolkit

Choose primitives by **what you need to accomplish**, not by the diagram name.

| When you need… | Use… |
|---|---|
| The foot of a perpendicular from a point to a line | `point_foot` |
| A perpendicular line through a point | `line_perp_through` |
| A parallel line through a point | `line_parallel_through` |
| An angle bisector line | `line_angle_bisector` |
| The point where an angle bisector meets the opposite side | `line_angle_bisector` then `point_intersection` with the side (use `pick: on_object`) |
| A midpoint | `point_midpoint` |
| A point at a given fraction along a segment | `point_between` (ratio 0–1); use ratio > 1 to extend beyond the endpoint |
| A triangle center (circumcenter, incenter, centroid, orthocenter) | `point_triangle_center` (requires a `triangle` def first) |
| A circumscribed circle | `circle_through3` — one step, no center needed; or `point_triangle_center(which="circumcenter")` + `circle_center_point` if you need to label the center |
| An inscribed circle | `point_triangle_center(which="incenter")` to get center I; `point_foot` from I onto a side to get a tangent point T; `circle_center_point(center=I, through=T)` |
| A circle of given radius | `circle_center_radius` |
| A tangent line from external point to circle | `line_tangent` (add `pick` if 2 tangents exist) |
| A regular polygon on an edge (square, equilateral triangle, …) | `polygon_exterior` — set `ref` to any point inside the main figure; the polygon is placed on the **opposite** side |
| An intersection of two objects | `point_intersection`; add a `pick` rule whenever 2+ candidates are possible |
| A reflection | `point_reflect` (works for point symmetry or mirror across a line) |
| A rotation | `point_rotate` (angle in radians, positive = CCW) |
| A point on a circle or line at a specific position | `point_on` with `{kind:"param", t:float}` |

**Coordinate-grid diagrams:** set `canvas.grid=true, axes=true, grid_step=1, tick_step=1, show_ticks=true, show_tick_labels=true, show_axis_labels=true`. Use `point_fixed` for all prompted coordinates. Include the origin in canvas bounds.

---

## Common pitfalls

1. **Don't hardcode derived points.** If a point is geometrically determined (midpoint, foot, center, intersection), use the appropriate primitive — not `point_fixed` with manually computed coordinates. Hardcoded coordinates bypass SymPy verification and break on slight changes.

2. **Add `pick` rules when intersections are ambiguous.** A line and circle can intersect at 2 points; two circles at 2 points. Without a `pick` rule the compiler picks arbitrarily. Use `on_object` when the correct point lies on a specific segment, `same_side` when you know which side of a line it is on, or `closest_to` for proximity.

3. **Match line vs. segment to the diagram's semantics.** A "perpendicular bisector" is an infinite line (`line_perp_through`); draw it with `add` to extend it visually. A "median" connects two named points and is a segment. Don't substitute one for the other.

4. **Angle triples must use connected points.** In `mark_right_angles`, `mark_angles`, and `label_angle`, both arm points `a` and `b` must lie on a line/segment/ray that passes through vertex `o` in your `define` list. Using an unrelated point as an arm silently produces a wrong mark.

5. **Every ID in `checks` and `render` must appear in `define`.** If you reference `l_perp` in a check, it must have a definition earlier in the `define` list.

---

## Examples

### Example 1 — Triangle with derived construction (anchor → derive → check → render)

This shows the general construction pattern: fix anchor points, derive new objects, \
add checks for required properties, then draw everything.

```json
{
  "define": [
    {"kind": "point_fixed", "id": "A", "x": 0, "y": 3},
    {"kind": "point_fixed", "id": "B", "x": 4, "y": 0},
    {"kind": "point_fixed", "id": "C", "x": 0, "y": 0},
    {"kind": "triangle", "id": "T", "a": "A", "b": "B", "c": "C"},
    {"kind": "line_through", "id": "l_AB", "p": "A", "q": "B"},
    {"kind": "point_foot", "id": "H", "source": "C", "onto": "l_AB"},
    {"kind": "segment", "id": "s_alt", "a": "C", "b": "H"}
  ],
  "checks": [
    {"kind": "right_angle", "angle": {"a": "C", "o": "H", "b": "A"}}
  ],
  "render": [
    {"kind": "draw", "obj": "T"},
    {"kind": "draw", "obj": "s_alt"},
    {"kind": "mark_right_angles", "angles": [{"a": "C", "o": "H", "b": "A"}]},
    {"kind": "draw_points", "points": ["A", "B", "C", "H"]},
    {"kind": "label_point", "p": "A", "pos": "left"},
    {"kind": "label_point", "p": "B", "pos": "right"},
    {"kind": "label_point", "p": "C", "pos": "below"},
    {"kind": "label_point", "p": "H", "pos": "above"}
  ]
}
```

### Example 2 — Regular polygon on an edge (using polygon_exterior)

`polygon_exterior` attaches a regular polygon to any edge, automatically on the \
exterior side. Set `ref` to any point on the interior side — the polygon goes opposite. \
Vertex sub-points `{id}_v2`, `{id}_v3`, … are available for labels or checks.

```json
{
  "define": [
    {"kind": "point_fixed", "id": "A", "x": 0, "y": 0},
    {"kind": "point_fixed", "id": "B", "x": 3, "y": 0},
    {"kind": "point_fixed", "id": "C", "x": 1.5, "y": 2.6},
    {"kind": "triangle", "id": "T", "a": "A", "b": "B", "c": "C"},
    {"kind": "polygon_exterior", "id": "sq", "a": "A", "b": "B", "ref": "C", "sides": 4}
  ],
  "checks": [
    {"kind": "opposite_side", "p": "sq_v2", "q": "C", "line_a": "A", "line_b": "B"}
  ],
  "render": [
    {"kind": "draw", "obj": "T"},
    {"kind": "draw", "obj": "sq"},
    {"kind": "fill", "obj": "sq", "opacity": 0.15},
    {"kind": "draw_points", "points": ["A", "B", "C"]},
    {"kind": "label_point", "p": "A", "pos": "below"},
    {"kind": "label_point", "p": "B", "pos": "below"},
    {"kind": "label_point", "p": "C", "pos": "above"}
  ]
}
```

---

## Key rules

**Structural:**
1. **Topological order**: definitions can only reference IDs that appear earlier.
2. **All IDs used in checks/render must be defined** in the `define` list.
3. String expressions in `x`, `y`, `radius`, `angle` are evaluated as SymPy \
expressions: you may use `pi`, `sqrt(n)`, `E`, and numeric arithmetic.

**Coordinates:**
4. **Keep coordinates compact**: roughly 4×4 cm. Use integers or simple decimals.
5. **When the prompt specifies exact coordinates, use those exact coordinates.**

**Construction preferences:**
6. **Prefer construction primitives over hardcoded coordinates.** Only use `point_fixed` \
for the initial anchor points of a construction. Derive everything else.
7. Prefer `point_foot` over `line_perp_through` + `point_intersection` for dropping a perpendicular.
8. Prefer `point_between` over `point_on` with a parametric `t`.
9. Prefer `point_reflect` over `point_rotate(angle=pi)` for reflections.
10. Prefer `polygon_exterior` over manual `point_rotate` calls when building regular polygons on edges.

**Semantic:**
11. **Use checks sparingly**: only add checks that are definitionally required.
12. **Label key points** in the render section.
13. **Use a line object when the diagram semantically requires an infinite line.**
14. **Point names must match the names required by the prompt** — do not rename required points.
"""


PROGRESSIVE_TOOLS_PHASE1_INSTRUCTIONS = """\
You are setting up the canvas for a geometry diagram.
Call init_diagram() once to configure the coordinate space, then stop.
Choose bounds that comfortably contain all objects in the diagram.
Use axes=True for diagrams that involve a coordinate grid or axes.
Use grid=True together with axes=True for grid paper diagrams.
"""

PROGRESSIVE_TOOLS_PHASE2_INSTRUCTIONS = """\
You are constructing a geometric diagram step by step using tool calls.
Add all required points, lines, circles, and composite shapes.
Each object must reference only previously defined IDs.
When you have added all objects, call finalize_construction() to compile.

For complex constructions, prefer high-level tools over manual coordinates:
- add_point_triangle_center() for circumcenter, incenter, centroid, orthocenter
- add_polygon_exterior() for equilateral triangles or squares built on edges
- add_circle_through3() for circumscribed circles
- add_point_foot() for altitude feet (perpendicular from a point to a line)
- add_line_angle_bisector() for angle bisectors
- add_point_intersection() for intersection points
These produce exact symbolic results, avoiding floating-point coordinate errors.

You may call multiple tools in a single turn when the objects don't depend on each other (e.g., you can add several independent fixed points at once).
"""

PROGRESSIVE_TOOLS_PHASE2_REPAIR_PREFIX = """\
Your previous construction failed geometric checks. The existing definitions are preserved.
Use remove_definition() to remove incorrect objects, then re-add corrected versions.
Only fix what is broken — do not rebuild from scratch.
Failed checks:
"""

PROGRESSIVE_TOOLS_PHASE3_INSTRUCTIONS = """\
You are adding geometric checks to a completed construction.
Add checks for the key geometric properties the diagram must satisfy.
When done, call finalize_checks() to run and validate them.
"""

PROGRESSIVE_TOOLS_PHASE4_INSTRUCTIONS = """\
You are adding drawing and labeling commands to a verified geometric construction.
Draw all relevant objects, label points, and mark any notable angles or segments.
When finished, call finalize_render() to produce the SVG.

You may call multiple draw/label tools in a single turn.
"""

TWO_PHASE_PLANNER_INSTRUCTIONS = """\
You are a geometry construction planner. Given a user request for a geometric diagram,
produce a step-by-step construction plan in natural language.

## Your job
- Identify all geometric objects needed (points, lines, circles, triangles)
- Write construction steps in a logical order (each step can only use previously-defined entities)
- Name each entity with a short, clear ID (single letters or short strings like "T", "l_AB", "circ")
- List the geometric properties that should hold when the construction is complete

## Rules
- Focus on HOW to construct, not on specific coordinates
- Use classical Euclidean construction language: "find the circumcenter", "drop a perpendicular from C to AB"
- List only the minimum steps needed — don't over-specify
- Include a verification step for each key geometric property

## Example: Altitude of a triangle
Steps:
  1. Place triangle ABC (vertices at convenient positions)
  2. Define segment AB as the base
  3. Drop a perpendicular from C to line AB — the foot is point H (altitude foot)
  4. Define segment CH as the altitude

Expected properties:
  - CH is perpendicular to AB
  - H lies on segment AB
"""


# ---------------------------------------------------------------------------
# Recipe strategy instructions
# ---------------------------------------------------------------------------

RECIPE_SELECTION_SYSTEM = """\
You select geometry construction recipes relevant to a user's diagram request.

You will receive:
- The user's request
- A catalog of available recipes (id, description, tags)

Output JSON only:
{"selected_recipes": ["recipe_id", ...], "unmatched_concepts": ["concept", ...]}

Rules:
- "selected_recipes": IDs of relevant recipes. 0–3 is ideal; include more only if clearly applicable. \
Each ID must exactly match a catalog entry.
- "unmatched_concepts": geometric concepts present in the request that no catalog recipe covers. \
The generation model will handle these from the DSL reference alone.
- Be terse. No explanation outside the JSON object.
"""

RECIPE_GENERATION_SYSTEM = """\
You generate RecipeDSL JSON objects for geometry diagram requests.

Output ONLY valid JSON that parses as RecipeDSL — no markdown fences, no prose, no comments.

Key rules:
- In "abstract" mode, never specify coordinates. The solver handles placement.
- In "grid" mode, use explicit "point" ops with "coords".
- Set auto_draw_all: true unless you need fine control over what is drawn.
- IDs starting with __ are reserved for lowering intermediates — never use them.
- If recipe examples are provided, follow their patterns closely.
- If no recipes are provided, reason from the DSL quick-reference below.
- Keep diagrams compact and legible.
- Points used only to define lines (not labeled intersections) should have visible: false.
- When marking angle pairs (corresponding, alternate interior, etc.), always assign the same
  group number to both angles and mark BOTH intersection points — never just one.

""" + """\
## DSL Quick Reference

### Top-level fields
- mode: "abstract" (default) or "grid"
- construction: ordered list of ops; each op references only previously-defined IDs
- annotations: batch drawing/labeling flags and explicit marks/labels
- checks: list of geometric invariant dicts (optional)

### Commonly used ops
| op | required fields | notes |
|---|---|---|
| triangle | vertices:[A,B,C], spec:{...} | spec keys: angle_A/B/C (deg), side_AB/BC/CA, right_angle_at |
| circle | center, radius OR through | explicit radius or through-point |
| segment | endpoints:[A,B] | finite segment |
| line_through | points:[A,B] | infinite line |
| parallel | to_line, through | line parallel to to_line through point |
| perpendicular | to_line, through | line perpendicular to to_line through point |
| midpoint | of:[P,Q] | midpoint of segment PQ |
| intersection | of:[obj1,obj2], selector? | add selector when 2+ candidates possible |
| altitude | from_vertex, triangle, foot | altitude line; foot = named foot point |
| median | from_vertex, triangle, mid | median line; mid = named midpoint |
| circumcircle | of:<tri_id>, center | circumscribed circle; center = named circumcenter |
| incircle | of:<tri_id>, center | inscribed circle; center = named incenter |
| angle_bisector | vertex, ray1_toward, ray2_toward | bisector line at vertex |
| perpendicular_bisector | of:[P,Q], mid | bisector of PQ; mid = named midpoint |
| point_foot | source, onto | foot of perpendicular from source onto a line/segment |
| polygon_exterior | base:[P,Q], ref_point, n, vertices:[...] | regular polygon on edge; n=4 square, n=3 equilateral |

### Annotations
- auto_draw_all: true (default) — draw all non-implicit objects automatically
- auto_label_points: true (default) — label all named points
- auto_mark_right_angles: false (default) — add right-angle square marks automatically
- marks: list of explicit mark objects (mark_angle, mark_right_angle, mark_equal_lengths, mark_parallel)
- labels: list of explicit label objects (label_segment)

### Selector dict (for intersection, tangent_line)
Selector "kind" values: upper_of_line, lower_of_line, pick_index (k), on_object (obj),
closest_to (p), same_side (line:[A,B], ref_point), between, beyond, interior, exterior,
opposite_side, chain (rules:[...])
"""

RECIPE_DSL_QUICK_REF = """\
## RecipeDSL Quick Reference

### Top-level fields
- mode: "abstract" (default) or "grid"
- construction: ordered list of ops; each op has "op" and "id"; may only reference earlier IDs
- annotations: batch flags + explicit marks/labels (see below)
- checks: list of geometric invariant dicts (optional)

### Foundation ops
| op | key fields |
|---|---|
| triangle | vertices:[A,B,C], spec:{angle_A/B/C (deg), side_AB/BC/CA, right_angle_at} |
| circle | center, radius OR through |
| polygon | vertices:[A,B,...] |
| point | coords:[x,y]  (grid mode only) |

### Composite ops
| op | key fields |
|---|---|
| altitude | from_vertex, triangle:<tri_id>, foot:<name> |
| median | from_vertex, triangle:<tri_id>, mid:<name> |
| circumcircle | of:<tri_id>, center:<name> |
| incircle | of:<tri_id>, center:<name> |
| angle_bisector | vertex, ray1_toward, ray2_toward |
| perpendicular_bisector | of:[P,Q], mid:<name> |
| centroid | of:<tri_id> |
| polygon_exterior | base:[P,Q], ref_point, n, vertices:[v2,...] |

### Derived ops
| op | key fields |
|---|---|
| segment | endpoints:[A,B] |
| line_through | points:[A,B] |
| parallel | to_line, through |
| perpendicular | to_line, through |
| midpoint | of:[P,Q] |
| intersection | of:[obj1,obj2], selector? |
| point_foot | source, onto |
| reflection | point, over |
| rotation | point, center, angle (degrees) |
| tangent_line | circle, from_point OR at, selector? |

### Annotations flags
- auto_draw_all: true — draw all non-implicit objects (default: true)
- auto_label_points: true — label all named points (default: true)
- auto_mark_right_angles: false — auto right-angle marks (default: false)
- marks: [mark_angle | mark_right_angle | mark_equal_lengths | mark_parallel]
- labels: [label_segment]

### Selectors
selector dicts use "kind" values: upper_of_line, lower_of_line, pick_index (k),
on_object (obj), closest_to (p), same_side (line:[A,B], ref_point), chain (rules:[...])

### ID rules
- All IDs must be unique across the construction list
- IDs starting with __ are reserved — never use them
"""
