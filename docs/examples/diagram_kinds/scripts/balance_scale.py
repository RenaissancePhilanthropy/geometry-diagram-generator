# Balance scale illustrating 2x + 3 = 7
# Layout: fulcrum at center bottom, beam horizontal, pans hanging from each end

canvas(x_range=(-8, 8), y_range=(-4, 10))

# ── Fulcrum (triangle) ──────────────────────────────────────────────────────
f_base_y = 0.0
f_top_y  = 2.2
f_left  = point(-1.2, f_base_y)
f_right = point( 1.2, f_base_y)
f_top   = point( 0.0, f_top_y)
fulcrum = triangle(f_left, f_right, f_top)
fill(fulcrum, color="dimgray")
draw(fulcrum, color="dimgray")

# base line under fulcrum
base_l = point(-2.0, f_base_y)
base_r = point( 2.0, f_base_y)
draw(segment(base_l, base_r), color="dimgray", thick=True)

# ── Beam ────────────────────────────────────────────────────────────────────
beam_y   = f_top_y + 0.15          # beam sits on top of fulcrum
beam_l   = point(-6.5, beam_y)
beam_r   = point( 6.5, beam_y)
beam_top = point(-6.5, beam_y + 0.22)
beam_tr  = point( 6.5, beam_y + 0.22)

beam_rect = polygon(beam_l, beam_r, beam_tr, beam_top)
fill(beam_rect, color="saddlebrown")
draw(beam_rect, color="saddlebrown")

# ── Strings (vertical rods from beam ends down to pans) ─────────────────────
string_len = 2.2
pan_top_y  = beam_y - string_len    # top edge (rim) of each pan

# left string
ls_top = point(-6.5, beam_y)
ls_bot = point(-6.5, pan_top_y)
draw(segment(ls_top, ls_bot), color="dimgray", width=1.5)

# right string
rs_top = point( 6.5, beam_y)
rs_bot = point( 6.5, pan_top_y)
draw(segment(rs_top, rs_bot), color="dimgray", width=1.5)

# ── Pans ────────────────────────────────────────────────────────────────────
pan_w      = 3.0    # half-width of each pan
pan_thick  = 0.18   # thickness of pan platform
# Pan = a flat rectangular platform + two short side walls

# LEFT pan  ──────────────────────────────────────────────────────────────────
lp_cx = -6.5
lp_left  = point(lp_cx - pan_w, pan_top_y)
lp_right = point(lp_cx + pan_w, pan_top_y)
lp_rb    = point(lp_cx + pan_w, pan_top_y - pan_thick)
lp_lb    = point(lp_cx - pan_w, pan_top_y - pan_thick)

left_pan = polygon(lp_left, lp_right, lp_rb, lp_lb)
fill(left_pan, color="peru")
draw(left_pan, color="sienna", thick=True)

# RIGHT pan ──────────────────────────────────────────────────────────────────
rp_cx = 6.5
rp_left  = point(rp_cx - pan_w, pan_top_y)
rp_right = point(rp_cx + pan_w, pan_top_y)
rp_rb    = point(rp_cx + pan_w, pan_top_y - pan_thick)
rp_lb    = point(rp_cx - pan_w, pan_top_y - pan_thick)

right_pan = polygon(rp_left, rp_right, rp_rb, rp_lb)
fill(right_pan, color="peru")
draw(right_pan, color="sienna", thick=True)

# ── LEFT PAN contents: 2x + 3  ──────────────────────────────────────────────
# Platform top edge is at pan_top_y.  All contents go ABOVE (higher y).
# We draw two "x" blocks and three unit squares, stacked upward.

block_h   = 0.9   # height of each block
block_gap = 0.12  # small gap between blocks

# row 1 bottom edge sits exactly on the platform top
row1_bot = pan_top_y          # platform surface — items rest here
row1_top = row1_bot + block_h

# ── two x-blocks side by side (left pan, row 1) ─────────────────────────────
xb_w = 1.0   # width of each x-block
# centre them: two blocks + small gap in middle
x1_left  = point(lp_cx - xb_w - 0.08, row1_bot)
x1_right = point(lp_cx - 0.08,         row1_bot)
x1_tr    = point(lp_cx - 0.08,         row1_top)
x1_tl    = point(lp_cx - xb_w - 0.08, row1_top)
xblock1  = polygon(x1_left, x1_right, x1_tr, x1_tl)
fill(xblock1, color="steelblue", opacity=0.85)
draw(xblock1, color="navy")

