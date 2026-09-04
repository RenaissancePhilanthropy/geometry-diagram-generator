"""Prompts for the 5 diagram kinds that needed a genuine fresh
PythonFullStrategy.run() (not baseline reuse) when the diagram-kinds-poc
gallery was assembled, per that ticket's corrected scope:

- area_model, attribute_chart: baseline verdict was "partial" and a
  cookbook helper now exists that targets their exact defect
  (bar()/table_grid() respectively) -- re-run WITH
  experimental_diagram_cookbook=True, describing the same content as the
  baseline prompt (the fix is expected to come from the cookbook helper
  being available to the script-writing LLM, not from new prompt wording).
- coordinate_plane, scatter_plot, shape_comparison: baseline verdict was
  "partial" due to canvas-sizing / label-overlap defects (not missing
  primitives) -- re-run WITHOUT the cookbook flag, with the prompt
  explicitly calling out margins/spacing informed by the exact baseline
  defect recorded in manifest.json.

Each kind maps to a list of attempt prompts, tried in order (index 0
first) until one produces a clean render or the list is exhausted (known
gap). Keeping every attempt's prompt text here (not just the final winner)
so the generation history shows real iteration, per the "small amount of
reasonable prompt iteration (2-3 tries) is acceptable and expected"
guidance the gallery was built under.
"""

from __future__ import annotations

