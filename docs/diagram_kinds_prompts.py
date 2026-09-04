"""Prompts for the diagram kinds that needed a genuine fresh
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
- work_table, l_prism, prism_net: added in a later round-2 gallery review
  after these 3 previously "baseline-reuse" kinds were found to have their
  own real construction bugs (see manifest.json / assemble_diagram_kinds_
  manifest.py's FRESH_CHOICES notes for the exact coordinate evidence):
  work_table had one non-uniform row height (fixed by re-running WITH
  experimental_diagram_cookbook=True so table_grid() is available, which
  computes uniform row heights by construction); l_prism had the same
  depth edge braced twice in reversed direction (fixed by an explicit,
  no-cookbook prompt enumerating every distinct edge to label exactly
  once); prism_net had visually crowded (if numerically distinct) face
  labels (attempted with an explicit no-cookbook prompt asking for a
  larger/more-spaced net layout).
- balance_scale: added in a round-3 gallery review after this previously
  "baseline-reuse" kind was found to have its own real construction bug
  (see manifest.json / assemble_diagram_kinds_manifest.py's FRESH_CHOICES
  notes for the exact coordinate evidence): each pan's contents (a stack of
  blocks on one pan, a column of coins on the other) were drawn entirely
  BELOW that pan's platform surface (larger y = lower on the SVG canvas),
  i.e. hanging off the bottom of the pan rather than resting inside/on top
  of it. Fixed by re-running WITHOUT the cookbook flag, with a prompt that
  spells out the physical reasoning (unsecured objects resting on a pan
  must be drawn above the platform's surface -- smaller y -- or they would
  visually appear to fall out of/through the pan) rather than a bare
  coordinate instruction.

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
        # ticket 06, pydsl-authoring-quality: flipped to True for this
        # kind's round-4 re-attempt, which needs the chart_axes() cookbook
        # helper (ticket 03) to route around the tall/narrow-canvas root
        # cause documented in manifest.json (to_svg.py's single shared
        # x/y scale factor). Attempts 0-2 below are the original
        # known-gap round's history (all run WITHOUT the cookbook flag,
        # before chart_axes() existed) -- kept verbatim for the record,
        # even though the flag they'd now be re-run under has changed.
        # Attempt 3+ are this ticket's new chart_axes()-based attempts.
        True,
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
            # Attempt 4 (ticket 06, pydsl-authoring-quality): use the new
            # chart_axes() cookbook helper to compress the x (0-8 hours)
            # and y (0-100 score) data ranges into a square-ish geometry
            # region for PLACEMENT only, so the renderer's single shared
            # x/y scale (root cause of attempts 0-2's tall/narrow canvas)
            # no longer forces a bad aspect ratio -- while every label
            # still shows the true, unmapped data value.
            "Draw a scatter plot of hours studied (x, 0 to 8) vs. test "
            "score (y, 0 to 100) for these points: (1, 55), (2, 60), "
            "(3, 68), (4, 74), (5, 85), (6, 90), plus a line of best fit "
            "through the data. Because the x-axis and y-axis have very "
            "different natural ranges, use the chart_axes() cookbook "
            "helper to place everything: call "
            "`axes = chart_axes(x_data_range=(0, 8), y_data_range=(0, 100), "
            "geom_size=10.0)` once, then for every plotted point, both "
            "endpoints of the best-fit line, and every axis tick mark, "
            "compute `gx, gy = axes.map(data_x, data_y)` and use "
            "`(gx, gy)` as that item's geometry position (e.g. "
            "`point(*axes.map(hours, score))`). Draw x-axis ticks at "
            "hours 0, 2, 4, 6, 8 and y-axis ticks at scores 0, 25, 50, "
            "75, 100, each placed via axes.map() the same way. Label "
            "every tick and every point with its TRUE, unmapped data "
            "value as text (e.g. the point for (3, 68) must be labeled "
            "'68', never its mapped geometry coordinate). Label the "
            "x-axis 'Hours' and the y-axis 'Score'. Do not add a slope "
            "triangle or rise/run labels. Leave clear margin around the "
            "plotted region so no label, tick mark, or axis title is "
            "clipped at any canvas edge.",
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
    "work_table": (
        True,
        [
            "Draw a ratio table showing the number of cups of flour to cups "
            "of sugar in a recipe: 1 to 2, 2 to 4, 3 to 6, and 4 to 8. Use a "
            "single bordered grid (one header row for the two column "
            "labels, then one data row per ratio pair) where every row, "
            "including the header row, has EXACTLY the same height as "
            "every other row -- no row may be taller or shorter than the "
            "others for any reason.",
        ],
    ),
    "l_prism": (
        False,
        [
            "Draw a single L-shaped solid (3D, one combined shape, not two "
            "separate boxes) formed by joining a 6-long by 4-wide by "
            "3-tall rectangular block with a 2-by-2-by-3 rectangular notch "
            "cut into one corner of it. Label exactly these 5 distinct "
            "edge dimensions, each with its own brace, and label each one "
            "EXACTLY ONCE: the overall length of 6, the overall width of "
            "4, the overall height of 3, the notch width of 2, and the "
            "notch depth of 2. Do not brace the same edge twice, and never "
            "draw two braces between the same pair of endpoints (whether "
            "in the same order or reversed) -- every brace must span a "
            "visually distinct edge of the solid.",
        ],
    ),
    "prism_net": (
        False,
        [
            "Draw the flat unfolded net of a rectangular prism that is 4 "
            "units long, 2 units wide, and 3 units tall, laid out on a "
            "grid with each face labeled with its dimensions. Use a large "
            "layout with generous spacing: leave clear empty space between "
            "every pair of adjacent faces in the net, and place each "
            "dimension label with enough room around it that it does not "
            "sit tightly against a face's edge or another label -- prefer "
            "a bigger overall canvas over cramming the net into a small "
            "area.",
            # Attempt 2 fallback: attempt 0 added a title caption above the
            # net whose y-coordinate landed outside (above) the canvas's
            # own viewBox, clipping it entirely invisible. Explicitly ban a
            # title/caption above the net and require every label
            # (including the net itself) to stay fully within the canvas
            # bounds with real margin, while keeping the spacing ask.
            "Draw the flat unfolded net of a rectangular prism that is 4 "
            "units long, 2 units wide, and 3 units tall, laid out on a "
            "grid with each face labeled only with its dimensions (for "
            "example '4 x 3') -- do not add a face-name label like 'FRONT' "
            "or 'TOP', and do not add any title or caption above or below "
            "the net. Use a large layout with generous spacing: leave "
            "clear empty space between every pair of adjacent faces, and "
            "place each dimension label centered inside its own face with "
            "room around it so it never touches an edge or another label. "
            "Every label must be placed fully inside the canvas bounds, "
            "with at least half a unit of blank margin on all four sides "
            "of the whole net -- nothing may be clipped at or fall outside "
            "any canvas edge.",
        ],
    ),
    "balance_scale": (
        False,
        [
            "Draw a balance scale with a level beam resting on a triangular "
            "fulcrum, with a pan hanging from each end of the beam, to "
            "illustrate the equation 2x + 3 = 7 balanced on the two sides. "
            "Physical constraint: anything drawn on top of a pan (blocks, "
            "coins, weights, or any other contents) is unsecured and "
            "resting on the pan's flat platform surface under gravity -- it "
            "must therefore be drawn entirely ABOVE that platform surface "
            "(at a smaller y-coordinate / higher up on the canvas than the "
            "platform), stacked upward from the platform's top edge. Never "
            "draw pan contents below the platform's surface (at a larger "
            "y-coordinate) -- that would place them underneath or hanging "
            "off the bottom of the pan, which is physically impossible: "
            "unsecured objects placed below a pan's surface would simply "
            "fall out of the pan under gravity rather than rest in it.",
        ],
    ),
}

FINAL_KIND_NAMES: list[str] = list(FINAL_KIND_CONFIGS.keys())

assert len(FINAL_KIND_NAMES) == 9, f"expected 9 fresh-generation kinds, got {len(FINAL_KIND_NAMES)}"
