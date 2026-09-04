# Set up canvas with margin
canvas(x_range=(-2, 13), y_range=(-2, 13))

# Build affine mapping for very different axis ranges
axes = chart_axes(x_data_range=(0, 8), y_data_range=(0, 100), geom_size=10.0)

# --- Axes ---
origin_pt  = point(*axes.map(0, 0))
x_end_pt   = point(*axes.map(8, 0))
y_end_pt   = point(*axes.map(0, 100))

draw(segment(origin_pt, x_end_pt), thick=True)   # x-axis
draw(segment(origin_pt, y_end_pt), thick=True)   # y-axis

# --- X-axis ticks and labels (hours 0,2,4,6,8) ---
for hrs in [0, 2, 4, 6, 8]:
    gx, gy = axes.map(hrs, 0)
    tick_top    = point(gx, gy + 0.15)
    tick_bottom = point(gx, gy - 0.15)
    draw(segment(tick_top, tick_bottom))
    label_text(str(hrs), at=(gx, gy - 0.45))

# X-axis title
label_text("Hours", at=(axes.map(4, 0)[0], axes.map(4, 0)[1] - 1.0))

# --- Y-axis ticks and labels (scores 0,25,50,75,100) ---
for score in [0, 25, 50, 75, 100]:
    gx, gy = axes.map(0, score)
    tick_left  = point(gx - 0.15, gy)
    tick_right = point(gx + 0.15, gy)
    draw(segment(tick_left, tick_right))
    label_text(str(score), at=(gx - 0.7, gy))

# Y-axis title
label_text("Score", at=(axes.map(0, 50)[0] - 1.4, axes.map(0, 50)[1]))

# --- Data points ---
data = [(1, 55), (2, 60), (3, 68), (4, 74), (5, 85), (6, 90)]

for hrs, score in data:
    gx, gy = axes.map(hrs, score)
    pt = point(gx, gy)
    draw_points(pt)
    # Label with true score value, offset slightly above-right
    label_text(str(score), at=(gx + 0.3, gy + 0.3))

# --- Line of best fit ---
# Simple linear regression on the data
n = len(data)
sum_x  = sum(d[0] for d in data)
sum_y  = sum(d[1] for d in data)
sum_xy = sum(d[0]*d[1] for d in data)
sum_x2 = sum(d[0]**2 for d in data)
slope     = (n*sum_xy - sum_x*sum_y) / (n*sum_x2 - sum_x**2)
intercept = (sum_y - slope*sum_x) / n

# Extend line to x=0 and x=8 (data range)
x_lo, x_hi = 0, 8
y_lo = slope * x_lo + intercept
y_hi = slope * x_hi + intercept

fit_start = point(*axes.map(x_lo, y_lo))
fit_end   = point(*axes.map(x_hi, y_hi))
draw(segment(fit_start, fit_end), color="red", thick=True, dashed=True)
