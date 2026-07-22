#!/usr/bin/env python
"""Paper figures from the locally-captured data. Offline, no GPU.

Computes per-cell AUROCs (verbalized / P(True) / internal probe, across- and
within-question) once, caches to interp/activations/plot_cache.json, then renders:

  fig1_internal_vs_verbalized.png  headline — probe beats stated confidence, per cell
  fig2_gap_by_domain.png           knowing-saying gap (probe - verbalized) by domain
  fig3_within_question.png         probe vs P(True) with difficulty fixed (the dissociation)
  fig4_steering.png                Mistral amplify: fail-confidence closes, correct holds, random flat
  fig5_layer_curve.png             decodability vs depth (chance at layer 0 -> mid/late peak)

    interp/.venv/bin/python interp/analysis/make_plots.py            # uses cache if present
    interp/.venv/bin/python interp/analysis/make_plots.py --recompute
"""
from __future__ import annotations
import argparse, json, pathlib, re, sys, warnings
import numpy as np
warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tier1_review import oof_scores, _auroc, within_q

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager  # noqa

ROOT = pathlib.Path("interp/activations")
FIGS = pathlib.Path("interp/figures"); FIGS.mkdir(exist_ok=True)
MODELS = ["gemma4", "qwen36", "glm", "mistral"]
DOMAINS = ["mmlu_pro", "math", "gpqa", "temporal"]
DLABEL = {"mmlu_pro": "MMLU-Pro", "math": "MATH", "gpqa": "GPQA", "temporal": "Geometry"}
MLABEL = {"gemma4": "Gemma-4", "qwen36": "Qwen3.6", "glm": "GLM-4.7", "mistral": "Mistral"}
# palette — matches the deck
INK, PAPER, SIGNAL, OKC, WRONGC, MUTED = "#14181f", "#e9ebee", "#e0932f", "#2f9e6b", "#cf4a52", "#8b97a5"
PROBE_C, VERB_C, PT_C = "#2f6fe0", "#b9772a", "#cf4a52"
# Renaissance Philanthropy brand palette (from renaissancephilanthropy.org)
DECK = {
    "PAPER": "#FFFFFF",
    "CARD": "#FFFFFF",
    "INK": "#131318",
    "MUTED": "#737382",
    "ACCENT": "#F87248",      # coral — the brand accent
    "ACCENT_SOFT": "#FBE4DA",
    "OK": "#2E7D4F",
    "FAIL": "#A32E2E",        # semantic red, kept distinct from the coral accent
    "SLATE": "#2F4F4F",
    "LINE": "#E4E3E7",
}


def cell_dir(m, d):
    return ROOT / (f"{m}_temporal" if d == "temporal" else f"fix_{m}_{d}")


def compute():
    out = {}
    for m in MODELS:
        for d in DOMAINS:
            cd = cell_dir(m, d)
            mf = cd / "meta.jsonl"
            if not mf.exists():
                continue
            recs = [json.loads(l) for l in mf.read_text().splitlines()]
            recs = [r for r in recs if (cd / f"{r['pid']}.npz").exists()]
            if len(recs) < 40:
                continue
            X, y, g, pt, vc = [], [], [], [], []
            for r in recs:
                try:
                    z = np.load(cd / f"{r['pid']}.npz")
                except Exception:
                    continue
                if "post_dtoken" not in z:
                    continue
                L = z["post_dtoken"].shape[0] - 1
                X.append(z["post_dtoken"][int(round(0.7 * L))].astype(np.float32))
                y.append(1 if r["grade"]["ok"] else 0)
                g.append(re.sub(r"_s\d+$", "", r["pid"]))
                pt.append(r.get("p_true")); vc.append(r.get("post_conf"))
            if len(set(y)) < 2:
                continue
            X, y, g = np.stack(X), np.array(y), np.array(g)
            pt = np.array([v if v is not None else np.nan for v in pt], float)
            vc = np.array([v if v is not None else np.nan for v in vc], float)
            s, _ = oof_scores(X, y, g); ok = ~np.isnan(s)
            mv = ok & ~np.isnan(vc)                 # probe vs verbalized (same-record; incl. geometry)
            if mv.sum() < 10:
                continue
            mpt = mv & ~np.isnan(pt)                # + P(True): QA only (geometry has no P(True))
            has_pt = mpt.sum() > 10
            # within-question probe/P(True) on the SAME records (mpt) where P(True) exists
            wq_p, nq = within_q(s[mpt], y[mpt], g[mpt]) if has_pt else within_q(s[mv], y[mv], g[mv])
            wq_pt, _ = within_q(pt[mpt], y[mpt], g[mpt]) if has_pt else (np.nan, 0)
            rec = dict(n=int(mv.sum()), pass_rate=float(y[mv].mean()),
                       probe=_auroc(s[mv], y[mv]),
                       verbalized=_auroc(vc[mv], y[mv]),
                       p_true=_auroc(pt[mpt], y[mpt]) if has_pt else None,
                       wq_probe=wq_p, wq_ptrue=wq_pt, n_mixed=nq)
            out[f"{m}_{d}"] = rec
            print(f"  {m:>8} {d:<9} n={rec['n']:<4} probe={rec['probe']:.3f} "
                  f"verb={rec['verbalized']}", flush=True)
    return out


