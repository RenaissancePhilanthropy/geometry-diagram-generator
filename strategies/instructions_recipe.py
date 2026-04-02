"""Prompt templates for the recipe-based strategy."""

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
| triangle | vertices:[A,B,C], spec:{...} | spec keys: angle_A/B/C (deg), side_AB/BC/CA, right_angle_at; optional center:[x,y] for centroid placement (default [2,2]) |
| regular_polygon | center, radius, vertices:[...], start_angle?, star? | N equally-spaced points on a circle + polygon; star:true connects every 2nd vertex (star polygon, e.g. pentagram) — requires odd N ≥ 5 |
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
- styles: named TikZ style definitions, e.g. {"highlight": {"color": "red", "thick": true}}
- draws: list of explicit draw objects — use when you need per-element styling
  Each entry: {"obj": "<id>", "style": "red"} OR {"obj": "<id>", "style": {"color": "red", "thick": true}}
  Shorthand: {"endpoints": ["A","B"], "style": "..."} draws the segment [A,B] without needing a named segment op
  NOTE: When auto_draw_all is true, objects in "draws" are NOT also auto-drawn — "draws" takes precedence.
  WARNING: When auto_draw_all is false, you MUST provide explicit draws for every element you want visible.

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
| regular_polygon | center, radius, vertices:[...], start_angle?, star? | N equally-spaced points on circle + polygon; star:true for star shape (odd N ≥ 5) |
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
- styles: {"name": {"color": "red", "thick": true, ...}} — named TikZ style definitions
- draws: explicit draw list for per-element styling
  {obj: "<id>", style?: "red" | {"color":"red","thick":true}}
  {endpoints: ["A","B"], style?: "..."} — draws segment [A,B] without a named segment op
  Objects in "draws" are not auto-drawn even when auto_draw_all is true.
  When auto_draw_all is false, EVERY visible element must appear in "draws".

### Selectors
selector dicts use "kind" values: upper_of_line, lower_of_line, pick_index (k),
on_object (obj), closest_to (p), same_side (line:[A,B], ref_point), chain (rules:[...])

### ID rules
- All IDs must be unique across the construction list
- IDs starting with __ are reserved — never use them
"""
