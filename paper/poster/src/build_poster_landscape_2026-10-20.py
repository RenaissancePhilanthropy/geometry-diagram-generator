"""Generate the two MATH-AI 2026 posters as draw.io XML from a spec.

Usage: python3 -I build_poster.py <gg|kbs> <out.drawio>
Images are read from img_gg/, img_kbs/ and rp_logo.png next to this script.
"""
import sys, os, base64, html
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- design tokens --------------------------------------------------------
ORANGE, INK, GRAY, CREAM, LINE, TINT = "#F87248", "#131318", "#737382", "#F4F2EE", "#B8B8C0", "#FFF1EB"
GREEN, RED = "#2F9E6E", "#D04A3A"
FONT = "Helvetica"
W, H = 4800, 3600
M = 50                       # print margin
COL_W, COL_X = 1520, (50, 1640, 3230)
HEADER_BOTTOM = 470
BAND_Y, BAND_H = 510, 170
BODY_Y = 740

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


def edge(src, dst, orth=False, exit=(0.5, 1), entry=(0.5, 0)):
    i = _id()
    st = f"endArrow=block;endFill=1;strokeWidth=6;strokeColor={INK};html=1;"
    st += f"exitX={exit[0]};exitY={exit[1]};entryX={entry[0]};entryY={entry[1]};"
    if orth:
        st += "edgeStyle=orthogonalEdgeStyle;"
    cells.append(f'<mxCell id="{i}" style="{st}" edge="1" parent="1" source="{src}" target="{dst}">'
                 f'<mxGeometry relative="1" as="geometry"/></mxCell>')


def text(x, y, w, h, value, size=40, color=INK, align="left", valign="top", bold=False, italic=False):
    fs = (1 if bold else 0) | (2 if italic else 0)
    st = (f"text;html=1;whiteSpace=wrap;align={align};verticalAlign={valign};fontSize={size};"
          f"fontFamily={FONT};fontColor={color};fontStyle={fs};spacing=0;spacingLeft=0;spacingRight=0;")
    return cell(st, x, y, w, h, value)


def box(x, y, w, h, value="", fill="#FFFFFF", stroke=LINE, sw=3, size=36, color=INK, bold=False,
        rounded=True, arc=6, align="center", valign="middle", spacing=14):
    st = (f"rounded={1 if rounded else 0};arcSize={arc};whiteSpace=wrap;html=1;fillColor={fill};"
          f"strokeColor={stroke};strokeWidth={sw};fontSize={size};fontFamily={FONT};fontColor={color};"
          f"fontStyle={1 if bold else 0};align={align};verticalAlign={valign};spacing={spacing};")
    return cell(st, x, y, w, h, value)


def image(path, x, y, w=None, h=None):
    from struct import unpack
    data = open(path, "rb").read()
    iw, ih = unpack(">II", data[16:24])          # PNG IHDR
    if w is None:
        w = h * iw / ih
    if h is None:
        h = w * ih / iw
    b64 = base64.b64encode(data).decode()
    st = f"shape=image;imageAspect=0;aspect=fixed;verticalLabelPosition=bottom;verticalAlign=top;image=data:image/png,{b64};"
    return cell(st, x, y, round(w), round(h)), round(w), round(h)


def section(col, y, n, title):
    """Numbered section header. Returns y where content starts."""
    x = COL_X[col]
    cell(f"ellipse;whiteSpace=wrap;html=1;fillColor={ORANGE};strokeColor=none;fontColor=#FFFFFF;"
         f"fontSize=50;fontStyle=1;fontFamily={FONT};align=center;verticalAlign=middle;", x, y, 90, 90, str(n))
    text(x + 115, y - 8, COL_W - 115, 106, title, size=64, color=ORANGE, valign="middle", bold=True)
    cell(f"line;strokeWidth=5;strokeColor={ORANGE};html=1;", x, y + 112, COL_W, 8)
    return y + 150


