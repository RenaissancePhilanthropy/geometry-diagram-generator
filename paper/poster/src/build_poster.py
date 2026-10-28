"""Generate the two MATH-AI 2026 posters as draw.io XML from a spec.

Portrait, 61 cm x 85 cm (the workshop's required size). draw.io pages are
100 px per inch, so the page is 2402 x 3346 px. Two columns.

Usage: python3 -I build_poster.py <gg|kbs> <out.drawio>
Images are read from img_gg/, img_kbs/ and rp_logo.png next to this script.
"""
import sys, os, base64
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- design tokens --------------------------------------------------------
ORANGE, INK, GRAY, CREAM, LINE, TINT = "#F87248", "#131318", "#737382", "#F4F2EE", "#B8B8C0", "#FFF1EB"
GREEN, RED = "#2F9E6E", "#D04A3A"
FONT = "Helvetica"
W, H = 2402, 3346           # 24.02 in x 33.46 in = 61 cm x 85 cm at 100 px/in
M = 50                      # print margin
GAP = 50
COL_W = (W - 2 * M - GAP) // 2          # 1126
COL_X = (M, M + COL_W + GAP)            # 50, 1226
HEADER_BOTTOM = 370
BAND_Y, BAND_H = 400, 120
BODY_Y = 560
BOTTOM = H - M

# type scale (px at 100 px/in; 32 px = 23 pt)
T_BODY, T_SMALL, T_SEC, T_STAT, T_STATLBL = 32, 27, 46, 64, 27

cells = []
_n = [1]


def _id():
    _n[0] += 1
    return f"c{_n[0]}"