# kind -> (use_cookbook, [attempt prompts in order])
FINAL_KIND_CONFIGS: "dict[str, tuple[bool, list[str]]]" = {
    "area_model": (
        True,
        [
            "Draw an area model (box method) rectangle for the multiplication "
            "23 x 15: split the rectangle into a 2-by-2 grid of cells with the "
            "factors 20 and 3 written above the rectangle and 10 and 5 written "
            "to the left of it, and label each of the 4 interior cells with "
            "its own partial product (20x10=200, 20x5=100, 3x10=30, 3x5=15). "
            "Make sure all 4 cell labels are present and none of the text "
            "overlaps.",
        ],
    ),
    "attribute_chart": (
        True,
        [
            "Draw a table comparing a square, a rectangle, and a triangle "
            "against the attributes 'Has 4 sides', 'Has right angles', and "
            "'All sides equal', with a check mark or an X in each cell. Use "
            "a single bordered grid for the whole table -- one header row "
            "with the shape names, one header column with the attribute "
            "names, and no duplicate or extra decorative rows/bands.",
        ],
    ),
    "coordinate_plane": (
        False,
        [
            "Draw a coordinate plane from -5 to 5 on both axes, plot the "
            "triangle with vertices (1, 1), (4, 1), and (4, 5), and draw an "
            "arrow showing it being translated 2 units left and 3 units "
            "down. Add a caption reading 'Translation: (x-2, y-3)' placed "
            "safely inside the canvas with enough left margin that it is "
            "not clipped by the left edge -- put it below the plane or in "
            "open space near the top-left of the grid, not flush against "
            "the canvas boundary.",
            # Attempt 2 fallback: be even more explicit / directive about
            # where the caption goes and ask for extra canvas margin.
            "Draw a coordinate plane from -5 to 5 on both axes, plot the "
            "triangle with vertices (1, 1), (4, 1), and (4, 5), and draw an "
            "arrow showing it being translated 2 units left and 3 units "
            "down. Add a caption reading 'Translation: (x-2, y-3)' as a "
            "title-style label centered above the plane (near the top of "
            "the canvas, horizontally centered between x=-5 and x=5), and "
            "leave at least 1 extra unit of blank margin on every side of "
            "the canvas so no label ever touches or crosses a canvas edge.",
        ],
    ),
    "scatter_plot": (
        False,
        [
            "Draw a scatter plot of hours studied vs. test score for these "
            "points: (1, 55), (2, 60), (3, 68), (4, 74), (5, 85), (6, 90), "
            "and draw a line of best fit through the data with a small "
            "slope triangle showing rise over run. Make the canvas wide "
            "enough and leave enough right-hand margin that the x-axis "
            "title, the 'rise'/'run' labels, and every other text label "
            "fit fully inside the canvas with none of it cut off at the "
            "right edge.",
            # Attempt 2 fallback: cap axis title length and be numerically
            # explicit about margin, in case vague "enough margin" wording
            # isn't being honored.
            "Draw a scatter plot of hours studied vs. test score for these "
            "points: (1, 55), (2, 60), (3, 68), (4, 74), (5, 85), (6, 90). "
            "Label the x-axis 'Hours' and the y-axis 'Score' (short labels "
            "only, no long titles). Draw a line of best fit through the "
            "data with a small slope triangle near the middle of the line "
            "showing rise over run, with the 'rise' and 'run' labels placed "
            "just above/below the triangle's legs. Leave at least 2 extra "
            "units of blank canvas margin to the right of x=6 and above "
            "y=90 so no label or text is ever clipped at any canvas edge.",
            # Attempt 3 fallback: attempt 2 made things worse (dense
            # per-unit y tick marks crowded the axis and the canvas was
            # still a tall, narrow strip) -- be maximally explicit that the
            # canvas must be WIDER than it is tall, use coarse tick spacing
            # only, and skip the background grid entirely.
            "Draw a simple scatter plot of hours studied (x-axis, 0 to 8) "
            "vs. test score (y-axis, 0 to 100, tick marks every 10 units "
            "only -- not every unit) for these points: (1, 55), (2, 60), "
            "(3, 68), (4, 74), (5, 85), (6, 90). Do not draw a background "
            "grid. Draw a line of best fit through the data. The plot "
            "must be noticeably WIDER than it is tall (a landscape-shaped "
            "canvas, roughly 1.5 times as wide as tall) so that a short "
            "x-axis label 'Hours' below the axis and a short y-axis label "
            "'Score' to the left of the axis both fit fully on the canvas "
            "with clear margin -- do not add a slope triangle or "
            "rise/run labels.",
        ],
    ),
    "shape_comparison": (
        False,
        [
            "Draw a square with side length 4 and a rectangle with width 6 "
            "and height 3 side by side, each labeled with its dimensions. "
            "Below each shape, write its Area and Perimeter as two separate "
            "lines of text that do not overlap each other or the shape "
            "above them. Below both shapes, add a one-sentence summary "
            "comparing their areas and perimeters, with enough bottom "
            "margin on the canvas that the summary sentence is never "
            "clipped.",
            # Attempt 2 fallback: force vertical stacking + explicit
            # per-line spacing and canvas margin.
            "Draw a square with side length 4 and a rectangle with width 6 "
            "and height 3 side by side, with clear empty space between the "
            "two shapes. Under the square, place two labels stacked "
            "vertically with visible spacing between them: 'Area = 16' then "
            "'Perimeter = 16'. Under the rectangle, similarly stack "
            "'Area = 18' then 'Perimeter = 18'. At the very bottom of the "
            "canvas, below all shape labels and with at least 1 full unit "
            "of blank margin beneath it, add one summary sentence comparing "
            "the two shapes' areas and perimeters. Make the canvas tall "
            "enough that nothing overlaps and the summary sentence is fully "
            "visible, not clipped at the bottom edge.",
            # Attempt 3 fallback: attempts 1-2 both wrapped the summary
            # onto two lines whose vertical spacing was too small, so the
            # lines overlapped each other. Force it onto a single line
            # this time so there is no wrapping to get wrong.
            "Draw a square with side length 4 and a rectangle with width 6 "
            "and height 3 side by side, with clear empty space between the "
            "two shapes. Under the square, place two labels stacked "
            "vertically with visible spacing between them: 'Area = 16' then "
            "'Perimeter = 16'. Under the rectangle, similarly stack "
            "'Area = 18' then 'Perimeter = 18'. At the very bottom of the "
            "canvas, add exactly ONE short summary label as a SINGLE line "
            "of text (for example: 'Rectangle has more area, same "
            "perimeter') -- it must be short enough to fit on one line, "
            "not wrapped onto two lines, and placed with at least 1 full "
            "unit of blank margin below it and above every other label so "
            "nothing overlaps or is clipped.",
        ],
    ),
}

FINAL_KIND_NAMES: list[str] = list(FINAL_KIND_CONFIGS.keys())

assert len(FINAL_KIND_NAMES) == 5, f"expected 5 fresh-generation kinds, got {len(FINAL_KIND_NAMES)}"
