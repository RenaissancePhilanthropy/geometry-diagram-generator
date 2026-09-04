# Rectangular prism net: 4 (length) x 2 (width) x 3 (height)
# Faces:
#   Top/Bottom: 4 x 2
#   Front/Back: 4 x 3
#   Left/Right: 2 x 3
#
# Classic cross layout (with generous spacing):
#   Gap between faces = 1.5 units
#
#         [Top 4x2]
#   [Left] [Front 4x3] [Right]
#         [Bottom 4x2]
#         [Back 4x3]  (folded below bottom)
#
# Let's place Front face as the central anchor.
# Front: 4 wide x 3 tall
# We'll use gap=1.5 between each face.

gap = 1.5
L = 4   # length
W = 2   # width
H = 3   # height

# --- Front face: center column, row 0 ---
# Anchor front at (0, 0) bottom-left
front_x0 = 0
front_y0 = 0

# Front corners
fA = point(front_x0,       front_y0)        # BL
fB = point(front_x0 + L,   front_y0)        # BR
fC = point(front_x0 + L,   front_y0 + H)    # TR
fD = point(front_x0,       front_y0 + H)    # TL
front_face = polygon(fA, fB, fC, fD)

# --- Top face: 4 x 2, above front, separated by gap ---
top_y0 = front_y0 + H + gap
tA = point(front_x0,       top_y0)
tB = point(front_x0 + L,   top_y0)
tC = point(front_x0 + L,   top_y0 + W)
tD = point(front_x0,       top_y0 + W)
top_face = polygon(tA, tB, tC, tD)

# --- Bottom face: 4 x 2, below front, separated by gap ---
bot_y0 = front_y0 - gap - W
bA = point(front_x0,       bot_y0)
bB = point(front_x0 + L,   bot_y0)
bC = point(front_x0 + L,   bot_y0 + W)
bD = point(front_x0,       bot_y0 + W)
bot_face = polygon(bA, bB, bC, bD)

# --- Back face: 4 x 3, below bottom, separated by gap ---
back_y0 = bot_y0 - gap - H
baA = point(front_x0,       back_y0)
baB = point(front_x0 + L,   back_y0)
baC = point(front_x0 + L,   back_y0 + H)
baD = point(front_x0,       back_y0 + H)
back_face = polygon(baA, baB, baC, baD)

# --- Left face: 2 x 3, left of front, separated by gap ---
left_x0 = front_x0 - gap - W
lA = point(left_x0,       front_y0)
lB = point(left_x0 + W,   front_y0)
lC = point(left_x0 + W,   front_y0 + H)
lD = point(left_x0,       front_y0 + H)
left_face = polygon(lA, lB, lC, lD)

# --- Right face: 2 x 3, right of front, separated by gap ---
right_x0 = front_x0 + L + gap
rA = point(right_x0,       front_y0)
rB = point(right_x0 + W,   front_y0)
rC = point(right_x0 + W,   front_y0 + H)
rD = point(right_x0,       front_y0 + H)
right_face = polygon(rA, rB, rC, rD)

# --- Canvas ---
margin = 2.5
all_xs = [left_x0, right_x0 + W, front_x0, front_x0 + L]
all_ys = [back_y0, top_y0 + W]
canvas(
    x_range=(left_x0 - margin, right_x0 + W + margin),
    y_range=(back_y0 - margin, top_y0 + W + margin),
    grid=True, grid_step=1
)

# --- Fill each face with a distinct soft color ---
fill(front_face, color="lightblue",   opacity=0.55)
fill(back_face,  color="lightyellow", opacity=0.55)
fill(top_face,   color="lightgreen",  opacity=0.55)
fill(bot_face,   color="lightgreen",  opacity=0.55)
fill(left_face,  color="lightsalmon", opacity=0.55)
fill(right_face, color="lightsalmon", opacity=0.55)

# --- Draw outlines ---
draw(front_face, thick=True)
draw(back_face,  thick=True)
draw(top_face,   thick=True)
draw(bot_face,   thick=True)
draw(left_face,  thick=True)
draw(right_face, thick=True)

# --- Face title labels (centered in each face) ---
label_offset_in = 0.35

# Front (center of face)
label_text("FRONT", at=(front_x0 + L/2, front_y0 + H/2 + 0.3))
label_text("4 × 3", at=(front_x0 + L/2, front_y0 + H/2 - 0.3))

# Back
label_text("BACK",  at=(front_x0 + L/2, back_y0 + H/2 + 0.3))
label_text("4 × 3", at=(front_x0 + L/2, back_y0 + H/2 - 0.3))

# Top
label_text("TOP",   at=(front_x0 + L/2, top_y0 + W/2 + 0.25))
label_text("4 × 2", at=(front_x0 + L/2, top_y0 + W/2 - 0.25))

# Bottom
label_text("BOTTOM",at=(front_x0 + L/2, bot_y0 + W/2 + 0.25))
label_text("4 × 2", at=(front_x0 + L/2, bot_y0 + W/2 - 0.25))

# Left
label_text("LEFT",  at=(left_x0 + W/2, front_y0 + H/2 + 0.3))
label_text("2 × 3", at=(left_x0 + W/2, front_y0 + H/2 - 0.3))

# Right
label_text("RIGHT", at=(right_x0 + W/2, front_y0 + H/2 + 0.3))
label_text("2 × 3", at=(right_x0 + W/2, front_y0 + H/2 - 0.3))

# --- Dimension annotations on the edges (outside the faces) ---
# Front face: bottom edge label "4" below
seg_front_bot = segment(fA, fB)
seg_front_bot.label("4", pos=0.5)

# Front face: left edge label "3"
seg_front_left = segment(fA, fD)
seg_front_left.label("3", pos=0.5)

# Top face: top edge label "4"
seg_top_top = segment(tD, tC)
seg_top_top.label("4", pos=0.5)

# Top face: left edge label "2"
seg_top_left = segment(tA, tD)
seg_top_left.label("2", pos=0.5)

# Bottom face: bottom edge label "4"
seg_bot_bot = segment(bA, bB)
seg_bot_bot.label("4", pos=0.5)

# Bottom face: left edge label "2"
seg_bot_left = segment(bA, bD)
seg_bot_left.label("2", pos=0.5)

# Back face: bottom edge label "4"
seg_back_bot = segment(baA, baB)
seg_back_bot.label("4", pos=0.5)

# Back face: left edge label "3"
seg_back_left = segment(baA, baD)
seg_back_left.label("3", pos=0.5)

# Left face: bottom edge label "2"
seg_left_bot = segment(lA, lB)
seg_left_bot.label("2", pos=0.5)

# Left face: left edge label "3"
seg_left_left = segment(lA, lD)
seg_left_left.label("3", pos=0.5)

# Right face: bottom edge label "2"
seg_right_bot = segment(rA, rB)
seg_right_bot.label("2", pos=0.5)

# Right face: right edge label "3"
seg_right_right = segment(rB, rC)
seg_right_right.label("3", pos=0.5)

# --- Title ---
label_text("Net of Rectangular Prism  (4 × 2 × 3)", at=(front_x0 + L/2, top_y0 + W + 1.6))
