# Rectangular prism: 4 (L) x 2 (W) x 3 (H)
# Face dimensions:
#   Front/Back: 4 wide x 3 tall
#   Left/Right: 2 wide x 3 tall
#   Top/Bottom: 4 wide x 2 tall
#
# Net layout (cross/T shape) with generous spacing (gap=1 between faces):
#
#   We'll use a classic cross layout:
#
#             [Top   4x2]
#   [Left 2x3][Front 4x3][Right 2x3][Back 4x3]
#             [Bottom4x2]
#
# Gap between faces: 1 unit

gap = 1.0
L = 4.0  # length
W = 2.0  # width
H = 3.0  # height

# Row of: Left, Front, Right, Back  (all height H=3)
# Middle row y range: let's say y from 0 to H=3
# Left face: x from 0 to W=2
# Front face: x from W+gap to W+gap+L = 2+1+4=7
# Right face: x from W+gap+L+gap to W+gap+L+gap+W = 7+1+2=10
# Back face: x from W+gap+L+gap+W+gap to W+gap+L+gap+W+gap+L = 10+1+4=15

mid_y0 = 0.0
mid_y1 = H  # 3

left_x0 = 0.0
left_x1 = W  # 2

front_x0 = left_x1 + gap  # 3
front_x1 = front_x0 + L   # 7

right_x0 = front_x1 + gap  # 8
right_x1 = right_x0 + W   # 10

back_x0 = right_x1 + gap  # 11
back_x1 = back_x0 + L    # 15

# Top face: above Front, y from H+gap to H+gap+W = 3+1+2=6
top_x0 = front_x0
top_x1 = front_x1
top_y0 = mid_y1 + gap   # 4
top_y1 = top_y0 + W     # 6

# Bottom face: below Front, y from -(gap+W) to 0 = -3 to 0
bot_x0 = front_x0
bot_x1 = front_x1
bot_y1 = mid_y0 - gap   # -1
bot_y0 = bot_y1 - W     # -3

# Canvas bounds with margin
margin = 1.5
canvas(
    x_range=(-margin, back_x1 + margin),
    y_range=(bot_y0 - margin, top_y1 + margin),
    grid=True,
    grid_step=1.0
)

# --- Build face polygons ---

# Front: 4x3
p_front_bl = point(front_x0, mid_y0)
p_front_br = point(front_x1, mid_y0)
p_front_tr = point(front_x1, mid_y1)
p_front_tl = point(front_x0, mid_y1)
face_front = polygon(p_front_bl, p_front_br, p_front_tr, p_front_tl)

# Back: 4x3
p_back_bl = point(back_x0, mid_y0)
p_back_br = point(back_x1, mid_y0)
p_back_tr = point(back_x1, mid_y1)
p_back_tl = point(back_x0, mid_y1)
face_back = polygon(p_back_bl, p_back_br, p_back_tr, p_back_tl)

# Left: 2x3
p_left_bl = point(left_x0, mid_y0)
p_left_br = point(left_x1, mid_y0)
p_left_tr = point(left_x1, mid_y1)
p_left_tl = point(left_x0, mid_y1)
face_left = polygon(p_left_bl, p_left_br, p_left_tr, p_left_tl)

# Right: 2x3
p_right_bl = point(right_x0, mid_y0)
p_right_br = point(right_x1, mid_y0)
p_right_tr = point(right_x1, mid_y1)
p_right_tl = point(right_x0, mid_y1)
face_right = polygon(p_right_bl, p_right_br, p_right_tr, p_right_tl)

# Top: 4x2
p_top_bl = point(top_x0, top_y0)
p_top_br = point(top_x1, top_y0)
p_top_tr = point(top_x1, top_y1)
p_top_tl = point(top_x0, top_y1)
face_top = polygon(p_top_bl, p_top_br, p_top_tr, p_top_tl)

# Bottom: 4x2
p_bot_bl = point(bot_x0, bot_y0)
p_bot_br = point(bot_x1, bot_y0)
p_bot_tr = point(bot_x1, bot_y1)
p_bot_tl = point(bot_x0, bot_y1)
face_bot = polygon(p_bot_bl, p_bot_br, p_bot_tr, p_bot_tl)

# --- Fill faces with distinct colors ---
fill(face_front,  color="lightsteelblue",  opacity=0.7)
fill(face_back,   color="lightsalmon",     opacity=0.7)
fill(face_left,   color="lightgreen",      opacity=0.7)
fill(face_right,  color="plum",            opacity=0.7)
fill(face_top,    color="lightyellow",     opacity=0.7)
fill(face_bot,    color="peachpuff",       opacity=0.7)

# --- Draw face outlines ---
draw(face_front, thick=True)
draw(face_back,  thick=True)
draw(face_left,  thick=True)
draw(face_right, thick=True)
draw(face_top,   thick=True)
draw(face_bot,   thick=True)

# --- Labels ---
label_in_polygon(face_front, "Front\n4 x 3")
label_in_polygon(face_back,  "Back\n4 x 3")
label_in_polygon(face_left,  "Left\n2 x 3")
label_in_polygon(face_right, "Right\n2 x 3")
label_in_polygon(face_top,   "Top\n4 x 2")
label_in_polygon(face_bot,   "Bottom\n4 x 2")
