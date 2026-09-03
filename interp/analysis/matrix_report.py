#!/usr/bin/env python
"""Aggregate the temporal-confidence matrix into one table with a RIGOR-corrected
internal-probe readout.

confidence_temporal.py reports internal AUROC at the BEST layer = max over 30-64
per-layer OOF AUROCs. Each layer's AUROC is honestly cross-validated (GroupKFold,
base-prompt-grouped), but taking the MAX over many layers is optimistically biased by
selection. This reads each cell's saved temporal_analysis.json (the per-layer curves —
no re-probe needed) and reports, for the POST and clean-PRE (no-elicitation) sites:

  layer0    AUROC at the embedding layer — read-site control; should be ~0.5 at the
            content-neutral decision token (if it's high, the site leaks identity).
  best      max over layers (optimistic; what the earlier messages quoted).
  fixed@0.7 AUROC at a single a-priori layer (0.7 * depth) — no selection bias.
  band      mean AUROC over the 0.5-0.9 depth band — robust to one spiky layer.

If internal (band / fixed@0.7) still clears verbalized, the "internal >> verbalized"
headline is robust to the layer-selection concern. Offline; reads only JSON.

    interp/.venv/bin/python interp/analysis/matrix_report.py
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

MODELS = ["gemma4", "qwen36", "glm", "mistral"]
QA = ["mmlu_pro", "gsm8k", "math", "gpqa"]
# (cell dir, model, domain) — QA matrix + geometry temporal.
CELLS = [(f"mtx_{m}_{b}", m, b) for m in MODELS for b in QA] + \
        [(f"{m}_temporal", m, "geometry") for m in MODELS]


def readout(curve):
    """(layer0, best, fixed@0.7, band[0.5-0.9]) from a per-layer AUROC list."""
    arr = np.array([np.nan if a is None else float(a) for a in curve], float)
    n = len(arr)
    if n == 0:
        return (np.nan,) * 4
    last = n - 1
    lo, hi = int(round(0.5 * last)), int(round(0.9 * last))
    return (arr[0], float(np.nanmax(arr)), arr[int(round(0.7 * last))],
            float(np.nanmean(arr[lo:hi + 1])))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-root", default="interp/activations")
    args = ap.parse_args()
    root = pathlib.Path(args.act_root)

    hdr = (f"{'cell':<22} {'pass':>5} | {'vPRE':>5} {'PRE.L0':>6} {'PRE.band':>8} | "
           f"{'vPOST':>5} {'PO.L0':>6} {'PO.fix':>7} {'PO.band':>8} {'PO.best':>8} | "
           f"{'band-v':>7}")
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for cell, model, domain in CELLS:
        jp = root / cell / "temporal_analysis.json"
        if not jp.exists():
            print(f"{cell:<22}  (no temporal_analysis.json)")
            continue
        j = json.loads(jp.read_text())
        lc = j.get("layer_curves", {})
        vpre, vpost = j.get("pre_auroc"), j.get("post_auroc")
        pre0, preb, pref, preband = readout(lc.get("prompt_dtoken", []))   # CLEAN pre (bug-free)
        po0, pob, pof, poband = readout(lc.get("post_dtoken", []))
        gap = poband - vpost if (vpost is not None and not np.isnan(poband)) else float("nan")
        rows.append(dict(cell=cell, model=model, domain=domain, pass_rate=j.get("pass_rate"),
                         vpost=vpost, po_band=poband, po_best=pob, gap=gap))
        f = lambda x: "  nan" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"
        print(f"{cell:<22} {j.get('pass_rate', float('nan')):>5.2f} | "
              f"{f(vpre):>5} {f(pre0):>6} {f(preband):>8} | "
              f"{f(vpost):>5} {f(po0):>6} {f(pof):>7} {f(poband):>8} {f(pob):>8} | {f(gap):>7}")

    # summary: does internal (band) beat verbalized POST, and by how much, per domain?
    print("\n=== internal(POST band) - verbalized(POST), by domain ===")
    for dom in ["geometry", "mmlu_pro", "gsm8k", "math"]:
        gs = [r["gap"] for r in rows if r["domain"] == dom and not np.isnan(r["gap"])]
        if gs:
            print(f"  {dom:<10}: mean +{np.mean(gs):.3f}   (per-model: "
                  + ", ".join(f"{r['model']} +{r['gap']:.2f}" for r in rows if r['domain'] == dom) + ")")
    allgaps = [r["gap"] for r in rows if not np.isnan(r["gap"])]
    n_pos = sum(1 for g in allgaps if g > 0)
    print(f"\n  internal band-mean beats verbalized POST in {n_pos}/{len(allgaps)} cells; "
          f"mean gap +{np.mean(allgaps):.3f}")
    # read-site control
    l0 = [readout(json.loads((root / c / 'temporal_analysis.json').read_text())
                  .get('layer_curves', {}).get('post_dtoken', []))[0]
          for c, _, _ in CELLS if (root / c / 'temporal_analysis.json').exists()]
    l0 = [x for x in l0 if not np.isnan(x)]
    print(f"  read-site control: POST layer-0 AUROC mean {np.mean(l0):.3f} "
          f"(range {min(l0):.2f}-{max(l0):.2f})  — should be ~0.5")


if __name__ == "__main__":
    main()