def cell(style, x, y, w, h, value=""):
    i = _id()
    cells.append(
        f'<mxCell id="{i}" value={quoteattr(value)} style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return i


def edge(src, dst, orth=False, exit=(0.5, 1), entry=(0.5, 0), sw=4):
    i = _id()
    st = f"endArrow=block;endFill=1;strokeWidth={sw};strokeColor={INK};html=1;"
    st += f"exitX={exit[0]};exitY={exit[1]};entryX={entry[0]};entryY={entry[1]};"
    if orth:
        st += "edgeStyle=orthogonalEdgeStyle;"
    cells.append(f'<mxCell id="{i}" style="{st}" edge="1" parent="1" source="{src}" target="{dst}">'
                 f'<mxGeometry relative="1" as="geometry"/></mxCell>')


def text(x, y, w, h, value, size=T_BODY, color=INK, align="left", valign="top", bold=False, italic=False):
    fs = (1 if bold else 0) | (2 if italic else 0)
    st = (f"text;html=1;whiteSpace=wrap;align={align};verticalAlign={valign};fontSize={size};"
          f"fontFamily={FONT};fontColor={color};fontStyle={fs};spacing=0;spacingLeft=0;spacingRight=0;")
    return cell(st, x, y, w, h, value)


def box(x, y, w, h, value="", fill="#FFFFFF", stroke=LINE, sw=2, size=T_BODY, color=INK, bold=False,
        rounded=True, arc=6, align="center", valign="middle", spacing=10):
    st = (f"rounded={1 if rounded else 0};arcSize={arc};whiteSpace=wrap;html=1;fillColor={fill};"
          f"strokeColor={stroke};strokeWidth={sw};fontSize={size};fontFamily={FONT};fontColor={color};"
          f"fontStyle={1 if bold else 0};align={align};verticalAlign={valign};spacing={spacing};")
    return cell(st, x, y, w, h, value)


def png_size(path):
    from struct import unpack
    return unpack(">II", open(path, "rb").read()[16:24])


def image(path, x, y, w=None, h=None):
    iw, ih = png_size(path)
    if w is None:
        w = h * iw / ih
    if h is None:
        h = w * ih / iw
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    st = f"shape=image;imageAspect=0;aspect=fixed;verticalLabelPosition=bottom;verticalAlign=top;image=data:image/png,{b64};"
    return cell(st, x, y, round(w), round(h)), round(w), round(h)


def fit(path, w=None, h=None):
    """Size an image would take, without placing it."""
    iw, ih = png_size(path)
    if w is None:
        w = h * iw / ih
    if h is None:
        h = w * ih / iw
    return round(w), round(h)


def section(col, y, n, title):
    """Numbered section header. Returns y where content starts."""
    x = COL_X[col]
    cell(f"ellipse;whiteSpace=wrap;html=1;fillColor={ORANGE};strokeColor=none;fontColor=#FFFFFF;"
         f"fontSize=36;fontStyle=1;fontFamily={FONT};align=center;verticalAlign=middle;", x, y, 64, 64, str(n))
    text(x + 84, y - 6, COL_W - 84, 76, title, size=T_SEC, color=ORANGE, valign="middle", bold=True)
    cell(f"line;strokeWidth=4;strokeColor={ORANGE};html=1;", x, y + 80, COL_W, 6)
    return y + 108


def stat(x, y, w, h, number, label, num_size=T_STAT, label_size=T_STATLBL, fill=CREAM):
    v = (f'<span style="font-size:{num_size}px;font-weight:bold;color:{ORANGE}">{number}</span><br>'
         f'<span style="font-size:{label_size}px;color:{INK}">{label}</span>')
    return box(x, y, w, h, v, fill=fill, stroke="none", sw=0, size=label_size, spacing=14)


def finding(x, y, w, h, number, body, num_w=300, num_size=52, size=T_SMALL + 2):
    """Cream tile: big number left, one bold claim + short body right."""
    box(x, y, w, h, "", fill=CREAM, stroke="none", sw=0)
    text(x + 20, y, num_w, h, f'<b>{number}</b>', size=num_size, color=ORANGE, valign="middle", align="center")
    text(x + num_w + 40, y + 16, w - num_w - 70, h - 32, body, size=size, valign="middle")


def pill(x, y, w, h, label, fill, size=30):
    return box(x, y, w, h, label, fill=fill, stroke="none", sw=0, size=size, color="#FFFFFF", bold=True, arc=50)


def qr_row(x, y, blurb, size=200):
    """Unnumbered code block: QR placeholder left, one line right."""
    box(x, y, size, size, "QR code<br><span style='font-size:22px;color:#737382'>to add</span>",
        fill="#FFFFFF", stroke=LINE, sw=2, size=26, bold=True)
    text(x + size + 30, y, COL_W - size - 30, size, blurb, size=T_BODY, valign="middle")
    return y + size


def header(title, authors, affil, title_size=62):
    cell("rounded=0;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=none;", 0, 0, W, H)   # page background
    cell(f"rounded=0;whiteSpace=wrap;html=1;fillColor={CREAM};strokeColor=none;", M, M, W - 2 * M, HEADER_BOTTOM - M)
    # institution badge with white-on-dark wordmark
    bw, bh, by = 380, 200, 110
    box(80, by, bw, bh, "", fill=INK, stroke="none", sw=0, arc=8)
    lw = 340
    image(os.path.join(HERE, "rp_logo.png"), 100, by + (bh - 46) / 2, w=lw)
    text(190, by, 260, bh, "Renaissance<br>Philanthropy", size=30, color="#FFFFFF", valign="middle", bold=True)
    box(W - 80 - bw, by, bw, bh, "MATH-AI 2026<br>at NeurIPS<br><span style='font-size:20px;color:#737382'>logo to add</span>",
        fill="#FFFFFF", stroke=LINE, sw=2, size=26, bold=True)
    tx, tw = 80 + bw + 30, W - 2 * (80 + bw + 30)
    text(tx, 60, tw, 190, title, size=title_size, align="center", valign="middle", bold=True)
    text(tx, 250, tw, 60, authors, size=36, align="center", valign="middle")
    text(tx, 305, tw, 50, affil, size=26, color=GRAY, align="center", valign="middle")


def band(value, size=38):
    box(M, BAND_Y, W - 2 * M, BAND_H, value, fill=ORANGE, stroke="none", sw=0, size=size,
        color="#FFFFFF", bold=True, rounded=False, spacing=16)


def takeaway(col, value, h=210):
    box(COL_X[col], BOTTOM - h, COL_W, h, f"<b>{value}</b>", fill=TINT, stroke=ORANGE, sw=5, size=32)
    return BOTTOM - h


def write(path, name):
    body = "\n".join(cells)
    xml = (f'<mxfile host="Electron" modified="2026-10-25T00:00:00.000Z" agent="poster-gen" version="24.7.17" type="device">'
           f'<diagram name="{name}" id="poster">'
           f'<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
           f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0" background="#FFFFFF">'
           f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram></mxfile>')
    open(path, "w").write(xml)
    print("wrote", path, len(cells), "cells")


# ===========================================================================
def geogenbench():
    img = lambda n: os.path.join(HERE, "img_gg", n)
    header("GeoGenBench: Symbolically Verified<br>Generation of Geometry Diagrams",
           "Mei Chen · Gordon Stein", "Renaissance Philanthropy")
    band("A geometry drawing can be graded exactly from its coordinates, with no judge.<br>"
         "Graded this way, the scaffold matters more than the model.")
    half = (COL_W - 46) // 2        # 540
    g2 = COL_W - 2 * half           # 46

    # ---------------- column 1 ----------------
    x = COL_X[0]
    y = section(0, BODY_Y, 1, "The problem")
    text(x, y, COL_W, 90,
         "Every geometry benchmark asks a model to read a diagram. None asks it to draw one, "
         "because grading a drawing has been the hard part.")
    y += 100
    text(x, y, COL_W, 80,
         "Both drawings below answer: <i>“Draw an acute triangle ABC with 60° at B and 70° at C. "
         "Drop the altitude from A to BC, meeting it at H.”</i>", size=T_SMALL, color=GRAY)
    y += 90
    pill(x + (half - 200) / 2, y, 200, 64, "PASS", GREEN)
    pill(x + half + g2 + (half - 200) / 2, y, 200, 64, "FAIL", RED)
    y += 84
    FH = 400
    box(x, y, half, FH, "", fill="#FFFFFF", stroke=GREEN, sw=4, arc=4)
    box(x + half + g2, y, half, FH, "", fill="#FFFFFF", stroke=RED, sw=4, arc=4)
    w1, h1 = fit(img("c10.png"), h=FH - 40)
    image(img("c10.png"), x + (half - w1) / 2, y + 20, h=FH - 40)
    w2, h2 = fit(img("c11.png"), w=half - 50)
    image(img("c11.png"), x + half + g2 + 25, y + (FH - h2) / 2, w=half - 50)
    y += FH + 14
    text(x, y, half, 110, "60° at B, 70° at C, altitude from A, foot H on BC. Every check holds.", size=T_SMALL, color=GRAY)
    text(x + half + g2, y, half, 110, "Obtuse at B, so H lands outside BC. The right angle is still there. "
         "A person glancing at it would likely pass it.", size=T_SMALL, color=GRAY)
    y += 120
    text(x, y, COL_W, 56, "Looking right is not the same as being right.", size=36, color=ORANGE, bold=True, align="center")
    y += 90

    y = section(0, y, 2, "What is new")
    th, g = 180, 36
    stat(x, y, half, th, "801", "prompts, each paired with the checks a correct drawing must pass")
    stat(x + half + g2, y, half, th, "15", "checks, each a few lines of arithmetic. No human, no vision judge")
    y += th + g
    stat(x, y, half, th, "6", "frontier models. A typed scaffold lifts every one, by 2 to 25 points")
    stat(x + half + g2, y, half, th, "0", "correct drawings failed by the grader in a 200-output human audit")
    y += th + 50

    y = section(0, y, 3, "How a drawing is graded")
    text(x, y, COL_W, 100,
         "<b>One template writes both.</b> A Python function emits the sentence the model sees and the "
         "checks the grader runs, from the same variables, so the two cannot disagree.")
    y += 130
    t = box(x + (COL_W - 720) / 2, y, 720, 84, "altitude_template(A, B, C, H, 60°, 70°)", fill=CREAM, stroke=LINE, sw=2, size=30)
    y += 134
    p = box(x, y, half, 220,
            "<b>Prompt</b>, shown to the model<br><span style='font-size:26px'>“Draw an acute triangle ABC with 60° at B "
            "and 70° at C. Drop the altitude from A to BC, meeting it at H.”</span>", fill="#FFFFFF", stroke=INK, sw=3, size=28)
    c = box(x + half + g2, y, half, 220,
            "<b>Checks</b>, never shown<br><span style='font-family:monospace;font-size:26px'>right_angle(A, H, B)<br>"
            "point_on_segment(H, B, C)<br>mark_present(right_angle, H)</span>", fill=TINT, stroke=ORANGE, sw=4, size=28)
    edge(t, p, orth=True)
    edge(t, c, orth=True)
    y += 250
    text(x, y, COL_W, 70, "<b>From drawing to verdict.</b> The model writes TikZ. We parse the coordinates "
         "back out of it and run the checks on them.")
    y += 86
    bw, bg = 262, 26
    s1 = box(x, y, bw, 110, "model writes<br><b>TikZ</b>", fill=CREAM, stroke=LINE, sw=2, size=28)
    s2 = box(x + bw + bg, y, bw, 110, "parse<br><b>coordinates</b>", fill=CREAM, stroke=LINE, sw=2, size=28)
    s3 = box(x + 2 * (bw + bg), y, bw, 110, "run the<br><b>checks</b>", fill=TINT, stroke=ORANGE, sw=4, size=28)
    s4 = box(x + 3 * (bw + bg), y, bw, 110, "<b>pass</b> · soft pass<br>· fail", fill=CREAM, stroke=LINE, sw=2, size=28)
    for a, b in ((s1, s2), (s2, s3), (s3, s4)):
        edge(a, b, exit=(1, 0.5), entry=(0, 0.5))
    y += 140
    text(x, y, COL_W, 100, "Fifteen checks such as right angle, midpoint, parallel, and point on segment, each "
         "arithmetic with a small tolerance. <b>A right angle is a dot product, not an opinion.</b>", size=30)
    y += 116
    text(x, y, COL_W, 44, "<b>600 prompts</b> from 30 templates, 200 per tier, plus <b>201</b> from a K–12 curriculum.", size=30)
    y += 60
    tw3 = (COL_W - 2 * 26) // 3
    box(x, y, tw3, 96, "<b>T1</b><br>a single shape", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    box(x + tw3 + 26, y, tw3, 96, "<b>T2</b><br>adds one construction", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    box(x + 2 * (tw3 + 26), y, tw3, 96, "<b>T3</b><br>combines several", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    y += 96
    print("gg col1 ends at", y, "of", BOTTOM)

    # ---------------- column 2 ----------------
    x = COL_X[1]
    y = section(1, BODY_Y, 4, "What we found")
    _, iw, ih = image(img("c44.png"), x + (COL_W - 1060) / 2, y, w=1060)
    y += ih + 6
    text(x, y, COL_W, 70, "Strict pass rate on 600 templated prompts, 3 repeats. Dashed box: three models "
         "within one point of each other at a 7× cost spread.", size=T_SMALL, color=GRAY)
    y += 86
    fh, fg = 156, 20
    finding(x, y, COL_W, fh, "+2 to +25", "<b>The scaffold lifts every model.</b> The weaker a model is at raw TikZ, the more it gains.")
    y += fh + fg
    finding(x, y, COL_W, fh, "1 point", "<b>The frontier converges.</b> GPT-5.5, Sonnet, and Opus finish within one point. Opus costs seven times more.")
    y += fh + fg
    finding(x, y, COL_W, fh, "92 → 36%", "<b>Without the scaffold</b> the same six models spread across 56 points.")
    y += fh + 30
    text(x, y, COL_W, 100, "<b>Wrong drawings, not broken code.</b> Most failures are clean, rendered diagrams with the "
         "wrong geometry. The grader catches them. A person glancing at the picture often would not.")
    y += 130
    text(x, y, COL_W, 100, "<b>Limits.</b> The top models are near the ceiling on T1 and T2. On the curriculum prompts "
         "every score we ran roughly halved. The scaffold bundles format, compile path, and retries; we have not separated them.",
         size=T_SMALL, color=GRAY)
    y += 120

    y = section(1, y, 5, "Can the grader be trusted")
    _, iw, ih = image(img("c41.png"), x, y, w=640)
    stat(x + 670, y, COL_W - 670, ih, "18%", "of the grader's <b>passes</b> overturned by two blind raters<br><br>"
         f"<span style='font-size:{T_STAT}px;font-weight:bold;color:{ORANGE}'>0%</span><br>of its <b>fails</b>")
    y += ih + 10
    text(x, y, COL_W, 70, "The disagreement sits in one tier, T2, where the templates check the construction "
         "but not the angles the prompt gave.", size=T_SMALL, color=GRAY)
    y += 80

    top = takeaway(1, "Each requirement on a drawing can be checked exactly, from its coordinates.<br>"
                      "Graded this way, the scaffold matters more than the model.")
    qr_y = top - 40 - 200
    print("gg col2 text ends at", y, "; qr row at", qr_y)
    qr_row(x, qr_y, "Prompts, templates, grader, and leaderboard.<br><span style='color:#737382'>Release link to be added.</span>")


# ===========================================================================
def kbs():
    img = lambda n: os.path.join(HERE, "img_kbs", n)
    header("Knowing Before Saying:<br>Internal Correctness Signals in Mathematical Reasoning",
           "Mei Chen¹ · Gordon Stein¹ · Andreas Ziegler²",
           "¹Renaissance Philanthropy   ²Institute for Aerospace Studies, University of Toronto", title_size=48)
    band("Open models carry a signal about their own errors that their stated confidence does not.<br>"
         "A linear probe on the hidden state reads it.")
    half = (COL_W - 46) // 2
    g2 = COL_W - 2 * half

    # ---------------- column 1 ----------------
    x = COL_X[0]
    y = section(0, BODY_Y, 1, "The problem")
    text(x, y, COL_W, 90, "A confidently wrong answer is a problem. On MATH a wrong derivation looks exactly like "
         "a right one, so nothing on the page gives it away.")
    y += 104
    ex = ("<b>One real attempt. Mistral on MATH.</b><br><br>"
          "<i>What integer n satisfies 0 ≤ n &lt; 18 and n ≡ −11213141 (mod 18)?</i><br><br>"
          "<span style='color:#737382'>Before answering:</span> &nbsp;<b>Confidence 90</b><br><br>"
          "r = −11213141 − 18 × (−622953)<br>r = −11213141 + 11213154<br>"
          f"r = <span style='color:{RED};font-weight:bold'>3</span> &nbsp;&nbsp;<span style='color:#737382'>(it is 13)</span><br>"
          "So n = 3.<br><br>"
          "<span style='color:#737382'>After answering:</span> &nbsp;<b>Confidence 95</b>")
    box(x, y, COL_W, 580, ex, fill="#FFFFFF", stroke=INK, sw=4, size=30, align="left", valign="top", spacing=30)
    y += 610
    pill(x, y, half, 120, "Model says<br><span style='font-size:44px'>95 / 100</span>", GRAY, size=27)
    pill(x + half + g2, y, half, 120, "Probe on the hidden state<br><span style='font-size:44px'>likely wrong</span>", ORANGE, size=27)
    y += 136
    text(x, y, COL_W, 70, "Every step is right until the last subtraction. The slip leaves no mark. Confidence went up.",
         size=T_SMALL, color=GRAY)
    y += 90

    y = section(0, y, 2, "What is new")
    th, g = 180, 36
    stat(x, y, half, th, "12 / 16", "model–task cells where the probe beats stated confidence. One tie.")
    stat(x + half + g2, y, half, th, "+0.20", "AUROC gap on MATH, the largest of the four tasks. Mean gap 0.10.")
    y += th + g
    stat(x, y, half, th, "0.84 → 0.56", "stated confidence on Mistral once the probed direction is erased", num_size=56)
    stat(x + half + g2, y, half, th, "4", "open models: Gemma-4, Qwen3.6, GLM-4.7, Mistral")
    y += th + 50

    y = section(0, y, 3, "How we read the state")
    text(x, y, COL_W, 70, "Three turns. We record the hidden state at the token where the model is about to write "
         "its confidence digit.")
    y += 86
    t1 = box(x, y, COL_W, 104, "<b>Turn 1</b> &nbsp;“How confident are you that you will get this right? 0–100.”<br>Model writes a number.", fill=CREAM, stroke=LINE, sw=2, size=28)
    y += 148
    t2 = box(x, y, COL_W, 96, "<b>Turn 2</b> &nbsp;The model answers the question.", fill=CREAM, stroke=LINE, sw=2, size=28)
    y += 140
    t3 = box(x, y, COL_W, 110, "<b>Turn 3</b> &nbsp;“How confident are you that the answer you just gave is correct?”<br>"
             f"<span style='color:{ORANGE};font-weight:bold'>▲ read site: the hidden state as it writes the digit</span>", fill=TINT, stroke=ORANGE, sw=4, size=28)
    edge(t1, t2)
    edge(t2, t3)
    y += 140
    text(x, y, COL_W, 90, "<b>The probe.</b> Standardize, 50 principal components, logistic regression. Five folds grouped "
         "by question, so the probe is scored only on questions it never saw.", size=30)
    y += 104
    text(x, y, COL_W, 110, "<b>The intervention.</b> At that same token, after the answer is written, scale the state along "
         "the correctness direction by a gain g. A random direction of the same norm is the control.", size=30)
    y += 134
    bw, bg = 262, 26
    box(x, y, bw, 100, "<b>g = 0</b><br>erased", fill=TINT, stroke=ORANGE, sw=4, size=28)
    box(x + bw + bg, y, bw, 100, "<b>g = 1</b><br>untouched", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    box(x + 2 * (bw + bg), y, bw, 100, "<b>g = 2</b><br>doubled", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    box(x + 3 * (bw + bg), y, bw, 100, "<b>g = 4</b><br>quadrupled", fill="#FFFFFF", stroke=LINE, sw=2, size=28)
    y += 100
    print("kbs col1 ends at", y, "of", BOTTOM)

    # ---------------- column 2 ----------------
    x = COL_X[1]
    y = section(1, BODY_Y, 4, "What we found")
    _, iw, ih = image(img("c34.png"), x, y, w=COL_W)
    y += ih + 16
    finding(x, y, COL_W, 170, "12 / 16", "<b>The state carries more than the report.</b> The probe beats stated confidence "
            "in 12 of 16 cells. Mean gap 0.10. On MATH, 0.20.")
    y += 196
    pw = 840
    _, iw, ih = image(img("c36.png"), x + (COL_W - pw) / 2, y, w=pw)
    y += ih + 16
    finding(x, y, COL_W, 200, "0.84<br>→ 0.56", "<b>On Mistral, the report uses the signal.</b> Erase the direction and "
            "stated confidence stops separating right from wrong. A random direction does nothing. "
            "The model becomes uniformly sure, not confused.", num_size=48)
    y += 220
    text(x, y, COL_W, 100, "<b>Not every model.</b> On GLM, erasing changes nothing. On Qwen3.6 the self-report is nearly "
         "flat to begin with, so there is nothing to erase. Gemma-4 leaves too few failures to test.", size=T_SMALL, color=GRAY)
    y += 120
    # depth figure beside its text
    fw = 600
    _, iw, ih = image(img("c31.png"), x, y, w=fw)
    text(x + fw + 30, y, COL_W - fw - 30, ih,
         "<b>Where in the network.</b> Fixed in advance at 70% of depth, for every model and every cell.<br><br>"
         "<span style='color:#737382;font-size:26px'>Probe AUROC by depth on MATH. Layer 0 is chance because its token is "
         "identical in every record. The signal is present from the first layers and flat across depth. "
         "The dot is the fixed layer.</span>", size=30, valign="middle")
    y += ih

    top = takeaway(1, "Four open models carry information about their own errors that their self-report does not.<br>"
                      "In Mistral, we have shown it is used when it self-reports.")
    qr_y = top - 40 - 200
    print("kbs col2 text ends at", y, "; qr row at", qr_y)
    qr_row(x, qr_y, "Code, prompts, and every per-cell number.<br><span style='color:#737382'>Repository link to be added.</span>")


if __name__ == "__main__":
    which, out = sys.argv[1], sys.argv[2]
    {"gg": geogenbench, "kbs": kbs}[which]()
    write(out, "poster")
