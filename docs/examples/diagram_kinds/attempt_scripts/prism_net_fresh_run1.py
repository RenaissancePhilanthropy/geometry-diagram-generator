# Rectangular prism: 4 units long (L), 2 units wide (W), 3 units tall (H)
# L=4, W=2, H=3
#
# Net layout (cross/plus shape) with generous spacing (gap=1 between faces):
#
#          [Top 4x2]
# [Left]  [Front 4x3] [Right]  [Back 4x3]
#          [Bottom 4x2]
#
# Face dimensions:
#  Front/Back: 4 wide x 3 tall
#  Left/Right: 2 wide x 3 tall
#  Top/Bottom: 4 wide x 2 tall
#
# Using gap=1 between faces for clear spacing.

L = 4   # length (x-direction for Front/Back)
W = 2   # width  (x-direction for Left/Right)
H = 3   # height (y-direction for Front/Back/Left/Right)

gap = 1.5  # spacing between adjacent faces

canvas(x_range=(-6, 16), y_range=(-5, 13), grid=True, grid_step=1)

# --- Layout origin: Front face anchored so its bottom-left is at (0, 0) ---
# Front face: 4 wide x 3 tall, bottom-left at (0, 0)
front_x0 = 0
front_y0 = 0

# Bottom face: 4 wide x 2 tall, sits below Front with gap
bottom_x0 = front_x0
bottom_y0 = front_y0 - gap - W   # gap below front, then 2 tall

# Top face: 4 wide x 2 tall, sits above Front with gap
top_x0 = front_x0
top_y0 = front_y0 + H + gap

# Left face: 2 wide x 3 tall, sits to left of Front with gap
left_x0 = front_x0 - gap - W
left_y0 = front_y0

# Right face: 2 wide x 3 tall, sits to right of Front with gap
right_x0 = front_x0 + L + gap
right_y0 = front_y0

# Back face: 4 wide x 3 tall, sits to right of Right with gap
back_x0 = right_x0 + W + gap
back_y0 = front_y0

# --- Build face polygons ---

# Front: 4 x 3
fp0 = point(front_x0,       front_y0)
fp1 = point(front_x0 + L,   front_y0)
fp2 = point(front_x0 + L,   front_y0 + H)
fp3 = point(front_x0,       front_y0 + H)
front_face = polygon(fp0, fp1, fp2, fp3)

# Back: 4 x 3
bp0 = point(back_x0,       back_y0)
bp1 = point(back_x0 + L,   back_y0)
bp2 = point(back_x0 + L,   back_y0 + H)
bp3 = point(back_x0,       back_y0 + H)
back_face = polygon(bp0, bp1, bp2, bp3)

# Left: 2 x 3
lp0 = point(left_x0,       left_y0)
lp1 = point(left_x0 + W,   left_y0)
lp2 = point(left_x0 + W,   left_y0 + H)
lp3 = point(left_x0,       left_y0 + H)
left_face = polygon(lp0, lp1, lp2, lp3)

# Right: 2 x 3
rp0 = point(right_x0,       right_y0)
rp1 = point(right_x0 + W,   right_y0)
rp2 = point(right_x0 + W,   right_y0 + H)
rp3 = point(right_x0,       right_y0 + H)
right_face = polygon(rp0, rp1, rp2, rp3)

# Top: 4 x 2
tp0 = point(top_x0,       top_y0)
tp1 = point(top_x0 + L,   top_y0)
tp2 = point(top_x0 + L,   top_y0 + W)
tp3 = point(top_x0,       top_y0 + W)
top_face = polygon(tp0, tp1, tp2, tp3)

# Bottom: 4 x 2
btp0 = point(bottom_x0,       bottom_y0)
btp1 = point(bottom_x0 + L,   bottom_y0)
btp2 = point(bottom_x0 + L,   bottom_y0 + W)
btp3 = point(bottom_x0,       bottom_y0 + W)
bottom_face = polygon(btp0, btp1, btp2, btp3)

# --- Fill faces with distinct colors ---
fill(front_face,  color="lightblue",   opacity=0.6)
fill(back_face,   color="lightyellow", opacity=0.6)
fill(left_face,   color="lightgreen",  opacity=0.6)
fill(right_face,  color="lightsalmon", opacity=0.6)
fill(top_face,    color="plum",        opacity=0.6)
fill(bottom_face, color="peachpuff",   opacity=0.6)

# --- Draw face outlines ---
draw(front_face,  thick=True)
draw(back_face,   thick=True)
draw(left_face,   thick=True)
draw(right_face,  thick=True)
draw(top_face,    thick=True)
draw(bottom_face, thick=True)

# --- Labels ---
label_in_polygon(front_face,  "Front\n4 × 3")
label_in_polygon(back_face,   "Back\n4 × 3")
label_in_polygon(left_face,   "Left\n2 × 3")
label_in_polygon(right_face,  "Right\n2 × 3")
label_in_polygon(top_face,    "Top\n4 × 2")
label_in_polygon(bottom_face, "Bottom\n4 × 2")
