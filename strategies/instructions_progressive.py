"""Prompt templates for the progressive tools strategy (phases 1–4)."""

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
