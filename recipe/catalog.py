# recipe/catalog.py
"""Recipe catalog loader and prompt builders.

Recipes are YAML files in recipe/recipes/. Each file has:
  name, description, tags, context, setup, example, notes

`setup` (list of DSL op dicts): prerequisite objects for the recipe; NOT sent to LLM.
`example` (dict with 'construction' key): the pattern being taught; sent to LLM.
`context` (str): one-sentence prose describing what's given; sent to LLM.
`notes` (list of str): non-obvious caveats; sent to LLM if non-empty.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


_RECIPES_BASE = Path(__file__).parent / "recipes"


def _catalog_dir(catalog: str = "default") -> Path:
    """Resolve the directory for a named recipe catalog."""
    d = (_RECIPES_BASE / catalog).resolve()
    # Reject path traversal
    if _RECIPES_BASE.resolve() not in d.parents:
        raise ValueError(f"Invalid catalog name: {catalog!r}")
    if not d.is_dir():
        raise FileNotFoundError(f"Recipe catalog {catalog!r} not found at {d}")
    return d


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class RecipeSummary(BaseModel):
    """One-liner entry for the selection catalog."""
    id: str
    name: str
    description: str
    tags: list[str] = []


class Recipe(BaseModel):
    """Full recipe loaded from YAML."""
    name: str
    description: str
    tags: list[str] = []
    context: str
    setup: list[dict[str, Any]] = []   # DSL op dicts; NOT sent to LLM
    example: dict[str, Any]            # RecipeDSL fragment; sent to LLM
    notes: list[str] = []


class RecipeSelection(BaseModel):
    """Output from the recipe selection model."""
    selected_recipes: list[str] = []
    unmatched_concepts: list[str] = []
    confidence: str = "high"  # "high" | "medium" | "low"


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

def _load_all_recipes(catalog: str = "default") -> dict[str, Recipe]:
    """Load all YAML files from the named catalog directory."""
    recipes: dict[str, Recipe] = {}
    for path in sorted(_catalog_dir(catalog).glob("*.yaml")):
        with path.open() as f:
            data = yaml.safe_load(f)
        recipe = Recipe.model_validate(data)
        recipes[recipe.name] = recipe
    return recipes


_CATALOG_CACHE: dict[str, dict[str, Recipe]] = {}


def _get_cache(catalog: str = "default") -> dict[str, Recipe]:
    if catalog not in _CATALOG_CACHE:
        _CATALOG_CACHE[catalog] = _load_all_recipes(catalog)
    return _CATALOG_CACHE[catalog]


def clear_cache() -> None:
    """Clear the recipe catalog cache (primarily for testing)."""
    _CATALOG_CACHE.clear()


def load_catalog(catalog: str = "default") -> list[RecipeSummary]:
    """Return catalog as a flat list of RecipeSummary objects."""
    return [
        RecipeSummary(
            id=r.name,
            name=r.name.replace("_", " ").title(),
            description=r.description,
            tags=r.tags,
        )
        for r in _get_cache(catalog).values()
    ]


def load_recipe(name: str, catalog: str = "default") -> Recipe:
    """Load a full recipe by name. Raises KeyError if not found."""
    cache = _get_cache(catalog)
    if name not in cache:
        raise KeyError(f"Recipe {name!r} not found. Available: {sorted(cache.keys())}")
    return cache[name]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_selection_prompt(user_request: str, catalog: list[RecipeSummary]) -> str:
    """Build the prompt for the recipe selection model."""
    catalog_text = "\n".join(
        f"- {entry.id}: {entry.description} [tags: {', '.join(entry.tags)}]"
        for entry in catalog
    )
    return (
        "You are selecting geometry construction recipes relevant to a user's request.\n\n"
        f"User request: {user_request}\n\n"
        "Available recipes:\n"
        f"{catalog_text}\n\n"
        "Select the recipes most relevant to this request. "
        "For each selected recipe, the ID must exactly match one of the available recipe IDs above.\n\n"
        "Respond with JSON only:\n"
        '{"selected_recipes": [...], "unmatched_concepts": [...], "confidence": "high"|"medium"|"low"}'
    )


def build_generation_prompt(
    user_request: str,
    recipes: list[Recipe],
    dsl_docs: str,
) -> str:
    """Build the prompt for the DSL generation model.

    The `setup` field of each recipe is NOT included (it's for tests only).
    The `context` + `example` of each recipe IS included.
    """
    sections: list[str] = []

    sections.append(
        "You are a geometry diagram assistant. Generate a RecipeDSL JSON object "
        "that describes the requested diagram.\n\n"
        f"DSL Reference:\n{dsl_docs}"
    )

    if recipes:
        sections.append("## Relevant Construction Examples\n")
        for recipe in recipes:
            example_json = json.dumps(recipe.example, indent=2)
            notes_text = ""
            if recipe.notes:
                notes_text = "\nNotes:\n" + "\n".join(f"- {n}" for n in recipe.notes)
            sections.append(
                f"### {recipe.name.replace('_', ' ').title()}\n"
                f"Context: {recipe.context}\n"
                f"Example construction:\n```json\n{example_json}\n```"
                f"{notes_text}"
            )

    sections.append(f"## User Request\n{user_request}")
    sections.append(
        "## Output\nRespond with a valid RecipeDSL JSON object only. "
        "Do not include markdown fences or explanations."
    )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# DSL documentation string (sent to LLM in every generation prompt)
# ---------------------------------------------------------------------------

DSL_DOCS = """\
RecipeDSL is a JSON object with these top-level fields:
- mode: "abstract" (default) or "grid"
- construction: ordered list of ops (each has "op" and "id")
- annotations: optional batch flags and explicit marks/labels

## Foundation ops
- triangle: {op, id, vertices:[A,B,C], spec:{angle_A, angle_B, side_AB, ...}}

## triangle op

spec fields (A/B/C are positional slots: A=vertices[0], B=vertices[1], C=vertices[2]):

| Form | Required fields | Example spec |
|------|----------------|--------------|
| SSS  | side_AB, side_BC, side_CA | {"side_AB": 4, "side_BC": 3, "side_CA": 5} |
| SAS  | two sides + included angle | {"side_AB": 4, "angle_B": 60, "side_BC": 3} |
| ASA  | two angles + included side | {"angle_A": 45, "side_AB": 5, "angle_B": 60} |
| AAS  | two angles + non-included side | {"angle_A": 45, "angle_B": 60, "side_BC": 4} |
| right_at | right_angle_at + 2 constraints | {"right_angle_at": "B", "side_AB": 3, "side_BC": 4} |

IMPORTANT: A/B/C always refer to the first, second, and third entry in `vertices`, regardless
of what those vertex IDs are named. Never use actual vertex IDs (like P, Q, R) in the spec.
  NOT supported: SSA (ambiguous)
- circle: {op, id, center, radius} or {op, id, center, through}
- ellipse: axis-aligned ellipse. Exactly one form:
    center_axes: {op, id, center:<pt_id>, hradius:<number>, vradius:<number>}
    bbox:        {op, id, bbox:[<corner1_id>, <corner2_id>]}
    foci:        {op, id, foci:[<f1_id>, <f2_id>], major_axis:<2a>}
             or  {op, id, foci:[<f1_id>, <f2_id>], through:<pt_id>}
    eccentricity:{op, id, center:<pt_id>, semi_major:<a>, eccentricity:<e>, orientation:"horizontal"|"vertical"}
  Example (Mathematics_15 — ellipse with center (1,3), horiz axis 3, vert axis 4):
    canvas: {op, id:"canvas", x_range:[-1,4], y_range:[0,8], axes:true, grid:true}
    center: {op:"point", id:"O", coords:[1,3]}
    ellipse: {op:"ellipse", id:"E", center:"O", hradius:1.5, vradius:2}
    label center with its coordinates: annotations.labels [{kind:"label_point", point:"O", text:"(1, 3)"}]
- polygon: {op, id, vertices:[...]}
- point: {op, id, coords:[x, y]}  (grid mode)

## Composite ops (auto-expand to multiple IR definitions)
- altitude: {op, id, from_vertex, triangle:<tri_id>, foot}  # preferred; or to_side:[P,Q]
  id = the altitude line; foot = the foot point on the base
- circumcircle: {op, id, of:<triangle_id>, center}
- incircle: {op, id, of:<triangle_id>, center}
- perpendicular_bisector: {op, id, of:[P,Q], mid}
- angle_bisector: {op, id, vertex, ray1_toward, ray2_toward}
- centroid: {op, id, of:<triangle_id>}
- median: {op, id, from_vertex, triangle:<tri_id>, mid}  # preferred; or to_side:[P,Q]
- polygon_exterior: {op, id, base:[P,Q], ref_point, n, vertices:[v2,...]}
  n=4 for square, n=3 for equilateral triangle
- polygon_from_angles_and_sides: {op, id, vertices:[A,B,...], side_lengths:[...], angles:[...], center?:[x,y], rotation?:degrees}
  Standalone mode: side_lengths N values, angles N or N-1. Optional rotation (degrees CCW) spins the shape before centering.
  Edge-anchored mode: add base:[P,Q] (must equal vertices[0:2]) + ref_point:str.
    side_lengths: N-1 (omit base edge) or N (include base edge as [0] for validation).
    Polygon is placed on the OPPOSITE side of base edge from ref_point.
    Works with any already-defined points including intersections and midpoints.

## Derived ops (direct IR mapping)
- midpoint: {op, id, of:[P,Q]}
- intersection: {op, id, of:[obj1,obj2], selector:{kind,...}}
- perpendicular: {op, id, to_line, through}
- parallel: {op, id, to_line, through}
- line_through: {op, id, points:[A,B]}
- segment: {op, id, endpoints:[A,B]}
- reflection: {op, id, point, over}
- rotation: {op, id, point, center, angle}  (angle in degrees)
- point_on_segment: {op, id, segment:[A,B], ratio}  (ratio 0-1)
- tangent_line: {op, id, circle, from_point, selector:{kind,...}}

## selector (for intersection and tangent_line ops)

selector kinds — use the exact kind string from this table:

| Description | kind string | Required fields |
|-------------|-------------|-----------------|
| nearest to a point | "closest_to" | "p": "<point_id>" |
| above a line | "upper_of_line" | "a": "<pt>", "b": "<pt>" |
| below a line | "lower_of_line" | "a": "<pt>", "b": "<pt>" |
| by index (0=first) | "index" | "k": 0 |
| inside a triangle | "inside_triangle" | "tri": "<triangle_id>" |
| same side as a point | "same_side" | "line": ["<pt>", "<pt>"], "ref_point": "<pt>" |
| between two points | "between" | "a": "<pt>", "b": "<pt>" |
| beyond a point | "beyond" | "from_point": "<pt>", "past_point": "<pt>" |
| interior of a shape | "interior" | "polygon": "<shape_id>" |
| exterior of a shape | "exterior" | "polygon": "<shape_id>" |
| opposite side | "opposite_side" | "line_through": ["<pt>", "<pt>"], "ref_point": "<pt>" |
| point on object | "on_object" | "obj": "<object_id>" |
| chain (sequential) | "chain" | "rules": [<selector>, ...] |

Examples:
  selector: {"kind": "closest_to", "p": "P"}
  selector: {"kind": "upper_of_line", "a": "A", "b": "B"}
  selector: {"kind": "index", "k": 0}
  selector: {"kind": "chain", "rules": [{"kind": "upper_of_line", "a": "A", "b": "B"}, {"kind": "closest_to", "p": "P"}]}

### Secant from external point — getting near and far intersections in order

A secant from external point A through a circle hits two points C (near) and D (far),
with order A–C–D. Use two separate intersection ops:
  # C = nearer intersection (closer to A)
  {op:"intersection", id:"C", of:["secant_line","circle"], selector:{"kind":"closest_to","p":"A"}}
  # D = farther intersection (beyond C from A's perspective)
  {op:"intersection", id:"D", of:["secant_line","circle"], selector:{"kind":"beyond","from_point":"A","past_point":"C"}}

Do NOT use "index" for secant intersections — the index order is arbitrary and may vary.

### Ratio points on a segment — direction matters

point_on_segment ratio is measured from segment[0] toward segment[1]:
  ratio=0   → at segment[0]
  ratio=1   → at segment[1]
  ratio=0.5 → midpoint

For ratio strings "m:n", the point is m/(m+n) of the way from segment[0] to segment[1].

Examples:
  "M on BC with MC = 2·MB" → MB:MC = 1:2 → segment:["B","C"], ratio:"1:2"  (1/3 from B)
  "F on AD with AF:FD = 1:2"             → segment:["A","D"], ratio:"1:2"  (1/3 from A)
  "G on CN with NC = 3·GC" → GC:CN = 1:3 → segment:["C","N"], ratio:"1:3"  (1/4 from C)

A common mistake: writing ratio:"2:1" when the problem says MC=2·MB — that places M at 2/3
from B (i.e. MB=2·MC), which is the opposite. Always map the first ratio component to the
distance from segment[0].

## Annotations
- auto_draw_all: true (default) — draw all non-implicit objects
- auto_label_points: true (default) — label all named points
- auto_mark_right_angles: false (default) — add right-angle marks

### annotations.labels — explicit text callouts
  {"kind":"label_segment", "endpoints":["A","B"], "text":"c"}
      Text beside midpoint of segment AB (side lengths, etc.)
  {"kind":"label_point", "point":"A", "text":"A_1", "pos":"above"}
      Override the auto-generated label for point A. Omit "text" to keep
      the point id but change only "pos". pos ∈ {auto, above, below, left,
      right, above left, above right, below left, below right}.
  {"kind":"label_angle", "a":"B", "vertex":"A", "b":"C", "text":"45°"}
      Text inside the angle at vertex A formed by rays AB and AC. Shorthand
      form: {"kind":"label_angle", "at":"A", "of":"tri_ABC", "text":"α"}.
      Pair with a mark_angle to also draw the arc.
  {"kind":"label_free_text", "text":"S_1", "centroid_of":"poly1"}
      Place text at the centroid of a named polygon or triangle.
  {"kind":"label_free_text", "text":"s^{2} = r^{2} + h^{2}", "at":[3.0, 1.5]}
      Place text at explicit construction coordinates.
      text supports LaTeX: ^{2} (superscript), _{n} (subscript), \\pi, \\sqrt{3}.

### annotations.draws — explicit draw control (use when auto_draw_all=false or for styled elements)
  {"obj": "circle1"}                              — draw named object
  {"endpoints": ["A","B"], "style": "red"}        — draw segment with named color
  {"obj": "seg1", "style": {"dashed": true, "color": "blue"}}  — inline style dict

### annotations.styles — named style definitions
  styles: {"highlight": {"color": "red", "thick": true}}
  Style properties: color, dashed, dotted, thick, thin, opacity, "->", "<->", "<-"
  Arrow styles add arrowheads: {"->": true} for end arrow, {"<->": true} for both ends.

## Render ops (in construction list)
- fill: {op:"fill", id, obj:"poly1", opacity:0.3, style:{"color":"blue","fill":"lightblue"}}
    Fills a closed shape (polygon, circle, triangle). Optional holes:[...] for cutouts.
- arc: {op:"arc", id, center:"O", start:"A", end:"B", reflex:false}
    Arc from A to B around center O. reflex:true for major arc (>180°).

## Layout — multiple figures
Side-by-side: use separate constructions with offset centers and a wide canvas.
  E.g., two triangles: first at center:[1.5,2], second at center:[5.5,2], canvas width≥8.
  triangle, polygon_from_sides, and polygon_from_angles_and_sides all support center:[x,y].
  Each op must use distinct vertex names across all shapes in the diagram.

## checks (optional)

The `checks` field accepts a list of geometric assertions. These are validated at parse time.

Supported check kinds:
  {"check": "distance", "points": ["A", "B"], "expected": 5.0}
  {"check": "parallel", "seg1": ["A", "B"], "seg2": ["C", "D"]}
  {"check": "perpendicular", "seg1": ["A", "B"], "seg2": ["B", "C"]}
  {"check": "angle_equals", "points": ["A", "B", "C"], "expected": 90.0}
  {"check": "collinear", "points": ["A", "B", "C"]}
  {"check": "on_circle", "point": "P", "circle": "c1"}
  {"check": "tangent", "obj1": "c1", "obj2": "L1"}

Note: The lowerer auto-generates checks from construction ops (triangles, altitudes, etc.).
Explicit checks in this field are supplemental assertions.

## ID rules
- All IDs must be unique
- IDs starting with __ are reserved (used internally during lowering)
"""
