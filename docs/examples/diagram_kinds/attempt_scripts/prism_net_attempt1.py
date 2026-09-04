# Rectangular prism: 4 units long (L=4), 2 units wide (W=2), 3 units tall (H=3)
# Faces:
#   Top/Bottom: 4 x 2
#   Front/Back: 4 x 3
#   Left/Right: 2 x 3
#
# Classic cross-shaped net layout (with generous spacing/gaps):
# We'll use a cross layout:
#
#           [Top: 4x2]
#  [Left:2x3][Front:4x3][Right:2x3]
#           [Bottom:4x2]
#
# We add a gap of 0.8 between each face for clear empty space.
#
# Let's define everything carefully with coordinates.

GAP = 0.8  # gap between faces

L = 4.0  # length
W = 2.0  # width
H = 3.0  # height

# Layout the cross:
# Row 1 (middle row): Left(W x H), Front(L x H), Right(W x H)
# Row 2 (top of middle): Top(L x W) centered above Front
# Row 3 (bottom of middle): Bottom(L x W) centered below Front

# X positions:
# Left face starts at x=0, width=W=2
# Gap
# Front face starts at x=W+GAP, width=L=4
# Gap
# Right face starts at x=W+GAP+L+GAP, width=W=2

x_left   = 0.0
x_front  = x_left + W + GAP
x_right  = x_front + L + GAP

# Y positions (bottom of each face):
# Middle row (Front, Left, Right) at y=0, height=H=3
y_mid_bottom = 0.0
y_mid_top    = y_mid_bottom + H  # = 3.0

# Top face: above front face, with gap
y_top_bottom = y_mid_top + GAP
y_top_top    = y_top_bottom + W  # = 3 + 0.8 + 2 = 5.8

# Bottom face: below middle row, with gap
y_bot_top    = y_mid_bottom - GAP
y_bot_bottom = y_bot_top - W  # = -0.8 - 2 = -2.8

# Canvas bounds: add generous margin
MARGIN = 1.2

x_min = x_left - MARGIN
x_max = x_right + W + MARGIN
y_min = y_bot_bottom - MARGIN
y_max = y_top_top + MARGIN

canvas(x_range=(x_min, x_max), y_range=(y_min, y_max), grid=True, grid_step=1.0)

# --- Define all face corners as polygons ---

# Front face: L x H (4 x 3)
p_fr_bl = point(x_front,       y_mid_bottom)
p_fr_br = point(x_front + L,   y_mid_bottom)
p_fr_tr = point(x_front + L,   y_mid_top)
p_fr_tl = point(x_front,       y_mid_top)
front = polygon(p_fr_bl, p_fr_br, p_fr_tr, p_fr_tl)

# Left face: W x H (2 x 3)
p_lf_bl = point(x_left,       y_mid_bottom)
p_lf_br = point(x_left + W,   y_mid_bottom)
p_lf_tr = point(x_left + W,   y_mid_top)
p_lf_tl = point(x_left,       y_mid_top)
left_face = polygon(p_lf_bl, p_lf_br, p_lf_tr, p_lf_tl)

# Right face: W x H (2 x 3)
p_rf_bl = point(x_right,       y_mid_bottom)
p_rf_br = point(x_right + W,   y_mid_bottom)
p_rf_tr = point(x_right + W,   y_mid_top)
p_rf_tl = point(x_right,       y_mid_top)
right_face = polygon(p_rf_bl, p_rf_br, p_rf_tr, p_rf_tl)

# Top face: L x W (4 x 2) — above front
p_tp_bl = point(x_front,       y_top_bottom)
p_tp_br = point(x_front + L,   y_top_bottom)
p_tp_tr = point(x_front + L,   y_top_top)
p_tp_tl = point(x_front,       y_top_top)
top_face = polygon(p_tp_bl, p_tp_br, p_tp_tr, p_tp_tl)

# Bottom face: L x W (4 x 2) — below front
p_bt_tl = point(x_front,       y_bot_top)
p_bt_tr = point(x_front + L,   y_bot_top)
p_bt_br = point(x_front + L,   y_bot_bottom)
p_bt_bl = point(x_front,       y_bot_bottom)
bottom_face = polygon(p_bt_bl, p_bt_br, p_bt_tr, p_bt_tl)

# --- Fill faces with distinct light colors ---
fill(front,       color="lightsteelblue",  opacity=0.55)
fill(left_face,   color="lightsalmon",     opacity=0.55)
fill(right_face,  color="lightsalmon",     opacity=0.55)
fill(top_face,    color="lightgreen",      opacity=0.55)
fill(bottom_face, color="lightgreen",      opacity=0.55)

# --- Draw outlines ---
draw(front,       thick=True)
draw(left_face,   thick=True)
draw(right_face,  thick=True)
draw(top_face,    thick=True)
draw(bottom_face, thick=True)

# --- Labels: centered inside each face ---
# Front: 4 x 3  — center at (x_front + L/2, y_mid_bottom + H/2)
label_text("4 × 3", at=(x_front + L/2,     y_mid_bottom + H/2))

# Left: 2 x 3
label_text("2 × 3", at=(x_left + W/2,      y_mid_bottom + H/2))

# Right: 2 x 3
label_text("2 × 3", at=(x_right + W/2,     y_mid_bottom + H/2))

# Top: 4 x 2
label_text("4 × 2", at=(x_front + L/2,     y_top_bottom + W/2))

# Bottom: 4 x 2
label_text("4 × 2", at=(x_front + L/2,     y_bot_bottom + W/2))
