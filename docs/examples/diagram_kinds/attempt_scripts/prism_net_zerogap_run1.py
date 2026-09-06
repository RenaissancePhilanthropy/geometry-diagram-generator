# Rectangular prism: length=4 (x), width=2 (y), height=3 (z)
# L=4, W=2, H=3
# Face dimensions:
#   Front/Back: 4 x 3
#   Left/Right: 2 x 3
#   Top/Bottom: 4 x 2

# Net layout (cross shape):
#
#         [Top]       col1, row2
# [Left] [Front] [Right] [Back]    row1
#         [Bottom]    col1, row0
#
# Using a standard cross layout:
# - Bottom at bottom: x in [2,6], y in [0,2]
# - Front (center): x in [2,6], y in [2,5]
# - Top: x in [2,6], y in [5,7]
# - Left: x in [0,2], y in [2,5]
# - Right: x in [6,8], y in [2,5]
# - Back: x in [8,12], y in [2,5]

L = 4  # length (x-dimension)
W = 2  # width (y-dimension)
H = 3  # height (z-dimension)

# Column starts
x0 = 0  # left face starts here
x1 = W       # = 2, front/top/bottom start here
x2 = W + L   # = 6, right face starts here
x3 = W + L + W  # = 8, back face starts here
x4 = W + L + W + L  # = 12, back face ends here

# Row starts
y0 = 0        # bottom face starts here
y1 = W        # = 2, front/left/right/back starts here
y2 = W + H    # = 5, top starts here
y3 = W + H + W  # = 7, top ends here

canvas(x_range=(-0.5, 12.5), y_range=(-0.5, 7.5), grid=True, grid_step=1)

# --- Define all 6 face polygons ---

# Bottom face: 4 x 2, shares top edge with Front bottom edge
p_bot_bl = point(x1, y0)
p_bot_br = point(x2, y0)
p_bot_tr = point(x2, y1)
p_bot_tl = point(x1, y1)
face_bottom = polygon(p_bot_bl, p_bot_br, p_bot_tr, p_bot_tl)

# Front face: 4 x 3
p_fro_bl = point(x1, y1)
p_fro_br = point(x2, y1)
p_fro_tr = point(x2, y2)
p_fro_tl = point(x1, y2)
face_front = polygon(p_fro_bl, p_fro_br, p_fro_tr, p_fro_tl)

# Top face: 4 x 2, shares bottom edge with Front top edge
p_top_bl = point(x1, y2)
p_top_br = point(x2, y2)
p_top_tr = point(x2, y3)
p_top_tl = point(x1, y3)
face_top = polygon(p_top_bl, p_top_br, p_top_tr, p_top_tl)

# Left face: 2 x 3, shares right edge with Front left edge
p_lft_bl = point(x0, y1)
p_lft_br = point(x1, y1)
p_lft_tr = point(x1, y2)
p_lft_tl = point(x0, y2)
face_left = polygon(p_lft_bl, p_lft_br, p_lft_tr, p_lft_tl)

# Right face: 2 x 3, shares left edge with Front right edge
p_rgt_bl = point(x2, y1)
p_rgt_br = point(x3, y1)
p_rgt_tr = point(x3, y2)
p_rgt_tl = point(x2, y2)
face_right = polygon(p_rgt_bl, p_rgt_br, p_rgt_tr, p_rgt_tl)

# Back face: 4 x 3, shares left edge with Right right edge
p_bck_bl = point(x3, y1)
p_bck_br = point(x4, y1)
p_bck_tr = point(x4, y2)
p_bck_tl = point(x3, y2)
face_back = polygon(p_bck_bl, p_bck_br, p_bck_tr, p_bck_tl)

# --- Draw all faces with distinct fill colors ---
fill(face_bottom, color="lightblue", opacity=0.5)
fill(face_front, color="lightyellow", opacity=0.5)
fill(face_top, color="lightgreen", opacity=0.5)
fill(face_left, color="lightsalmon", opacity=0.5)
fill(face_right, color="plum", opacity=0.5)
fill(face_back, color="peachpuff", opacity=0.5)

draw(face_bottom, thick=True)
draw(face_front, thick=True)
draw(face_top, thick=True)
draw(face_left, thick=True)
draw(face_right, thick=True)
draw(face_back, thick=True)

# --- Label all faces ---
label_in_polygon(face_bottom, "Bottom\n4 × 2")
label_in_polygon(face_front,  "Front\n4 × 3")
label_in_polygon(face_top,    "Top\n4 × 2")
label_in_polygon(face_left,   "Left\n2 × 3")
label_in_polygon(face_right,  "Right\n2 × 3")
label_in_polygon(face_back,   "Back\n4 × 3")
