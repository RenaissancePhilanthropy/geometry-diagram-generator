# Rectangular prism: length=4, width=2, height=3
# L=4, W=2, H=3
#
# Net layout (cross shape):
#
#         [Top 4x2]         row y=3..5
# [Left]  [Front]  [Right] [Back]   row y=0..3
#         [Bottom 4x2]      row y=-2..0
#
# Columns:
#   Left:   x=0..2  (width=W=2)
#   Front:  x=2..6  (width=L=4)
#   Right:  x=6..8  (width=W=2)
#   Back:   x=8..12 (width=L=4)
#
# Rows:
#   Bottom: y=-3..0   (height=H=3)
#   Middle: y=0..3    (height=H=3)  — Left/Front/Right/Back
#   Top:    y=3..5    (height=W=2)

L = 4  # length
W = 2  # width
H = 3  # height

canvas(x_range=(-1, 14), y_range=(-4, 6), grid=True, grid_step=1)

# --- Front face: 4 x 3, x=[2,6], y=[0,3] ---
f_bl = point(2, 0)
f_br = point(6, 0)
f_tr = point(6, 3)
f_tl = point(2, 3)
front = polygon(f_bl, f_br, f_tr, f_tl)

# --- Back face: 4 x 3, x=[8,12], y=[0,3] ---
bk_bl = point(8, 0)
bk_br = point(12, 0)
bk_tr = point(12, 3)
bk_tl = point(8, 3)
back = polygon(bk_bl, bk_br, bk_tr, bk_tl)

# --- Left face: 2 x 3, x=[0,2], y=[0,3] ---
l_bl = point(0, 0)
l_br = point(2, 0)
l_tr = point(2, 3)
l_tl = point(0, 3)
left_face = polygon(l_bl, l_br, l_tr, l_tl)

# --- Right face: 2 x 3, x=[6,8], y=[0,3] ---
r_bl = point(6, 0)
r_br = point(8, 0)
r_tr = point(8, 3)
r_tl = point(6, 3)
right_face = polygon(r_bl, r_br, r_tr, r_tl)

# --- Top face: 4 x 2, x=[2,6], y=[3,5] ---
t_bl = point(2, 3)
t_br = point(6, 3)
t_tr = point(6, 5)
t_tl = point(2, 5)
top_face = polygon(t_bl, t_br, t_tr, t_tl)

# --- Bottom face: 4 x 2, x=[2,6], y=[-2,0] ---  (H=3 below)
bt_bl = point(2, -3)
bt_br = point(6, -3)
bt_tr = point(6, 0)
bt_tl = point(2, 0)
bottom_face = polygon(bt_bl, bt_br, bt_tr, bt_tl)

# Draw all faces with distinct fills
fill(front,       color="lightskyblue",  opacity=0.5)
fill(back,        color="lightcoral",    opacity=0.5)
fill(left_face,   color="lightgreen",    opacity=0.5)
fill(right_face,  color="khaki",         opacity=0.5)
fill(top_face,    color="plum",          opacity=0.5)
fill(bottom_face, color="peachpuff",     opacity=0.5)

draw(front)
draw(back)
draw(left_face)
draw(right_face)
draw(top_face)
draw(bottom_face)

# Label each face using label_in_polygon (width-aware, auto-wraps)
label_in_polygon(front,       "Front\n4 × 3")
label_in_polygon(back,        "Back\n4 × 3")
label_in_polygon(left_face,   "Left\n2 × 3")
label_in_polygon(right_face,  "Right\n2 × 3")
label_in_polygon(top_face,    "Top\n4 × 2")
label_in_polygon(bottom_face, "Bottom\n4 × 3")
