#!/usr/bin/env python
"""Render the PRE/POST probe-by-depth curves as a themed inline SVG.

Two panels sharing one y scale. Each panel has two lines: the probe read before the
model attempts (difficulty only) and after it attempts. The contrast between the
panels is the point, so the axes are identical and the panels sit side by side.

Colors come from CSS custom properties so the figure themes with the page it is
embedded in; `currentColor` carries axes and text.

Usage:
    python interp/analysis/make_pre_post_svg.py \
        interp/results/curve_mmlu_pro.json interp/results/curve_geometry.json \
        --out interp/results/fig_pre_post.svg
"""
from __future__ import annotations

import argparse
import json
import pathlib

W, H = 760, 356
PAD_L, PAD_R, PAD_T, PAD_B = 52, 18, 44, 74
GAP = 46
YMIN, YMAX = 0.40, 0.90


def panel(x0: float, w: float, d: dict, show_y: bool) -> str:
    pre, post = d["curve"]["pre"], d["curve"]["post"]
    L = len(pre)
    ph = H - PAD_T - PAD_B
    fx = lambda i: x0 + (i / (L - 1)) * w
    fy = lambda v: PAD_T + ph * (1 - (v - YMIN) / (YMAX - YMIN))
    out = []

    # gridlines + y labels
    for v in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        y = fy(v)
        dash = ' stroke-dasharray="4 3"' if abs(v - 0.5) < 1e-9 else ""
        op = ".45" if abs(v - 0.5) < 1e-9 else ".14"
        out.append(f'<line x1="{x0:.0f}" y1="{y:.1f}" x2="{x0+w:.0f}" y2="{y:.1f}" '
                   f'stroke="currentColor" stroke-opacity="{op}"{dash}/>')
        if show_y:
            out.append(f'<text x="{x0-9:.0f}" y="{y+3.5:.1f}" text-anchor="end" font-size="10.5" '
                       f'fill="currentColor" fill-opacity=".55">{v:.1f}</text>')
    out.append(f'<text x="{x0-9:.0f}" y="{fy(0.5)-11:.1f}" text-anchor="end" font-size="9.5" '
               f'fill="currentColor" fill-opacity=".55">chance</text>' if show_y else "")

    # x ticks at 0, .25, .5, .75, 1 of depth
    for frac in (0, .25, .5, .75, 1.0):
        i = round(frac * (L - 1))
        out.append(f'<text x="{fx(i):.0f}" y="{H-PAD_B+16:.0f}" text-anchor="middle" font-size="10.5" '
                   f'fill="currentColor" fill-opacity=".55">{i}</text>')

    def path(vals, color, dash=""):
        pts = " ".join(f"{fx(i):.1f},{fy(v):.1f}" for i, v in enumerate(vals) if v == v)
        return (f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.1" '
                f'stroke-linejoin="round"{dash}/>')

    out.append(path(pre, "var(--stated, #2F6DB5)", ' stroke-dasharray="5 4"'))
    out.append(path(post, "var(--internal, #E0562B)"))

    # mark the reported layer
    fixed = d["fixed_layer"]
    out.append(f'<line x1="{fx(fixed):.1f}" y1="{PAD_T}" x2="{fx(fixed):.1f}" y2="{H-PAD_B}" '
               f'stroke="currentColor" stroke-opacity=".28" stroke-dasharray="2 3"/>')
    out.append(f'<text x="{fx(fixed):.1f}" y="{PAD_T-8:.0f}" text-anchor="middle" font-size="9.5" '
               f'fill="currentColor" fill-opacity=".55">reported layer</text>')

    # endpoint values
    f = d["at_fixed_layer"]
    y_post, y_pre = fy(f["post"]), fy(f["pre"])
    out.append(f'<circle cx="{fx(fixed):.1f}" cy="{y_post:.1f}" r="3.6" fill="var(--internal, #E0562B)"/>')
    out.append(f'<circle cx="{fx(fixed):.1f}" cy="{y_pre:.1f}" r="3.6" fill="var(--stated, #2F6DB5)"/>')
    ty_post, ty_pre = y_post - 8, y_pre + 15
    if abs(ty_post - ty_pre) < 15:                    # lines cross: separate the labels,
        mid = (y_post + y_pre) / 2                    # keeping each above/below its own dot
        if y_post <= y_pre:
            ty_post, ty_pre = mid - 10, mid + 19
        else:
            ty_pre, ty_post = mid - 10, mid + 19
    out.append(f'<text x="{fx(fixed)+7:.1f}" y="{ty_post:.1f}" font-size="11" font-weight="700" '
               f'fill="var(--internal, #E0562B)">{f["post"]:.2f}</text>')
    out.append(f'<text x="{fx(fixed)+7:.1f}" y="{ty_pre:.1f}" font-size="11" font-weight="700" '
               f'fill="var(--stated, #2F6DB5)">{f["pre"]:.2f}</text>')

    # panel title + axis frame
    out.append(f'<text x="{x0:.0f}" y="{PAD_T-24:.0f}" font-size="13" font-weight="700" '
               f'fill="currentColor">{d["label"]}</text>')
    out.append(f'<line x1="{x0:.0f}" y1="{H-PAD_B:.0f}" x2="{x0+w:.0f}" y2="{H-PAD_B:.0f}" '
               f'stroke="currentColor" stroke-opacity=".45"/>')
    return "\n  ".join(p for p in out if p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs=2)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ds = [json.loads(pathlib.Path(p).read_text()) for p in a.json]

    pw = (W - PAD_L - PAD_R - GAP) / 2
    label = (f'{ds[0]["label"]} and {ds[1]["label"]}: probe accuracy by depth, read before '
             f'versus after the attempt')
    body = [panel(PAD_L, pw, ds[0], True),
            panel(PAD_L + pw + GAP, pw, ds[1], False)]

    legend_y = H - 10
    legend = (
        f'<line x1="{PAD_L}" y1="{legend_y-4}" x2="{PAD_L+22}" y2="{legend_y-4}" '
        f'stroke="var(--stated, #2F6DB5)" stroke-width="2.1" stroke-dasharray="5 4"/>'
        f'<text x="{PAD_L+28}" y="{legend_y}" font-size="11" fill="currentColor">'
        f'before the attempt (question only)</text>'
        f'<line x1="{PAD_L+232}" y1="{legend_y-4}" x2="{PAD_L+254}" y2="{legend_y-4}" '
        f'stroke="var(--internal, #E0562B)" stroke-width="2.1"/>'
        f'<text x="{PAD_L+260}" y="{legend_y}" font-size="11" fill="currentColor">'
        f'after the attempt</text>'
    )
    svg = (
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{label}" '
        f'font-family="Manrope, Helvetica Neue, Arial, sans-serif">\n  '
        + "\n  ".join(body)
        + f'\n  <text x="{PAD_L+pw/2:.0f}" y="{H-PAD_B+34:.0f}" text-anchor="middle" font-size="10.5" '
          f'fill="currentColor" fill-opacity=".55">layer</text>\n  '
        + f'\n  <text x="{PAD_L+pw+GAP+pw/2:.0f}" y="{H-PAD_B+34:.0f}" text-anchor="middle" font-size="10.5" '
          f'fill="currentColor" fill-opacity=".55">layer</text>'
        + legend + "\n</svg>\n"
    )
    pathlib.Path(a.out).write_text(svg)
    print("wrote", a.out, f"({len(svg)} bytes)")
    for d in ds:
        f = d["at_fixed_layer"]
        print(f'  {d["label"]:10} pre {f["pre"]:.3f}  post {f["post"]:.3f}  '
              f'corr {f["corr_pre_post_scores"]:+.2f}  post-probe-at-pre {f["post_probe_read_at_pre_site"]:.3f}')


if __name__ == "__main__":
    main()
