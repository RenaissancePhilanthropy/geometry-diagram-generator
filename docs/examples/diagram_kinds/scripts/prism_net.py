# Rectangular prism: 4 units long (L), 2 units wide (W), 3 units tall (H)
# L=4, W=2, H=3
#
# Net layout (cross shape with generous spacing):
# Gap between faces = 1 unit
#
# Layout plan (with 1-unit gaps between faces):
#
#         [Top 4x2]
#         [Front 4x3]
# [Left]  [Bottom 4x2]  [Right]
#         [Back 4x3]
#
# Let's place faces with 1.5-unit gaps for clarity.
# Using a plus/cross layout:
#
# Columns: Left | Bottom/Top/Front/Back column | Right
# The "spine" column is centered, with Top above Front, Front above Bottom, Bottom above Back
# Left and Right attach to the sides of the Bottom face
#
# Let's define coordinates carefully:
# Gap = 1.5
# L = 4, W = 2, H = 3
#
# Spine column x: from 0 to 4
# 
# Bottom row (y): Back face
# Next row: Bottom face
# Next row: Front face  
# Next row: Top face
#
# With gaps of 1.5 between each face row:
# y positions (bottom of each face):
#   Back:   y=0, height=H=3   -> top at y=3
#   gap 1.5
#   Bottom: y=4.5, height=W=2 -> top at y=6.5
#   gap 1.5
#   Front:  y=8, height=H=3   -> top at y=11
#   gap 1.5
#   Top:    y=12.5, height=W=2 -> top at y=14.5
#
# Left attaches to Left side of Bottom face:
#   x: from -(1.5+W) to -1.5 = from -3.5 to -1.5
#   y: same as Bottom face: 4.5 to 6.5
#
# Right attaches to Right side of Bottom face:
#   x: from 4+1.5 to 4+1.5+W = 5.5 to 7.5
#   y: same as Bottom face: 4.5 to 6.5

gap = 1.5
L = 4
W = 2
H = 3

# X range for spine column: 0 to L=4
spine_x0 = 0
spine_x1 = L  # =4

# Y positions
back_y0 = 0
back_y1 = back_y0 + H  # =3

bottom_y0 = back_y1 + gap  # =4.5
bottom_y1 = bottom_y0 + W  # =6.5

front_y0 = bottom_y1 + gap  # =8
front_y1 = front_y0 + H    # =11

top_y0 = front_y1 + gap    # =12.5
top_y1 = top_y0 + W        # =14.5

# Left face: W wide, H tall (W=2, H=3) -- actually Left face is W x H
# Left face dimensions: width=W=2 (in x), height=H=3... wait
# Let me reconsider face dimensions:
# Front/Back face: L x H = 4 x 3
# Top/Bottom face: L x W = 4 x 2
# Left/Right face: W x H = 2 x 3
#
# Left and Right faces attach to sides of the Bottom face (4x2)
# Bottom face spans y: bottom_y0 to bottom_y1 (height=W=2) -- correct, the W dimension
# Left/Right faces have height W=2 (matching the bottom face height) and width H=3
# Wait: Left face is W x H. In the net, it attaches to the left side of Bottom.
# Bottom face has dimension L (horizontal) x W (vertical).
# Left face is W x H. When folded, it rotates around the left edge of Bottom.
# The left edge of Bottom is W=2 tall. Left face has one edge of length W and the other of H=3.
# So Left face in the net: height=W=2 (matches bottom), width=H=3.
# It extends to the LEFT of the spine column.

left_x1 = spine_x0 - gap  # =-1.5
left_x0 = left_x1 - H     # =-4.5   (width=H=3 extending left)
left_y0 = bottom_y0        # =4.5
left_y1 = bottom_y1        # =6.5

right_x0 = spine_x1 + gap  # =5.5
right_x1 = right_x0 + H    # =8.5   (width=H=3 extending right)
right_y0 = bottom_y0        # =4.5
right_y1 = bottom_y1        # =6.5

# Canvas bounds with margin
margin = 1.5
canvas_x0 = left_x0 - margin    # =-4.5-1.5=-6
canvas_x1 = right_x1 + margin   # =8.5+1.5=10
canvas_y0 = back_y0 - margin    # =-1.5
canvas_y1 = top_y1 + margin     # =14.5+1.5=16

canvas(x_range=(canvas_x0, canvas_x1), y_range=(canvas_y0, canvas_y1), grid=True, grid_step=1)

# --- Define face polygons ---

# Back face: 4 x 3
p_back_bl = point(spine_x0, back_y0)
p_back_br = point(spine_x1, back_y0)
p_back_tr = point(spine_x1, back_y1)
p_back_tl = point(spine_x0, back_y1)
face_back = polygon(p_back_bl, p_back_br, p_back_tr, p_back_tl)

# Bottom face: 4 x 2
p_bot_bl = point(spine_x0, bottom_y0)
p_bot_br = point(spine_x1, bottom_y0)
p_bot_tr = point(spine_x1, bottom_y1)
p_bot_tl = point(spine_x0, bottom_y1)
face_bottom = polygon(p_bot_bl, p_bot_br, p_bot_tr, p_bot_tl)

# Front face: 4 x 3
p_front_bl = point(spine_x0, front_y0)
p_front_br = point(spine_x1, front_y0)
p_front_tr = point(spine_x1, front_y1)
p_front_tl = point(spine_x0, front_y1)
face_front = polygon(p_front_bl, p_front_br, p_front_tr, p_front_tl)

# Top face: 4 x 2
p_top_bl = point(spine_x0, top_y0)
p_top_br = point(spine_x1, top_y0)
p_top_tr = point(spine_x1, top_y1)
p_top_tl = point(spine_x0, top_y1)
face_top = polygon(p_top_bl, p_top_br, p_top_tr, p_top_tl)

# Left face: 3 x 2 (H x W)
p_left_bl = point(left_x0, left_y0)
p_left_br = point(left_x1, left_y0)
p_left_tr = point(left_x1, left_y1)
p_left_tl = point(left_x0, left_y1)
face_left = polygon(p_left_bl, p_left_br, p_left_tr, p_left_tl)

# Right face: 3 x 2 (H x W)
p_right_bl = point(right_x0, right_y0)
p_right_br = point(right_x1, right_y0)
p_right_tr = point(right_x1, right_y1)
p_right_tl = point(right_x0, right_y1)
face_right = polygon(p_right_bl, p_right_br, p_right_tr, p_right_tl)

# --- Fill faces with distinct colors ---
fill(face_back,   color="lightblue",   opacity=0.5)
fill(face_bottom, color="lightyellow", opacity=0.5)
fill(face_front,  color="lightgreen",  opacity=0.5)
fill(face_top,    color="lightsalmon", opacity=0.5)
fill(face_left,   color="plum",        opacity=0.5)
fill(face_right,  color="lightcoral",  opacity=0.5)

# --- Draw face outlines ---
draw(face_back,   thick=True)
draw(face_bottom, thick=True)
draw(face_front,  thick=True)
draw(face_top,    thick=True)
draw(face_left,   thick=True)
draw(face_right,  thick=True)

# --- Label each face using label_in_polygon ---
label_in_polygon(face_back,   "Back\n4 x 3")
label_in_polygon(face_bottom, "Bottom\n4 x 2")
label_in_polygon(face_front,  "Front\n4 x 3")
label_in_polygon(face_top,    "Top\n4 x 2")
label_in_polygon(face_left,   "Left\n2 x 3")
label_in_polygon(face_right,  "Right\n2 x 3")