def stat(x, y, w, h, number, label, num_size=88, label_size=34, fill=CREAM):
    v = (f'<span style="font-size:{num_size}px;font-weight:bold;color:{ORANGE}">{number}</span><br>'
         f'<span style="font-size:{label_size}px;color:{INK}">{label}</span>')
    return box(x, y, w, h, v, fill=fill, stroke="none", sw=0, size=label_size, spacing=20)


def finding(x, y, w, h, number, body, num_w=430, num_size=72):
    """Cream tile: big number left, one bold claim + short body right."""
    box(x, y, w, h, "", fill=CREAM, stroke="none", sw=0)
    text(x + 30, y, num_w, h, f'<b>{number}</b>', size=num_size, color=ORANGE, valign="middle", align="center")
    text(x + num_w + 50, y + 25, w - num_w - 90, h - 50, body, size=38, valign="middle")


def pill(x, y, w, h, label, fill, size=44):
    return box(x, y, w, h, label, fill=fill, stroke="none", sw=0, size=size, color="#FFFFFF", bold=True, arc=50)


def header(title, authors, affil, title_size=92):
    cell(f"rounded=0;whiteSpace=wrap;html=1;fillColor={CREAM};strokeColor=none;", M, M, W - 2 * M, HEADER_BOTTOM - M)
    # institution badge with white-on-dark wordmark
    box(90, 110, 560, 300, "", fill=INK, stroke="none", sw=0, arc=8)
    image(os.path.join(HERE, "rp_logo.png"), 120, 110 + (300 - 67) / 2, w=500)
    text(250, 110, 380, 300, "Renaissance<br>Philanthropy", size=44, color="#FFFFFF", valign="middle", bold=True)
    box(4150, 110, 560, 300, "MATH-AI 2026<br>at NeurIPS<br><span style='font-size:28px;color:#737382'>logo to add</span>",
        fill="#FFFFFF", stroke=LINE, sw=3, size=36, bold=True)
    text(690, 70, 3420, 235, title, size=title_size, align="center", valign="middle", bold=True)
    text(690, 305, 3420, 80, authors, size=54, align="center", valign="middle")
    text(690, 385, 3420, 70, affil, size=38, color=GRAY, align="center", valign="middle")


def band(value, size=56):
    box(M, BAND_Y, W - 2 * M, BAND_H, value, fill=ORANGE, stroke="none", sw=0, size=size,
        color="#FFFFFF", bold=True, rounded=False, spacing=24)


