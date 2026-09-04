"""The 30 diagram-kind prompts for ticket 07's PythonFullStrategy baseline.

Each entry is a plain, kind-specific end-user request — no mention of
"kinds", the taxonomy project, or cookbook helpers (per the ticket).
`prompt` is `None` only for the `none` kind, which is not a rendering kind
at all (see ticket 07's item 30) and is never sent to the strategy.

Kept as a separate module (rather than inline in the runner) so the
prompt data can be read/edited independently of the execution/manifest
logic in run_baseline.py, per the ticket's "Code Organization" note.
"""

from __future__ import annotations

KIND_PROMPTS: list[tuple[str, "str | None"]] = [
    (
        "grid_area",
        "Draw a 4-by-6 rectangle on a unit-square grid so students can find "
        "its area by counting the unit squares inside it.",
    ),
    (
        "tape_diagram",
        "Draw a tape diagram for 3 times 4: one bar split into 3 equal "
        "sections, each labeled 4, to show 3 x 4 = 12.",
    ),
    (
        "number_line",
        "Draw a horizontal number line from 0 to 10 with a tick mark at "
        "every whole number, and plot points at 3 and 7.5.",
    ),
    (
        "coordinate_plane",
        "Draw a coordinate plane from -5 to 5 on both axes, plot the "
        "triangle with vertices (1, 1), (4, 1), and (4, 5), and draw an "
        "arrow showing it being translated 2 units left and 3 units down.",
    ),
    (
        "scatter_plot",
        "Draw a scatter plot of hours studied vs. test score for these "
        "points: (1, 55), (2, 60), (3, 68), (4, 74), (5, 85), (6, 90), and "
        "draw a line of best fit through the data with a small slope "
        "triangle showing rise over run.",
    ),
    (
        "shape_comparison",
        "Draw a square with side length 4 and a rectangle with width 6 and "
        "height 3 side by side, each labeled with its dimensions, so "
        "students can compare their areas and perimeters.",
    ),
    (
        "attribute_chart",
        "Draw a table comparing a square, a rectangle, and a triangle "
        "against the attributes 'Has 4 sides', 'Has right angles', and "
        "'All sides equal', with a check mark or an X in each cell.",
    ),
    (
        "work_table",
        "Draw a ratio table showing the number of cups of flour to cups of "
        "sugar in a recipe: 1 to 2, 2 to 4, 3 to 6, and 4 to 8.",
    ),
    (
        "area_model",
        "Draw an area model (box method) rectangle for the multiplication "
        "23 x 15: split the rectangle into a 2-by-2 grid of cells with the "
        "factors 20 and 3 written above the rectangle and 10 and 5 written "
        "to the left of it, and label each interior cell with its partial "
        "product.",
    ),
    (
        "equation_steps",
        "Show the worked solution steps for solving 3x + 5 = 20 for x, one "
        "step per line.",
    ),
    (
        "angle_figure",
        "Draw two parallel horizontal lines cut by a single transversal "
        "line, with matching arrowheads marking the lines as parallel, and "
        "label the four angles formed at the top intersection as 1, 2, 3, "
        "and 4.",
    ),
    (
        "cube_volume",
        "Draw a rectangular prism that is 3 units long, 2 units wide, and 2 "
        "units tall in 3D, with its visible faces divided into a grid of "
        "unit cubes so students can find its volume by counting cubes.",
    ),
    (
        "prism_3d",
        "Draw a labeled rectangular prism in 3D with length 5, width 3, and "
        "height 4, using dashed lines for the hidden back edges.",
    ),
    (
        "l_prism",
        "Draw a single L-shaped solid formed by joining a large "
        "rectangular block with a smaller rectangular block cut into one "
        "corner of it, as one combined 3D shape, with edge lengths labeled.",
    ),
    (
        "prism_net",
        "Draw the flat unfolded net of a rectangular prism that is 4 units "
        "long, 2 units wide, and 3 units tall, laid out on a grid with each "
        "face labeled with its dimensions.",
    ),
    (
        "composite_polygon",
        "Draw an L-shaped floor plan made of two rectangles — one 8 by 4 "
        "and one 3 by 5 — on a grid, with a dashed line showing how it "
        "splits into the two rectangular regions for computing total area.",
    ),
    (
        "dot_plot",
        "Draw a dot plot for these shoe sizes collected from a class: 6, 7, "
        "7, 8, 8, 8, 9, 9, 10, with a horizontal axis labeled by shoe size "
        "and a stack of dots above each value showing how many students "
        "have that size.",
    ),
    (
        "circle",
        "Draw a circle with its center marked, a radius segment labeled r "
        "= 4 cm, and a diameter segment labeled d = 8 cm.",
    ),
    (
        "column_arithmetic",
        "Draw the standard column-addition layout for 347 + 265, with each "
        "digit in its own place-value column, the plus sign in the left "
        "column, and a rule line above the answer row.",
    ),
    (
        "long_division",
        "Draw the long-division house layout for 84 divided by 4: the "
        "divisor 4 to the left of the bracket, the dividend 84 under the "
        "bar, the quotient above the bar, and at least one multiply-and-"
        "subtract step shown underneath.",
    ),
    (
        "composite",
        "Draw a small rectangle labeled 'Garden' next to a small circle "
        "labeled 'Pond', connected by a curly brace labeled 'Backyard' "
        "showing they're both part of the same yard.",
    ),
    (
        "object_array",
        "Draw 3 groups of 5 small circles each, arranged in neat rows, to "
        "show 3 groups of 5 equals 15 objects.",
    ),
    (
        "bar_graph",
        "Draw a vertical bar graph of favorite fruit votes: apples 8, "
        "bananas 5, grapes 12, oranges 7, with labeled axes and bars.",
    ),
    (
        "place_value_blocks",
        "Draw base-ten blocks representing the number 243: 2 hundreds "
        "flats (each a 10-by-10 grid of unit squares), 4 tens rods, and 3 "
        "ones units.",
    ),
    (
        "place_value_chart",
        "Draw a place-value chart with labeled columns for Thousands, "
        "Hundreds, Tens, and Ones, with the digits 2, 5, 6, 9 placed in "
        "their correct columns to show the number 2569.",
    ),
    (
        "number_bond",
        "Draw a number bond showing the whole number 12 in a circle at the "
        "top, connected by branches to two part circles below it showing 7 "
        "and 5.",
    ),
    (
        "ruler_measure",
        "Draw a ruler marked from 0 to 6 inches with tick marks at every "
        "quarter inch, and draw a pencil above it aligned so its tip is at "
        "0 and its end is at 4.5 inches.",
    ),
    (
        "fill_level",
        "Draw two upright rectangular containers of the same size side by "
        "side, one shaded up to 25% full and the other shaded up to 75% "
        "full, each labeled with its fill percentage.",
    ),
    (
        "balance_scale",
        "Draw a balance scale with a level beam resting on a triangular "
        "fulcrum, with a pan hanging from each end of the beam, to "
        "illustrate the equation 2x + 3 = 7 balanced on the two sides.",
    ),
    (
        "none",
        None,
    ),
]

KIND_NAMES: list[str] = [kind for kind, _ in KIND_PROMPTS]

assert len(KIND_PROMPTS) == 30, f"expected 30 kinds, got {len(KIND_PROMPTS)}"
assert len(set(KIND_NAMES)) == 30, "kind names must be unique"
