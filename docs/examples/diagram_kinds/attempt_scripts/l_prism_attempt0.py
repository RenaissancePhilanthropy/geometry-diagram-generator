# L-shaped solid: 6 long x 4 wide x 3 tall, with a 2x2x3 notch cut from one corner
# We'll draw this in isometric-like perspective (oblique projection)
# The L-shape lies in the XY plane, extruded in Z

# Oblique projection parameters
# x-axis goes right, y-axis goes up-right at angle, z-axis goes up
import math

canvas(x_range=(-1, 12), y_range=(-1, 9))

# Oblique projection: world (x, y, z) -> screen (sx, sy)
# x goes right, z goes up, y goes diagonally (up-right at 30 deg)
ax = 1.0     # x scale
ay = 0.0     # x contribution to sy
bx = 0.4     # y contribution to sx (oblique angle)
by = 0.3     # y contribution to sy
cx = 0.0     # z contribution to sx
cy = 0.8     # z contribution to sy

def proj(x, y, z):
    sx = ax * x + bx * y + cx * z
    sy = ay * x + by * y + cy * z
    return point(sx, sy)

# L-shape vertices (looking from top, z=0 bottom, z=3 top)
# Full block would be 6x4, notch cuts 2x2 from one corner (say top-right corner in XY)
# L-shape corners (XY, bottom face z=0):
# A=(0,0), B=(6,0), C=(6,2), D=(4,2), E=(4,4), F=(0,4)
# Going counter-clockwise

# Bottom face (z=0)
A0 = proj(0, 0, 0)
B0 = proj(6, 0, 0)
C0 = proj(6, 2, 0)
D0 = proj(4, 2, 0)
E0 = proj(4, 4, 0)
F0 = proj(0, 4, 0)

# Top face (z=3)
A3 = proj(0, 0, 3)
B3 = proj(6, 0, 3)
C3 = proj(6, 2, 3)
D3 = proj(4, 2, 3)
E3 = proj(4, 4, 3)
F3 = proj(0, 4, 3)

# Draw visible faces of the L-shaped solid
# Front face (y=0): A0-B0-B3-A3
front = polygon(A0, B0, B3, A3)
fill(front, color="lightsteelblue", opacity=0.7)
draw(front, color="black", thick=True)

# Right face (x=6, y=0 to 2): B0-C0-C3-B3
right1 = polygon(B0, C0, C3, B3)
fill(right1, color="lightblue", opacity=0.7)
draw(right1, color="black", thick=True)

# Notch front face (x=4 to 6, y=2): C0-D0-D3-C3
notch_front = polygon(C0, D0, D3, C3)
fill(notch_front, color="lightblue", opacity=0.7)
draw(notch_front, color="black", thick=True)

# Left side of notch (x=4, y=2 to 4): D0-E0-E3-D3
notch_side = polygon(D0, E0, E3, D3)
fill(notch_side, color="lightblue", opacity=0.6)
draw(notch_side, color="black", thick=True)

# Left face (x=0): A0-F0-F3-A3
left_face = polygon(A0, F0, F3, A3)
fill(left_face, color="steelblue", opacity=0.5)
draw(left_face, color="black", thick=True)

# Top face (z=3): L-shaped polygon
top_face = polygon(A3, B3, C3, D3, E3, F3)
fill(top_face, color="lightcyan", opacity=0.9)
draw(top_face, color="black", thick=True)

# Back face (y=4, x=0 to 4): F0-E0-E3-F3
back_face = polygon(F0, E0, E3, F3)
fill(back_face, color="slategray", opacity=0.4)
draw(back_face, color="black", thick=True)

# Draw hidden edges as dashed lines
# Bottom face interior edges
draw(segment(A0, B0), dashed=True, color="gray")
draw(segment(B0, C0), dashed=True, color="gray")
draw(segment(C0, D0), dashed=True, color="gray")
draw(segment(D0, E0), dashed=True, color="gray")
draw(segment(E0, F0), dashed=True, color="gray")
draw(segment(F0, A0), dashed=True, color="gray")

# Mark visible solid edges (already drawn via polygons, but reinforce key ones)
# Vertical edges visible
draw(segment(A0, A3), color="black", thick=True)
draw(segment(B0, B3), color="black", thick=True)
draw(segment(C0, C3), color="black", thick=True)
draw(segment(D0, D3), color="black", thick=True)
draw(segment(E0, E3), color="black", thick=True)
draw(segment(F0, F3), color="black", thick=True)

# Label key points for reference
A3.label("", pos="above left")

# Now add braces for the 5 labeled dimensions
# 1. Overall length = 6: brace along front bottom edge A0 to B0
# A0 is proj(0,0,0), B0 is proj(6,0,0)
draw_brace((A0.x, A0.y), (B0.x, B0.y), direction="down", label="6")

# 2. Overall width = 4: brace along left face bottom edge A0 to F0
# A0=proj(0,0,0), F0=proj(0,4,0)
draw_brace((A0.x, A0.y), (F0.x, F0.y), direction="left", label="4")

# 3. Overall height = 3: brace along left vertical edge A0 to A3
# A0=proj(0,0,0), A3=proj(0,0,3)
draw_brace((A0.x, A0.y), (A3.x, A3.y), direction="left", label="3")

# 4. Notch width = 2: brace along the notch inner face bottom edge C0 to D0
# C0=proj(6,2,0), D0=proj(4,2,0)
# This is the edge from x=6 to x=4 at y=2 z=0
draw_brace((D0.x, D0.y), (C0.x, C0.y), direction="down", label="2")

# 5. Notch depth = 2: brace along the notch left face bottom D0 to E0
# D0=proj(4,2,0), E0=proj(4,4,0)
# This is the edge from y=2 to y=4 at x=4 z=0
draw_brace((D0.x, D0.y), (E0.x, E0.y), direction="right", label="2")
