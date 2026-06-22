"""Retry hint patterns and text for the RecipeStrategy retry loop.

These are extracted from the inline hint blocks in strategies/recipe.py
so they can be overridden by GEPA prompt optimization.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Hint text constants — one per retry hint pattern
# ---------------------------------------------------------------------------

HINT_ANGLE_EQUALITY = """\
When two angles must be equal across separate constructions (e.g.
mark_angle group), ensure the triangles are geometrically similar.
For triangle ops: use the same angle values in both specs, OR use
proportional side lengths with matching right_angle_at positions
(e.g. legs 2:3 and 10:15 produce identical base angles).
For free points: derive the second construction's coordinates from
the first using the same ratios or rotation angles."""

HINT_RIGHT_ANGLE_BASE = """\
A mark_right_angle annotation failed because the angle at that
vertex is not 90°. The annotation declares an intent — the construction
must make it true."""

HINT_RIGHT_ANGLE_CANDIDATES = """\
The checker found right angles at the same vertex using
DIFFERENT point triples — use one of these instead:"""

HINT_RIGHT_ANGLE_FOOT = """\
Use point_foot to project the point onto the line:
`{op: 'point_foot', id: 'X', source: 'P', onto: 'seg_AB'}`
guarantees angle P-X-endpoint = 90°. Do not place the foot
manually with point_along or fixed coordinates — only
point_foot guarantees the right angle."""

HINT_CIRCULAR_DEP = """\
A circular dependency was detected — this almost always means a
triangle (or other shape) op has an `id` that is the same as one of its
own vertex names. For example, `{op:'triangle', id:'T', vertices:['R','S','T']}`
creates a cycle because the shape object and vertex point share the id 'T'.
Fix: give the triangle a distinct id that does not appear in its vertices
list, e.g. `id:'tri_RST'`."""

HINT_BETWEEN_SELECTOR = """\
The intersection exists but is outside the segment
(t<0 = before the start point, t>1 = beyond the end point). This
usually means the two objects' endpoints are placed so they don't
actually cross between the named points. Reposition the endpoints so
the two lines/segments genuinely intersect between the selector's
reference points. For chords: ensure both chords span the interior of
the circle and cross each other. For an angle bisector: verify the
vertex angle is what the problem states (check the actual angle in
your coords)."""

HINT_TRIANGLE_SPEC = """\
Your triangle spec is geometrically invalid. Common causes:
  • SSA (two sides + non-included angle) is ambiguous — switch to SAS, ASA, AAS, or SSS.
  • Triangle inequality violated — the three side lengths cannot form a triangle.
 Unambiguous spec forms:
  • SAS: two sides + the INCLUDED angle (e.g. side_AB, angle_B, side_BC)
  • ASA: two angles + the included side (e.g. angle_A, side_AB, angle_B)
  • AAS: two angles + a non-included side (e.g. angle_A, angle_B, side_BC)
  • SSS: all three sides (e.g. side_AB, side_BC, side_CA)
  • right_angle_at + two constraints (e.g. right_angle_at:'B', side_AB:3, side_BC:4)
 IMPORTANT: spec keys always use positional A/B/C (first/second/third vertex slot),
 not actual vertex letters."""

HINT_MARK_ANGLE_CANDIDATES = """\
A mark_angle annotation failed because the two angles in
the group are not equal. The checker found angle pairs that ARE
equal at the same vertex(es) — use one of these instead:"""

HINT_MARK_ANGLE_FALLBACK = """\
A mark_angle annotation failed because the two angles in
the group are not equal. This means the construction doesn't
produce geometrically equal angles. If using two triangles,
make them similar by using the same angle values or proportional
side lengths in both specs."""

HINT_UNDEFINED_ID = """\
Every id used in 'endpoints', 'of', 'through', 'to_line', etc.
must appear as the 'id' of an earlier construction op.
Common mistake: in grid mode, triangle/rectangle vertex names are
labels — they are NOT automatically defined as point ids. You must
add explicit `{op: 'point', id: 'A', coords: [...]}` ops before
referencing 'A' in other ops."""

# ---------------------------------------------------------------------------
# Hint pattern definitions: (regex, hint_key)
# ---------------------------------------------------------------------------

HINT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"Angle \S+ = [\d.]+° but \S+ = [\d.]+"), "hint_angle_equality"),
    (re.compile(r"mark_right_angle\(.*?\).*?not 90"), "hint_right_angle"),
    (re.compile(r"[Cc]ircular dependency.*nodes are in a cycle"), "hint_circular_dep"),
    (re.compile(r"beyond|before .+, t≈"), "hint_between_selector"),
    (re.compile(r"Triangle '.*?':.*(?:ambiguous|inequality|cannot solve|not valid)", re.IGNORECASE), "hint_triangle_spec"),
    (re.compile(r"mark_angle.*?not equal|MarkAngle at|mark_angle group=\d.*?but", re.IGNORECASE), "hint_mark_angle"),
    (re.compile(r"references undefined id '"), "hint_undefined_id"),
]

# ---------------------------------------------------------------------------
# Default hint text map — key matches the hint_key from HINT_PATTERNS
# ---------------------------------------------------------------------------

HINT_TEXTS: dict[str, str] = {
    "hint_angle_equality": HINT_ANGLE_EQUALITY,
    "hint_right_angle": HINT_RIGHT_ANGLE_BASE,
    "hint_circular_dep": HINT_CIRCULAR_DEP,
    "hint_between_selector": HINT_BETWEEN_SELECTOR,
    "hint_triangle_spec": HINT_TRIANGLE_SPEC,
    "hint_mark_angle": HINT_MARK_ANGLE_FALLBACK,
    "hint_undefined_id": HINT_UNDEFINED_ID,
}