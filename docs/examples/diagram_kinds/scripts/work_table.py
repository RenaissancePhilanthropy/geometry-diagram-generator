# Ratio table: Cups of Flour vs Cups of Sugar
# 1 header row + 4 data rows = 5 rows total
# 2 columns

canvas(x_range=(-0.5, 7.5), y_range=(-0.5, 7.5))

col_widths = [3.0, 3.0]
row_heights = [1.0, 1.0, 1.0, 1.0, 1.0]  # all identical heights

tg = table_grid(0.0, 7.0, col_widths, row_heights, color="black", thick=True)

# Header row (row 0)
hdr0 = tg.cell(0, 0)
hdr1 = tg.cell(0, 1)

# Fill header cells with a light blue background
header_rect0 = rectangle(point(hdr0.x0, hdr0.y1), hdr0.width, hdr0.height, pivot="corner")
header_rect1 = rectangle(point(hdr1.x0, hdr1.y1), hdr1.width, hdr1.height, pivot="corner")
fill(header_rect0, color="steelblue", opacity=0.3)
fill(header_rect1, color="steelblue", opacity=0.3)

label_text("Cups of Flour", at=(hdr0.cx, hdr0.cy))
label_text("Cups of Sugar", at=(hdr1.cx, hdr1.cy))

# Data rows
data = [
    (1, 2),
    (2, 4),
    (3, 6),
    (4, 8),
]

for i, (flour, sugar) in enumerate(data):
    row = i + 1
    c0 = tg.cell(row, 0)
    c1 = tg.cell(row, 1)
    label_text(str(flour), at=(c0.cx, c0.cy))
    label_text(str(sugar), at=(c1.cx, c1.cy))