def style(ax, theme=None):
    if theme is None:
        theme = {"paper": PAPER, "ink": INK, "muted": MUTED, "line": "#cfd4da", "transparent": False}
    ax.set_facecolor("none" if theme["transparent"] else theme["paper"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(theme["muted"])
    ax.tick_params(colors=theme["ink"], labelsize=theme["tick_size"])
    ax.grid(axis="y", color=theme["line"], lw=.7, zorder=0)


def plot_theme(deck=False):
    if deck:
        return {
            "paper": DECK["PAPER"],
            "ink": DECK["INK"],
            "muted": DECK["MUTED"],
            "line": DECK["LINE"],
            "probe": DECK["ACCENT"],
            "verb": DECK["MUTED"],
            "signal": DECK["ACCENT"],
            "ok": DECK["OK"],
            "wrong": DECK["FAIL"],
            "p_true": DECK["MUTED"],
            "transparent": True,
            "tick_size": 10,
            "label_size": 11,
            "legend_size": 10,
            "title": False,
            "fig5_colors": [DECK["ACCENT"], DECK["SLATE"], DECK["MUTED"], DECK["INK"]],
        }
    return {
        "paper": PAPER,
        "ink": INK,
        "muted": MUTED,
        "line": "#cfd4da",
        "probe": PROBE_C,
        "verb": VERB_C,
        "signal": SIGNAL,
        "ok": OKC,
        "wrong": WRONGC,
        "p_true": PT_C,
        "transparent": False,
        "tick_size": 9,
        "label_size": 10,
        "legend_size": 10,
        "title": True,
        "fig5_colors": None,
    }


def finish(fig, path, theme):
    fig.tight_layout()
    if theme["transparent"]:
        fig.patch.set_alpha(0)
        fig.savefig(path, transparent=True)
    else:
        fig.savefig(path, facecolor=theme["paper"])
    plt.close(fig)


def fig1(C, deck=False, out=None):
    theme = plot_theme(deck)
    out = out or (FIGS / "fig1_internal_vs_verbalized.png")
    keys = [f"{m}_{d}" for d in DOMAINS for m in MODELS if f"{m}_{d}" in C and C[f"{m}_{d}"]["verbalized"]]
    labels = [f"{MLABEL[k.split('_')[0]]}\n{DLABEL[k.split('_',1)[1]]}" for k in keys]
    v = [C[k]["verbalized"] for k in keys]; p = [C[k]["probe"] for k in keys]
    x = np.arange(len(keys)); w = 0.38
    fig, ax = plt.subplots(figsize=(min(15, 1.0 * len(keys) + 2), 5.2), dpi=150)
    fig.patch.set_facecolor(theme["paper"])
    ax.bar(x - w/2, v, w, label="stated confidence", color=theme["verb"], zorder=3)
    ax.bar(x + w/2, p, w, label="internal probe", color=theme["probe"], zorder=3)
    ax.axhline(0.5, color=theme["muted"], lw=1, ls=(0, (4, 3)), zorder=2)
    ax.text(len(keys)-.4, 0.505, "chance", color=theme["muted"], fontsize=theme["tick_size"] - 1, va="bottom", ha="right")
    style(ax, theme); ax.set_ylim(0.4, 1.0); ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=theme["tick_size"] - 1)
    ax.set_ylabel("AUROC  (predicting own correctness)", fontsize=theme["label_size"], color=theme["ink"])
    if theme["title"]:
        ax.set_title("The residual stream predicts correctness better than the model says it can",
                     fontsize=13, color=theme["ink"], weight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=theme["legend_size"], loc="upper right")
    finish(fig, out, theme)


def fig2(C, deck=False, out=None):
    theme = plot_theme(deck)
    out = out or (FIGS / "fig2_gap_by_domain.png")
    by = {d: [] for d in DOMAINS}
    for k, r in C.items():
        if r["verbalized"] is None:
            continue
        d = k.split("_", 1)[1]
        by[d].append(r["probe"] - r["verbalized"])
    dd = [d for d in DOMAINS if by[d]]
    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=150); fig.patch.set_facecolor(theme["paper"])
    x = np.arange(len(dd))
    means = [np.mean(by[d]) for d in dd]
    ax.bar(x, means, 0.6, color=theme["signal"], zorder=3)
    for i, d in enumerate(dd):
        for val in by[d]:
            ax.scatter(i + np.random.uniform(-.12, .12), val, color=theme["ink"], s=22, zorder=4, alpha=.7)
    ax.axhline(0, color=theme["muted"], lw=1)
    style(ax, theme); ax.set_xticks(x); ax.set_xticklabels([DLABEL[d] for d in dd])
    ax.set_ylabel("probe − stated  (AUROC gap)", fontsize=theme["label_size"], color=theme["ink"])
    if theme["title"]:
        ax.set_title("Knowing − saying gap, by domain  (dots = models)",
                     fontsize=12.5, color=theme["ink"], weight="bold", loc="left", pad=12)
    finish(fig, out, theme)