x2_left  = point(lp_cx + 0.08,         row1_bot)
x2_right = point(lp_cx + xb_w + 0.08,  row1_bot)
x2_tr    = point(lp_cx + xb_w + 0.08,  row1_top)
x2_tl    = point(lp_cx + 0.08,         row1_top)
xblock2  = polygon(x2_left, x2_right, x2_tr, x2_tl)
fill(xblock2, color="steelblue", opacity=0.85)
draw(xblock2, color="navy")

# labels inside x-blocks
label_text("x", at=(lp_cx - xb_w/2 - 0.08, row1_bot + block_h/2))
label_text("x", at=(lp_cx + xb_w/2 + 0.08, row1_bot + block_h/2))

# ── three unit squares stacked above the x-blocks ───────────────────────────
unit_w = 0.75
row2_bot = row1_top + block_gap
row2_top = row2_bot + unit_w   # unit squares are square: h = w

u_spacing = unit_w + 0.12
u_start_x = lp_cx - u_spacing  # centre the three squares

for i in range(3):
    ux_l = u_start_x + i * (unit_w + 0.15)
    u_bl = point(ux_l,            row2_bot)
    u_br = point(ux_l + unit_w,   row2_bot)
    u_tr = point(ux_l + unit_w,   row2_top)
    u_tl = point(ux_l,            row2_top)
    usq  = polygon(u_bl, u_br, u_tr, u_tl)
    fill(usq, color="tomato", opacity=0.85)
    draw(usq, color="darkred")
    label_text("1", at=(ux_l + unit_w/2, row2_bot + unit_w/2))

# ── RIGHT PAN contents: 7  ──────────────────────────────────────────────────
# Seven unit squares arranged as a 4+3 two-row stack, all above the platform.

rrow1_bot = pan_top_y
rrow1_top = rrow1_bot + unit_w

n_row1 = 4
total_w_r1 = n_row1 * unit_w + (n_row1 - 1) * 0.15
rx_start = rp_cx - total_w_r1 / 2

for i in range(4):
    ux_l = rx_start + i * (unit_w + 0.15)
    u_bl = point(ux_l,            rrow1_bot)
    u_br = point(ux_l + unit_w,   rrow1_bot)
    u_tr = point(ux_l + unit_w,   rrow1_top)
    u_tl = point(ux_l,            rrow1_top)
    usq  = polygon(u_bl, u_br, u_tr, u_tl)
    fill(usq, color="gold", opacity=0.90)
    draw(usq, color="darkorange")
    label_text("1", at=(ux_l + unit_w/2, rrow1_bot + unit_w/2))

rrow2_bot = rrow1_top + block_gap
rrow2_top = rrow2_bot + unit_w

n_row2 = 3
total_w_r2 = n_row2 * unit_w + (n_row2 - 1) * 0.15
rx2_start = rp_cx - total_w_r2 / 2

for i in range(3):
    ux_l = rx2_start + i * (unit_w + 0.15)
    u_bl = point(ux_l,            rrow2_bot)
    u_br = point(ux_l + unit_w,   rrow2_bot)
    u_tr = point(ux_l + unit_w,   rrow2_top)
    u_tl = point(ux_l,            rrow2_top)
    usq  = polygon(u_bl, u_br, u_tr, u_tl)
    fill(usq, color="gold", opacity=0.90)
    draw(usq, color="darkorange")
    label_text("1", at=(ux_l + unit_w/2, rrow2_bot + unit_w/2))

# ── Equation labels below pans ───────────────────────────────────────────────
label_text("2x + 3", at=(lp_cx, pan_top_y - pan_thick - 0.55))
label_text("7",      at=(rp_cx, pan_top_y - pan_thick - 0.55))
label_text("=",      at=(0.0,   pan_top_y - pan_thick - 0.55))

# ── Title ────────────────────────────────────────────────────────────────────
label_text("2x + 3 = 7", at=(0.0, 8.5))
