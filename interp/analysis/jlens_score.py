#!/usr/bin/env python
"""Offline half of the J-lens adapter (task #16): score our SAVED decision-token
activations with the word-readout vectors extracted by interp/jlens_fit.py, and race
the zero-shot J-lens readout against the supervised probe / P(True) / verbalized on
the exact same records.

The readout: r_{w,l} = J_lᵀ u_w (built on the box) makes "disposed to say w later"
a single dot product per record:  score_w = r_{w,l} · h.  Our failure signal is
    jl = mean(fail-word scores) - mean(success-word scores)
(higher = drifting toward saying "wrong"/"error" => predicts an incorrect answer).
Secondary: a digit-weighted stated-confidence expectation from the '0'..'9' rows.

Interpretation guide (global-workspace framing):
  jl ~= probe        -> the correctness signal IS in the verbalizable channel (suppression story)
  jl ~= chance << probe -> knowledge exists but never enters the workspace (access story)
  split by domain    -> the knowing-vs-saying gap IS workspace entry (headline)

    interp/.venv/bin/python interp/analysis/jlens_score.py \
        --readouts interp/activations/jlens/jlens_readouts_mistral.npz \
        --cells fix_mistral_mmlu_pro fix_mistral_math fix_mistral_gpqa
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tier1_review import load_cell, oof_scores, _auroc, within_q  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readouts", required=True, help="jlens_readouts_<short>.npz from jlens_fit.py")
    ap.add_argument("--cells", nargs="+", required=True)
    ap.add_argument("--act-root", default="interp/activations")
    ap.add_argument("--site", choices=("post", "prompt"), default="post",
                    help="post = post-confidence decision token; prompt = clean pre-task read")
    args = ap.parse_args()

    z = np.load(args.readouts, allow_pickle=True)
    R, words = z["R"], [str(w) for w in z["words"]]          # [W, L, D]
    n_fail, n_ok = int(z["n_fail"]), int(z["n_ok"])
    W, L, D = R.shape
    fail_R = R[:n_fail].mean(0)                              # [L, D]
    ok_R = R[n_fail:n_fail + n_ok].mean(0)
    dig_R = R[n_fail + n_ok:]                                # [10, L, D]
    idx = {"0": 0, "e": int(round(0.15 * (L - 1))), "f": int(round(0.7 * (L - 1)))}
    print(f"readouts: {args.readouts} | {W} words x {L} layers x d={D} | "
          f"corpus={z['corpus']} | site={args.site}")

    results = {}
    for cell in args.cells:
        d = pathlib.Path(args.act_root) / cell
        if not (d / "meta.jsonl").exists():
            print(f"{cell}: missing — skip")
            continue
        meta, arr = load_cell(d)
        key = "q" if args.site == "post" else "p"
        if arr[f"{key}f"].shape[1] != D:
            print(f"{cell}: dim mismatch (cell d={arr[f'{key}f'].shape[1]} vs readout d={D}) "
                  f"— wrong model's readouts; skip")
            continue
        y = np.array([1 if r["grade"]["ok"] else 0 for r in meta])
        g = np.array([re.sub(r"_s\d+$", "", r["pid"]) for r in meta])
        pt = np.array([r.get("p_true") if r.get("p_true") is not None else np.nan
                       for r in meta], float)
        vc = np.array([r["post_conf"] if r.get("post_conf") is not None else np.nan
                       for r in meta], float)

        row = {}
        for lk, li in idx.items():
            h = np.nan_to_num(np.asarray(arr[f"{key}{lk}"], np.float32))
            jl = h @ fail_R[li] - h @ ok_R[li]                # failure-disposition
            has = ~np.isnan(np.asarray(arr[f"{key}{lk}"], np.float32)[:, 0])
            row[f"jlens_auroc_L{lk}"] = _auroc(-jl[has], y[has])   # -jl predicts ok
            if lk == "f":
                jlf, hasf = jl, has
        # digit-expectation readout (stated-confidence proxy, zero elicitation)
        hf = np.nan_to_num(np.asarray(arr[f"{key}f"], np.float32))
        dscore = hf @ dig_R[:, idx["f"], :].T                 # [N, 10]
        p = np.exp(dscore - dscore.max(1, keepdims=True)); p /= p.sum(1, keepdims=True)
        dconf = p @ np.arange(10)
        row["digit_conf_auroc"] = _auroc(dconf[hasf], y[hasf])

        # the race on identical records
        Xf = np.asarray(arr[f"{key}f"], np.float32)
        m = hasf & ~np.isnan(pt) & ~np.isnan(vc)
        s, _ = oof_scores(np.nan_to_num(Xf[m]), y[m], g[m])
        ok_s = ~np.isnan(s)
        row.update(n=int(m.sum()), pass_rate=float(y[m].mean()),
                   verbalized=_auroc(vc[m][ok_s], y[m][ok_s]),
                   probe=_auroc(s[ok_s], y[m][ok_s]),
                   p_true=_auroc(pt[m][ok_s], y[m][ok_s]),
                   jlens=_auroc(-jlf[m][ok_s], y[m][ok_s]))
        wq_j, nq = within_q(-jlf[m][ok_s], y[m][ok_s], g[m][ok_s])
        wq_p, _ = within_q(s[ok_s], y[m][ok_s], g[m][ok_s])
        row.update(within_q_jlens=wq_j, within_q_probe=wq_p, n_mixed=nq)
        results[cell] = row
        f3 = lambda x: "  nan" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"
        print(f"\n--- {cell} (n={row['n']}, pass={row['pass_rate']:.2f}) ---")
        print(f"  RACE      : verbalized={f3(row['verbalized'])}  probe={f3(row['probe'])}  "
              f"P(True)={f3(row['p_true'])}  JLENS={f3(row['jlens'])}")
        print(f"  jlens/layer: L0={f3(row['jlens_auroc_L0'])}  early={f3(row['jlens_auroc_Le'])}  "
              f"fix={f3(row['jlens_auroc_Lf'])}   digit-conf={f3(row['digit_conf_auroc'])}")
        print(f"  within-q  : jlens={f3(wq_j)}  probe={f3(wq_p)}  (n_mixed={nq})")

    outp = pathlib.Path(args.act_root) / "jlens_score.json"
    outp.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nsaved {outp}")


if __name__ == "__main__":
    main()
