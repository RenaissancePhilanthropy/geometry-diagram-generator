"""
Matched-format corpus builder for the cross-domain probe-transfer experiment.

Generates N unique valid geometry constructions from parametric templates
(no LLM), compiles each through the real pipeline for ground truth, and
renders the SAME figure into four surface formats:

  recipe   — the RecipeDSL JSON (the format the original probes were trained on)
  tikz     — tkz-euclide TikZ body via ir_to_tikz (pure text, no Docker)
  svg      — SVG source via ir_to_svg
  english  — plain-English rendering of the construction ops

For every format the builder records the exact char spans of every entity id,
so activation capture and probing need no format-specific parsing downstream.

Point/line labels are RANDOMIZED per figure (midpoints are not named "M"),
which removes the naming confound at the source — the token-identity baseline
for entity_relation should sit at chance on this corpus.

Output (corpus dir):
  figures.jsonl — one line per figure: construction dict, ground truth, params
  items.jsonl   — one line per (figure, format): text + id char spans

Usage:
  interp/.venv/bin/python interp/transfer/build_corpus.py \
      --n-figures 300 --seed 0 --out interp/transfer/corpus
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FORMATS = ("recipe", "tikz", "svg", "english")

# ---------------------------------------------------------------------------
# label pools — randomized per figure so entity names carry no relation info
# ---------------------------------------------------------------------------

_POINT_POOL = list("ABCDEFGHJKLMNPQRSTUVWXYZ")   # no I/O (TikZ/readability)
_LINE_POOL = list("abcdefghjkmnpqrstuvw")        # no i/l/o (confusable)


class Labels:
    """Hands out unique random labels for one figure."""

    def __init__(self, rng: random.Random):
        self.points = _POINT_POOL[:]
        self.lines = _LINE_POOL[:]
        rng.shuffle(self.points)
        rng.shuffle(self.lines)

    def pt(self) -> str:
        return self.points.pop()

    def ln(self) -> str:
        return self.lines.pop()


# ---------------------------------------------------------------------------
# templates — each returns (construction_ops, english_parts)
#
# english_parts is a list of (literal_text | ("id", entity_id)) fragments; the
# english renderer concatenates them and records spans for the id fragments.
# ---------------------------------------------------------------------------

def _tri_spec(rng: random.Random) -> dict:
    """Scalene ASA triangle spec with non-degenerate random angles."""
    a = rng.randint(35, 80)
    b = rng.randint(35, 80)
    while not (90 <= a + b <= 145) or abs(a - b) < 4:
        a, b = rng.randint(35, 80), rng.randint(35, 80)
    s = round(rng.uniform(4.0, 8.0), 1)
    return {"angle_A": a, "angle_B": b, "side_AB": s}


def _tri(rng, lab):
    """Base triangle; returns (op, tri_id, (A,B,C), spec, english_parts)."""
    A, B, C = lab.pt(), lab.pt(), lab.pt()
    t = lab.ln()
    spec = _tri_spec(rng)
    op = {"op": "triangle", "id": t, "vertices": [A, B, C], "spec": spec}
    eng = ["Construct the triangle ", ("id", t), " with vertices ", ("id", A),
           ", ", ("id", B), " and ", ("id", C), ", where the angle at ",
           ("id", A), f" measures {spec['angle_A']} degrees, the angle at ",
           ("id", B), f" measures {spec['angle_B']} degrees, and the side from ",
           ("id", A), " to ", ("id", B), f" has length {spec['side_AB']}. "]
    return op, t, (A, B, C), eng


def t_midsegment(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    M, N = lab.pt(), lab.pt()
    ops = [op,
           {"op": "midpoint", "id": M, "of": [A, B]},
           {"op": "midpoint", "id": N, "of": [A, C]},
           {"op": "segment", "id": lab.ln(), "endpoints": [M, N]}]
    eng += ["Let ", ("id", M), " be the midpoint of the segment from ",
            ("id", A), " to ", ("id", B), ". Let ", ("id", N),
            " be the midpoint of the segment from ", ("id", A), " to ",
            ("id", C), ". Draw the segment connecting ", ("id", M), " and ",
            ("id", N), "."]
    return ops, eng


def t_altitude(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    F, h = lab.pt(), lab.ln()
    ops = [op, {"op": "altitude", "id": h, "from_vertex": C, "triangle": t,
                "foot": F}]
    eng += ["Draw the altitude ", ("id", h), " from the vertex ", ("id", C),
            " of the triangle ", ("id", t),
            ", meeting the opposite side at the foot ", ("id", F), "."]
    return ops, eng


def t_perp_parallel(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    base, p, q = lab.ln(), lab.ln(), lab.ln()
    ops = [op,
           {"op": "line_through", "id": base, "points": [A, B]},
           {"op": "perpendicular", "id": p, "to_line": base, "through": C},
           {"op": "parallel", "id": q, "to_line": base, "through": C}]
    eng += ["Draw the line ", ("id", base), " through the points ", ("id", A),
            " and ", ("id", B), ". Draw the line ", ("id", p), " through ",
            ("id", C), " perpendicular to the line ", ("id", base),
            ". Draw the line ", ("id", q), " through ", ("id", C),
            " parallel to the line ", ("id", base), "."]
    return ops, eng


def t_bisector(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    w, base, D = lab.ln(), lab.ln(), lab.pt()
    ops = [op,
           {"op": "angle_bisector", "id": w, "vertex": A,
            "ray1_toward": B, "ray2_toward": C},
           {"op": "line_through", "id": base, "points": [B, C]},
           {"op": "intersection", "id": D, "of": [w, base],
            "selector": {"kind": "index", "k": 0}}]
    eng += ["Draw the bisector ", ("id", w), " of the angle at the vertex ",
            ("id", A), " between the rays toward ", ("id", B), " and toward ",
            ("id", C), ". Draw the line ", ("id", base),
            " through the points ", ("id", B), " and ", ("id", C), ". Let ",
            ("id", D), " be the intersection of ", ("id", w), " and ",
            ("id", base), "."]
    return ops, eng


def t_tangent(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    cc, O, E, tan = lab.ln(), lab.pt(), lab.pt(), lab.ln()
    ops = [op,
           {"op": "circumcircle", "id": cc, "of": t, "center": O},
           {"op": "reflection", "id": E, "point": O, "over": A},
           {"op": "tangent_line", "id": tan, "circle": cc, "from_point": E,
            "selector": {"kind": "index", "k": 0}}]
    eng += ["Draw the circumscribed circle ", ("id", cc), " of the triangle ",
            ("id", t), " with center ", ("id", O), ". Let ", ("id", E),
            " be the reflection of the point ", ("id", O), " over ", ("id", A),
            ". Draw the tangent line ", ("id", tan), " to the circle ",
            ("id", cc), " from the external point ", ("id", E), "."]
    return ops, eng


def t_cevian(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    P, M = lab.pt(), lab.pt()
    num, den = rng.choice([(1, 2), (1, 3), (2, 3), (3, 4), (2, 5)])
    ratio = f"{num}:{den - num}" if den - num > 0 else "1:1"
    frac = f"{num}/{den}"
    ops = [op,
           {"op": "point_on_segment", "id": P, "segment": [B, C],
            "ratio": ratio},
           {"op": "segment", "id": lab.ln(), "endpoints": [A, P]},
           {"op": "midpoint", "id": M, "of": [A, P]}]
    eng += ["Place the point ", ("id", P), " on the segment from ", ("id", B),
            " to ", ("id", C), f" so that it lies {frac} of the way from ",
            ("id", B), ". Draw the segment connecting ", ("id", A), " and ",
            ("id", P), ". Let ", ("id", M),
            " be the midpoint of the segment from ", ("id", A), " to ",
            ("id", P), "."]
    return ops, eng


def t_perp_bisector(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    pb, M = lab.ln(), lab.pt()
    ops = [op,
           {"op": "perpendicular_bisector", "id": pb, "of": [A, B], "mid": M}]
    eng += ["Draw the perpendicular bisector ", ("id", pb),
            " of the segment from ", ("id", A), " to ", ("id", B),
            ", crossing it at the midpoint ", ("id", M), "."]
    return ops, eng


def t_median(rng, lab):
    op, t, (A, B, C), eng = _tri(rng, lab)
    med, M = lab.ln(), lab.pt()
    ops = [op,
           {"op": "median", "id": med, "from_vertex": A, "triangle": t,
            "mid": M}]
    eng += ["Draw the median ", ("id", med), " from the vertex ", ("id", A),
            " of the triangle ", ("id", t),
            ", meeting the opposite side at its midpoint ", ("id", M), "."]
    return ops, eng


TEMPLATES = {
    "midsegment": t_midsegment,
    "altitude": t_altitude,
    "perp_parallel": t_perp_parallel,
    "bisector": t_bisector,
    "tangent": t_tangent,
    "cevian": t_cevian,
    "perp_bisector": t_perp_bisector,
    "median": t_median,
}


# ---------------------------------------------------------------------------
# format renderers — each returns (text, {entity_id: [[start, end], ...]})
# ---------------------------------------------------------------------------

def _boundary_spans(text: str, entity_id: str) -> list[list[int]]:
    """Char spans where entity_id occurs as a standalone identifier."""
    pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(entity_id)}(?![A-Za-z0-9_])")
    return [[m.start(), m.end()] for m in pat.finditer(text)]


def _quoted_spans(text: str, entity_id: str) -> list[list[int]]:
    """Char spans of the id inside quoted occurrences ("id"), matching the
    convention of geometry_labels.id_positions."""
    needle = f'"{entity_id}"'
    spans, start = [], 0
    while True:
        j = text.find(needle, start)
        if j == -1:
            break
        spans.append([j + 1, j + 1 + len(entity_id)])
        start = j + 1
    return spans


def render_recipe(construction: dict, entity_ids: set[str]):
    text = json.dumps(construction, indent=2)
    return text, {e: _quoted_spans(text, e) for e in entity_ids}


def render_tikz(diagram_ir, sym, entity_ids: set[str]):
    from ir.to_tikz import ir_to_tikz
    text = ir_to_tikz(diagram_ir, sym)
    return text, {e: _boundary_spans(text, e) for e in entity_ids}


def render_svg(diagram_ir, sym, entity_ids: set[str]):
    """Entity spans are only searched inside <text> element content — single-
    letter ids collide with SVG path commands (M, L, C, A, Z) otherwise."""
    from ir.to_svg import ir_to_svg
    text = ir_to_svg(diagram_ir, sym)
    spans: dict[str, list[list[int]]] = {e: [] for e in entity_ids}
    for m in re.finditer(r"<text[^>]*>(.*?)</text>", text, re.DOTALL):
        content, base = m.group(1), m.start(1)
        for e in entity_ids:
            for s, t in _boundary_spans(content, e):
                spans[e].append([base + s, base + t])
    return text, spans


def render_english(english_parts, entity_ids: set[str]):
    chunks, spans = [], {e: [] for e in entity_ids}
    pos = 0
    for part in english_parts:
        if isinstance(part, tuple):
            _, eid = part
            if eid in spans:
                spans[eid].append([pos, pos + len(eid)])
            chunks.append(eid)
            pos += len(eid)
        else:
            chunks.append(part)
            pos += len(part)
    return "".join(chunks), spans


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build_figure(template_name: str, rng: random.Random):
    """Generate + validate one figure; returns record dict or None."""
    from interp.geometry_labels import ground_truth, entity_ids
    from interp import grade
    from recipe.dsl import RecipeDSL
    from recipe.lower import lower_to_ir
    from ir.to_sympy import compile_defs

    lab = Labels(rng)
    ops, english_parts = TEMPLATES[template_name](rng, lab)
    construction = {"mode": "abstract", "construction": ops,
                    "annotations": {"auto_draw_all": True,
                                    "auto_label_points": True}}

    gt = ground_truth(construction)
    if not gt.get("ok"):
        return None
    g = grade.grade_completion(json.dumps(construction))
    if not g.ok:
        return None

    dsl = RecipeDSL.model_validate(construction)
    diagram_ir = lower_to_ir(dsl)
    sym = compile_defs(diagram_ir)

    eids = entity_ids(gt)
    formats = {}
    formats["recipe"] = render_recipe(construction, eids)
    formats["tikz"] = render_tikz(diagram_ir, sym, eids)
    formats["svg"] = render_svg(diagram_ir, sym, eids)
    formats["english"] = render_english(english_parts, eids)

    return {"construction": construction, "ground_truth": gt,
            "formats": formats, "entity_ids": sorted(eids)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-figures", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="interp/transfer/corpus")
    ap.add_argument("--max-tries", type=int, default=8,
                    help="param redraws per figure slot before giving up")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    tnames = list(TEMPLATES)

    figures, items = [], []
    fails = 0
    for i in range(args.n_figures):
        tname = tnames[i % len(tnames)]
        rec = None
        for _ in range(args.max_tries):
            rec = build_figure(tname, rng)
            if rec is not None:
                break
        if rec is None:
            fails += 1
            continue
        fid = f"{tname}_{i:04d}"
        figures.append({"figure_id": fid, "template": tname,
                        "construction": rec["construction"],
                        "ground_truth": rec["ground_truth"],
                        "entity_ids": rec["entity_ids"]})
        for fmt, (text, spans) in rec["formats"].items():
            items.append({"figure_id": fid, "format": fmt, "text": text,
                          "id_spans": {k: v for k, v in spans.items() if v}})

    with open(out / "figures.jsonl", "w") as f:
        for r in figures:
            f.write(json.dumps(r) + "\n")
    with open(out / "items.jsonl", "w") as f:
        for r in items:
            f.write(json.dumps(r) + "\n")

    # coverage report
    n_fig = len(figures)
    print(f"figures: {n_fig} valid ({fails} slots failed after retries)")
    by_fmt: dict[str, list[int]] = {f: [] for f in FORMATS}
    rel_counts: dict[str, int] = {}
    for r in figures:
        for rel in (r["ground_truth"].get("entity_relations") or {}).values():
            rel_counts[rel] = rel_counts.get(rel, 0) + 1
    for it in items:
        by_fmt[it["format"]].append(len(it["id_spans"]))
    for fmt in FORMATS:
        v = by_fmt[fmt]
        lens = [len(it["text"]) for it in items if it["format"] == fmt]
        print(f"  {fmt:8s}: mean entities-with-spans {sum(v)/max(len(v),1):.1f}"
              f", mean text chars {sum(lens)/max(len(lens),1):.0f}")
    print("relation classes:", json.dumps(rel_counts))


if __name__ == "__main__":
    main()
