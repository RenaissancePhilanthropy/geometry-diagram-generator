canvas(x_range=(-2.5, 9), y_range=(-1.5, 8))

# Define column widths and row heights proportional to the factors
# Columns: 20 and 3 (wider and narrower)
# Rows: 10 and 5 (taller and shorter)

col_widths = [4.0, 1.5]   # widths for factors 20 and 3
row_heights = [2.8, 1.4]  # heights for factors 10 and 5

x0 = 0.0
y0 = 0.0  # bottom-left of the whole rectangle (y increases upward, but table_grid goes downward — we'll place manually)

# We'll build the grid manually using bar() for full control
# Row 0 (top): factor 10, height = row_heights[0]
# Row 1 (bottom): factor 5, height = row_heights[1]
# Col 0 (left): factor 20, width = col_widths[0]
# Col 1 (right): factor 3, width = col_widths[1]

total_width = col_widths[0] + col_widths[1]
total_height = row_heights[0] + row_heights[1]

# Cells (x, y, width, height) — origin at bottom-left, rows go upward
# Cell (row=0, col=0): top-left → 20 x 10 = 200
# Cell (row=0, col=1): top-right → 3 x 10 = 30
# Cell (row=1, col=0): bottom-left → 20 x 5 = 100
# Cell (row=1, col=1): bottom-right → 3 x 5 = 15

# Using bar(x, y, width, height) where (x,y) is bottom-left corner of each cell

# Row 0 (top row), y starts at row_heights[1] from bottom
r0_y = row_heights[1]
# Row 1 (bottom row), y starts at 0
r1_y = 0.0

# Draw the 4 cells
cell_00 = bar(x0,               r0_y, col_widths[0], row_heights[0], fill_color="lightyellow")
cell_01 = bar(x0 + col_widths[0], r0_y, col_widths[1], row_heights[0], fill_color="lightcyan")
cell_10 = bar(x0,               r1_y, col_widths[0], row_heights[1], fill_color="lightcyan")
cell_11 = bar(x0 + col_widths[0], r1_y, col_widths[1], row_heights[1], fill_color="lightyellow")

# ── Partial-product labels inside each cell ──
# Cell centers
cx00 = x0 + col_widths[0] / 2
cy00 = r0_y + row_heights[0] / 2
label_text("200", at=(cx00, cy00), font_size=16)

cx01 = x0 + col_widths[0] + col_widths[1] / 2
cy01 = r0_y + row_heights[0] / 2
label_text("30", at=(cx01, cy01), font_size=16)

cx10 = x0 + col_widths[0] / 2
cy10 = r1_y + row_heights[1] / 2
label_text("100", at=(cx10, cy10), font_size=16)

cx11 = x0 + col_widths[0] + col_widths[1] / 2
cy11 = r1_y + row_heights[1] / 2
label_text("15", at=(cx11, cy11), font_size=16)

# ── Factor labels ABOVE the rectangle (for columns) ──
# Centered above each column, with a gap above the top edge
top_y = total_height + 0.55

label_text("20", at=(x0 + col_widths[0] / 2, top_y), font_size=17)
label_text("3",  at=(x0 + col_widths[0] + col_widths[1] / 2, top_y), font_size=17)

# ── Factor labels to the LEFT of the rectangle (for rows) ──
# Centered beside each row, with a gap to the left
left_x = -0.55

label_text("10", at=(left_x, r0_y + row_heights[0] / 2), font_size=17)
label_text("5",  at=(left_x, r1_y + row_heights[1] / 2), font_size=17)

# ── "×" symbol at the top-left corner (where row and column factors meet) ──
label_text("×", at=(left_x, top_y), font_size=17)

# ── Title above the diagram ──
label_text("23 × 15  (Area Model)", at=(total_width / 2, top_y + 1.0), font_size=15)

# ── Sum annotation below the rectangle ──
label_text("200 + 30 + 100 + 15  =  345", at=(total_width / 2, -1.0), font_size=13)