def write(path, name):
    body = "\n".join(cells)
    xml = (f'<mxfile host="Electron" modified="2026-10-20T00:00:00.000Z" agent="poster-gen" version="24.7.17" type="device">'
           f'<diagram name="{name}" id="poster">'
           f'<mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
           f'page="1" pageScale="1" pageWidth="{W}" pageHeight="{H}" math="0" shadow="0" background="#FFFFFF">'
           f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram></mxfile>')
    open(path, "w").write(xml)
    print("wrote", path, len(cells), "cells")


# ===========================================================================
def geogenbench():
    img = lambda n: os.path.join(HERE, "img_gg", n)
    header("GeoGenBench: Symbolically Verified Generation of Geometry Diagrams",
           "Mei Chen · Gordon Stein", "Renaissance Philanthropy")
    band("A geometry drawing can be graded exactly from its coordinates, with no judge. "
         "Graded this way, the scaffold matters more than the model.")

    # ---------------- column 1 ----------------
    x = COL_X[0]
    y = section(0, BODY_Y, 1, "The problem")
    text(x, y, COL_W, 130,
         "Every geometry benchmark asks a model to read a diagram. None asks it to draw one, "
         "because grading a drawing has been the hard part.", size=42)
    y += 150
    text(x, y, COL_W, 110,
         "Both drawings below answer: <i>“Draw an acute triangle ABC with 60° at B and 70° at C. "
         "Drop the altitude from A to BC, meeting it at H.”</i>", size=36, color=GRAY)
    y += 140
    # badges
    pill(x + 240, y, 260, 90, "PASS", GREEN)
    pill(x + 780 + 240, y, 260, 90, "FAIL", RED)
    y += 120
    # the two drawings, boxed in a common frame height
    FH = 640
    box(x, y, 740, FH, "", fill="#FFFFFF", stroke=GREEN, sw=5, arc=4)
    box(x + 780, y, 740, FH, "", fill="#FFFFFF", stroke=RED, sw=5, arc=4)
    _, w1, h1 = image(img("c10.png"), 0, 0, h=FH - 60)
    cells.pop()
    image(img("c10.png"), x + (740 - w1) / 2, y + 30, h=FH - 60)
    _, w2, h2 = image(img("c11.png"), 0, 0, w=680)
    cells.pop()
    image(img("c11.png"), x + 780 + 30, y + (FH - h2) / 2, w=680)
    y += FH + 20
    text(x, y, 740, 150, "60° at B, 70° at C, altitude from A, foot H on BC. Every check holds.", size=34, color=GRAY)
    text(x + 780, y, 740, 150, "Obtuse at B, so H lands outside BC. The right angle is still there. "
         "A person glancing at it would likely pass it.", size=34, color=GRAY)
    y += 150
    text(x, y, COL_W, 80, "Looking right is not the same as being right.", size=48, color=ORANGE, bold=True, align="center")
    y += 130

    y = section(0, y, 2, "What is new")
    tw, th, g = 740, 250, 40
    stat(x, y, tw, th, "801", "prompts, each paired with the checks a correct drawing must pass")
    stat(x + tw + g, y, tw, th, "15", "checks, each a few lines of arithmetic. No human, no vision judge")
    y += th + g
    stat(x, y, tw, th, "6", "frontier models. A typed scaffold lifts every one, by 2 to 25 points")
    stat(x + tw + g, y, tw, th, "0", "correct drawings failed by the grader in a 200-output human audit")
    y += th + 40

    y = section(0, y, 3, "Code and data")
    box(x, y, 400, 400, "QR code<br><span style='font-size:28px;color:#737382'>to add</span>", fill="#FFFFFF", stroke=LINE, sw=3, size=34, bold=True)
    text(x + 440, y + 20, COL_W - 440, 360,
         "Prompts, templates, grader, and leaderboard.<br><br><span style='color:#737382'>Release link to be added.</span>", size=40)

    # ---------------- column 2 ----------------
    x = COL_X[1]
    y = section(1, BODY_Y, 4, "How a drawing is graded")
    text(x, y, COL_W, 150,
         "<b>One template writes both.</b> A Python function emits the sentence the model sees and the "
         "checks the grader runs, from the same variables, so the two cannot disagree.", size=40)
    y += 170
    t = box(x + 240, y, 1040, 120, "altitude_template(A, B, C, H, 60°, 70°)", fill=CREAM, stroke=LINE, sw=3, size=38)
    y += 190
    p = box(x, y, 740, 300,
            "<b>Prompt</b>, shown to the model<br><span style='font-size:32px'>“Draw an acute triangle ABC with 60° at B "
            "and 70° at C. Drop the altitude from A to BC, meeting it at H.”</span>", fill="#FFFFFF", stroke=INK, sw=4, size=36)
    c = box(x + 780, y, 740, 300,
            "<b>Checks</b>, never shown<br><span style='font-family:monospace;font-size:32px'>right_angle(A, H, B)<br>"
            "point_on_segment(H, B, C)<br>mark_present(right_angle, H)</span>", fill=TINT, stroke=ORANGE, sw=5, size=36)
    edge(t, p, orth=True)
    edge(t, c, orth=True)
    y += 370
    text(x, y, COL_W, 100, "<b>From drawing to verdict.</b> The model writes TikZ. We parse the coordinates "
         "back out of it and run the checks on them.", size=40)
    y += 130
    bw, bg = 357, 30
    s1 = box(x, y, bw, 150, "model writes<br><b>TikZ</b>", fill=CREAM, stroke=LINE, sw=3)
    s2 = box(x + bw + bg, y, bw, 150, "parse<br><b>coordinates</b>", fill=CREAM, stroke=LINE, sw=3)
    s3 = box(x + 2 * (bw + bg), y, bw, 150, "run the<br><b>checks</b>", fill=TINT, stroke=ORANGE, sw=5)
    s4 = box(x + 3 * (bw + bg), y, bw, 150, "<b>pass</b> · soft pass<br>· fail", fill=CREAM, stroke=LINE, sw=3)
    for a, b in ((s1, s2), (s2, s3), (s3, s4)):
        edge(a, b, exit=(1, 0.5), entry=(0, 0.5))
    y += 200
    text(x, y, COL_W, 150, "Fifteen checks such as right angle, midpoint, parallel, and point on segment, each "
         "arithmetic with a small tolerance. <b>A right angle is a dot product, not an opinion.</b>", size=38)
    y += 190
    text(x, y, COL_W, 60, "<b>600 prompts</b> from 30 templates, 200 per tier, plus <b>201</b> from a K–12 curriculum.", size=38)
    y += 90
    tw3 = 486
    box(x, y, tw3, 130, "<b>T1</b><br>a single shape", fill="#FFFFFF", stroke=LINE, sw=3)
    box(x + tw3 + 31, y, tw3, 130, "<b>T2</b><br>adds one construction", fill="#FFFFFF", stroke=LINE, sw=3)
    box(x + 2 * (tw3 + 31), y, tw3, 130, "<b>T3</b><br>combines several", fill="#FFFFFF", stroke=LINE, sw=3)
    y += 190

    y = section(1, y + 60, 5, "Can the grader be trusted")
    _, iw, ih = image(img("c41.png"), x, y, w=1000)
    stat(x + 1030, y, 490, ih, "18%", "of the grader's <b>passes</b> overturned by two blind raters<br><br>"
         f"<span style='font-size:88px;font-weight:bold;color:{ORANGE}'>0%</span><br>of its <b>fails</b>")
    y += ih + 40
    text(x, y, COL_W, 130, "The disagreement sits in one tier, T2, where the templates check the construction "
         "but not the angles the prompt gave.", size=36, color=GRAY)

    # ---------------- column 3 ----------------
    x = COL_X[2]
    y = section(2, BODY_Y, 6, "What we found")
    _, iw, ih = image(img("c44.png"), x, y, w=COL_W)
    y += ih + 10
    text(x, y, COL_W, 100, "Strict pass rate on 600 templated prompts, 3 repeats. Dashed box: three models "
         "within one point of each other at a 7× cost spread.", size=34, color=GRAY)
    y += 130
    fh, fg = 250, 30
    finding(x, y, COL_W, fh, "+2 to +25", "<b>The scaffold lifts every model.</b> The weaker a model is at raw TikZ, the more it gains.")
    y += fh + fg
    finding(x, y, COL_W, fh, "1 point", "<b>The frontier converges.</b> GPT-5.5, Sonnet, and Opus finish within one point. Opus costs seven times more.")
    y += fh + fg
    finding(x, y, COL_W, fh, "92 → 36%", "<b>Without the scaffold</b> the same six models spread across 56 points.")
    y += fh + 40
    text(x, y, COL_W, 160, "<b>Wrong drawings, not broken code.</b> Most failures are clean, rendered diagrams with the "
         "wrong geometry. The grader catches them. A person glancing at the picture often would not.", size=40)
    y += 180
    text(x, y, COL_W, 130, "<b>Limits.</b> The top models are near the ceiling on T1 and T2. On the curriculum prompts "
         "every score we ran roughly halved. The scaffold bundles format, compile path, and retries; we have not separated them.",
         size=36, color=GRAY)
    y += 170
    box(x, 3230, COL_W, 300,
        "<b>Each requirement on a drawing can be checked exactly, from its coordinates.<br>"
        "Graded this way, the scaffold matters more than the model.</b>", fill=TINT, stroke=ORANGE, sw=6, size=44)


# ===========================================================================
def kbs():
    img = lambda n: os.path.join(HERE, "img_kbs", n)
    header("Knowing Before Saying:<br>Internal Correctness Signals in Mathematical Reasoning",
           "Mei Chen¹ · Gordon Stein¹ · Andreas Ziegler²",
           "¹Renaissance Philanthropy   ²Institute for Aerospace Studies, University of Toronto", title_size=84)
    band("Open models carry a signal about their own errors that their stated confidence does not. "
         "A linear probe on the hidden state reads it.")

    # ---------------- column 1 ----------------
    x = COL_X[0]
    y = section(0, BODY_Y, 1, "The problem")
    text(x, y, COL_W, 130, "A confidently wrong answer is a problem. On MATH a wrong derivation looks exactly like "
         "a right one, so nothing on the page gives it away.", size=42)
    y += 160
    ex = ("<b>One real attempt. Mistral on MATH.</b><br><br>"
          "<i>What integer n satisfies 0 ≤ n &lt; 18 and n ≡ −11213141 (mod 18)?</i><br><br>"
          "<span style='color:#737382'>Before answering:</span> &nbsp;<b>Confidence 90</b><br><br>"
          "r = −11213141 − 18 × (−622953)<br>r = −11213141 + 11213154<br>"
          f"r = <span style='color:{RED};font-weight:bold'>3</span> &nbsp;&nbsp;<span style='color:#737382'>(it is 13)</span><br>"
          "So n = 3.<br><br>"
          "<span style='color:#737382'>After answering:</span> &nbsp;<b>Confidence 95</b>")
    box(x, y, COL_W, 720, ex, fill="#FFFFFF", stroke=INK, sw=5, size=40, align="left", valign="top", spacing=40)
    y += 760
    pill(x, y, 740, 160, "Model says<br><span style='font-size:60px'>95 / 100</span>", GRAY, size=36)
    pill(x + 780, y, 740, 160, "Probe on the hidden state<br><span style='font-size:60px'>likely wrong</span>", ORANGE, size=36)
    y += 190
    text(x, y, COL_W, 90, "Every step is right until the last subtraction. The slip leaves no mark. Confidence went up.",
         size=36, color=GRAY)
    y += 130

    y = section(0, y, 2, "What is new")
    tw, th, g = 740, 250, 40
    stat(x, y, tw, th, "12 / 16", "model–task cells where the probe beats stated confidence. One tie.")
    stat(x + tw + g, y, tw, th, "+0.20", "AUROC gap on MATH, the largest of the four tasks. Mean gap 0.10.")
    y += th + g
    stat(x, y, tw, th, "0.84 → 0.56", "stated confidence on Mistral once the probed direction is erased", num_size=76)
    stat(x + tw + g, y, tw, th, "4", "open models: Gemma-4, Qwen3.6, GLM-4.7, Mistral")
    y += th + 60

    y = section(0, y, 3, "Code")
    box(x, y, 400, 400, "QR code<br><span style='font-size:28px;color:#737382'>to add</span>", fill="#FFFFFF", stroke=LINE, sw=3, size=34, bold=True)
    text(x + 440, y + 20, COL_W - 440, 360,
         "Code, prompts, and every per-cell number.<br><br><span style='color:#737382'>Repository link to be added.</span>", size=40)

    # ---------------- column 2 ----------------
    x = COL_X[1]
    y = section(1, BODY_Y, 4, "How we read the state")
    text(x, y, COL_W, 110, "Three turns. We record the hidden state at the token where the model is about to write "
         "its confidence digit.", size=40)
    y += 140
    t1 = box(x, y, COL_W, 150, "<b>Turn 1</b> &nbsp;“How confident are you that you will get this right? 0–100.”<br>Model writes a number.", fill=CREAM, stroke=LINE, sw=3)
    y += 220
    t2 = box(x, y, COL_W, 150, "<b>Turn 2</b> &nbsp;The model answers the question.", fill=CREAM, stroke=LINE, sw=3)
    y += 220
    t3 = box(x, y, COL_W, 160, "<b>Turn 3</b> &nbsp;“How confident are you that the answer you just gave is correct?”<br>"
             f"<span style='color:{ORANGE};font-weight:bold'>▲ read site: the hidden state as it writes the digit</span>", fill=TINT, stroke=ORANGE, sw=5)
    edge(t1, t2)
    edge(t2, t3)
    y += 220
    text(x, y, COL_W, 110, "<b>The probe.</b> Standardize, 50 principal components, logistic regression. Five folds grouped "
         "by question, so the probe is scored only on questions it never saw.", size=38)
    y += 150
    text(x, y, COL_W, 150, "<b>The intervention.</b> At that same token, after the answer is written, scale the state along "
         "the correctness direction by a gain g. A random direction of the same norm is the control.", size=38)
    y += 190
    bw, bg = 357, 30
    box(x, y, bw, 140, "<b>g = 0</b><br>erased", fill=TINT, stroke=ORANGE, sw=5)
    box(x + bw + bg, y, bw, 140, "<b>g = 1</b><br>untouched", fill="#FFFFFF", stroke=LINE, sw=3)
    box(x + 2 * (bw + bg), y, bw, 140, "<b>g = 2</b><br>doubled", fill="#FFFFFF", stroke=LINE, sw=3)
    box(x + 3 * (bw + bg), y, bw, 140, "<b>g = 4</b><br>quadrupled", fill="#FFFFFF", stroke=LINE, sw=3)
    y += 210
    text(x, y, COL_W, 70, "<b>Where in the network.</b> Fixed in advance at 70% of depth, for every model and every cell.", size=38)
    y += 100
    _, iw, ih = image(img("c31.png"), x, y, w=COL_W)
    y += ih + 20
    text(x, y, COL_W, 140, "Probe AUROC by depth on MATH, four models. Layer 0 is chance because its token is identical "
         "in every record. The signal is present from the first layers and flat across depth. The dot is the fixed layer.",
         size=34, color=GRAY)

    # ---------------- column 3 ----------------
    x = COL_X[2]
    y = section(2, BODY_Y, 5, "What we found")
    _, iw, ih = image(img("c34.png"), x, y, w=COL_W)
    y += ih + 20
    finding(x, y, COL_W, 230, "12 / 16", "<b>The state carries more than the report.</b> The probe beats stated confidence "
            "in 12 of 16 cells. Mean gap 0.10. On MATH, 0.20.", num_w=400)
    y += 260
    _, iw, ih = image(img("c36.png"), x + (COL_W - 1080) / 2, y, w=1080)
    y += ih + 20
    finding(x, y, COL_W, 260, "0.84<br>→ 0.56", "<b>On Mistral, the report uses the signal.</b> Erase the direction and "
            "stated confidence stops separating right from wrong. A random direction does nothing. "
            "The model becomes uniformly sure, not confused.", num_w=400, num_size=64)
    y += 290
    text(x, y, COL_W, 150, "<b>Not every model.</b> On GLM, erasing changes nothing. On Qwen3.6 the self-report is nearly "
         "flat to begin with, so there is nothing to erase. Gemma-4 leaves too few failures to test.", size=36, color=GRAY)
    box(x, 3230, COL_W, 300,
        "<b>Four open models carry information about their own errors that their self-report does not.<br>"
        "In Mistral, we have shown it is used when it self-reports.</b>", fill=TINT, stroke=ORANGE, sw=6, size=44)


if __name__ == "__main__":
    which, out = sys.argv[1], sys.argv[2]
    {"gg": geogenbench, "kbs": kbs}[which]()
    write(out, "poster")