def fig3(C, deck=False, out=None):
    theme = plot_theme(deck)
    out = out or (FIGS / "fig3_within_question.png")
    keys = [k for k in C if not np.isnan(C[k]["wq_probe"]) and not np.isnan(C[k]["wq_ptrue"])
            and C[k]["n_mixed"] >= 20]
    keys.sort(key=lambda k: -C[k]["wq_probe"])
    labels = [f"{MLABEL[k.split('_')[0]]} · {DLABEL[k.split('_',1)[1]]}\n(n={C[k]['n_mixed']})" for k in keys]
    wp = [C[k]["wq_probe"] for k in keys]; wt = [C[k]["wq_ptrue"] for k in keys]
    x = np.arange(len(keys)); w = 0.38
    fig, ax = plt.subplots(figsize=(min(13, 1.1*len(keys)+3), 4.8), dpi=150); fig.patch.set_facecolor(theme["paper"])
    ax.bar(x - w/2, wp, w, label="internal probe", color=theme["probe"], zorder=3)
    ax.bar(x + w/2, wt, w, label="P(True)  (the model's own bet)", color=theme["p_true"], zorder=3)
    ax.axhline(0.5, color=theme["muted"], lw=1, ls=(0, (4, 3)))
    style(ax, theme); ax.set_ylim(0.35, 0.85); ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=theme["tick_size"] - 1, rotation=18, ha="right")
    ax.set_ylabel("within-question AUROC", fontsize=theme["label_size"], color=theme["ink"])
    if theme["title"]:
        ax.set_title("Difficulty held fixed: the probe tracks the attempt, P(True) falls to chance",
                     fontsize=12, color=theme["ink"], weight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=theme["legend_size"])
    finish(fig, out, theme)


def fig4(deck=False, out=None):
    theme = plot_theme(deck)
    out = out or (FIGS / "fig4_steering.png")
    p = ROOT / "fix_mistral_math" / "steer_amplify.json"
    if not p.exists():
        print("  (no mistral steer_amplify.json — skip fig4)"); return
    j = json.load(open(p)); R = j["results"]
    gains = sorted({float(k.split("@")[1]) for k in R})
    def series(kind, field):
        return [R.get(f"{kind}@{g}", {}).get(field) for g in gains]
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=150); fig.patch.set_facecolor(theme["paper"])
    ax.plot(gains, series("steer", "mean_conf_fail"), "-o", color=theme["wrong"], lw=2.4, ms=7,
            label="stated conf · WRONG answers (steer)", zorder=4)
    ax.plot(gains, series("steer", "mean_conf_ok"), "-o", color=theme["ok"], lw=2.4, ms=7,
            label="stated conf · correct answers (steer)", zorder=4)
    rf = series("random", "mean_conf_fail")
    ax.plot(gains, rf, "--s", color=theme["muted"], lw=1.6, ms=5, label="WRONG answers (random dir.)", zorder=3)
    style(ax, theme); ax.set_xlabel("amplification gain  (1 = no-op)", fontsize=theme["label_size"], color=theme["ink"])
    ax.set_ylabel("mean stated confidence", fontsize=theme["label_size"], color=theme["ink"])
    if theme["title"]:
        ax.set_title("Amplifying the model's own signal makes it honest — Mistral × MATH",
                     fontsize=12, color=theme["ink"], weight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=theme["legend_size"] - 1, loc="lower left")
    finish(fig, out, theme)


def fig5(deck=False, out=None):
    theme = plot_theme(deck)
    out = out or (FIGS / "fig5_layer_curve.png")
    # decodability vs depth from saved layer curves (post_dtoken), averaged over models
    curves = []
    for m in MODELS:
        p = ROOT / f"mtx_{m}_mmlu_pro" / "temporal_analysis.json"
        if not p.exists():
            continue
        lc = json.load(open(p)).get("layer_curves", {}).get("post_dtoken")
        if lc:
            arr = np.array([np.nan if v is None else v for v in lc], float)
            xs = np.linspace(0, 1, len(arr))
            curves.append((xs, arr, MLABEL[m]))
    if not curves:
        print("  (no layer curves — skip fig5)"); return
    fig, ax = plt.subplots(figsize=(7.2, 4.8), dpi=150); fig.patch.set_facecolor(theme["paper"])
    for i, (xs, arr, lab) in enumerate(curves):
        color = theme["fig5_colors"][i % len(theme["fig5_colors"])] if theme["fig5_colors"] else None
        ax.plot(xs, arr, lw=2, alpha=.85, label=lab, color=color)
    ax.axhline(0.5, color=theme["muted"], lw=1, ls=(0, (4, 3)))
    ax.text(0.01, 0.505, "chance", color=theme["muted"], fontsize=theme["tick_size"] - 1, va="bottom")
    style(ax, theme); ax.set_xlabel("relative depth  (layer 0 → final)", fontsize=theme["label_size"], color=theme["ink"])
    ax.set_ylabel("correctness AUROC (probe)", fontsize=theme["label_size"], color=theme["ink"])
    if theme["title"]:
        ax.set_title("Computed, not lexical: chance at the embedding, rising to a mid/late peak",
                     fontsize=12, color=theme["ink"], weight="bold", loc="left", pad=12)
    ax.legend(frameon=False, fontsize=theme["legend_size"] - 1, title="MMLU-Pro", title_fontsize=theme["legend_size"] - 1)
    finish(fig, out, theme)


def render_deck_svgs(C):
    with plt.rc_context({
        "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "svg.fonttype": "none",
    }):
        paths = [
            FIGS / "fig1_deck.svg",
            FIGS / "fig2_deck.svg",
            FIGS / "fig3_deck.svg",
            FIGS / "fig4_deck.svg",
            FIGS / "fig5_deck.svg",
        ]
        fig1(C, deck=True, out=paths[0])
        fig2(C, deck=True, out=paths[1])
        fig3(C, deck=True, out=paths[2])
        fig4(deck=True, out=paths[3])
        fig5(deck=True, out=paths[4])
    return paths


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--recompute", action="store_true")
    args = ap.parse_args()
    cachep = ROOT / "plot_cache.json"
    if cachep.exists() and not args.recompute:
        C = json.load(open(cachep)); print(f"loaded cache ({len(C)} cells)")
    else:
        print("computing per-cell AUROCs (this is the slow part)...")
        C = compute(); cachep.write_text(json.dumps(C, indent=2))
        print(f"cached -> {cachep}")
    fig1(C); fig2(C); fig3(C); fig4(); fig5()
    svg_paths = render_deck_svgs(C)
    print("saved figures ->", FIGS)
    for f in sorted(FIGS.glob("*.png")):
        print("  ", f.name)
    for f in svg_paths:
        if f.exists():
            print("  ", f)


if __name__ == "__main__":
    main()
