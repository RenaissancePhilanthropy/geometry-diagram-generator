"""
Temporal confidence analysis — evaluate a 3-turn (pre-task / task / post-task)
capture from interp/capture_temporal.py.

Answers, in order:
  1. Dataset & outcome spread (calibration only means something if success varies).
  2. Verbalized CALIBRATION, pre vs post — reliability curve (do low-confidence
     ones fail?), AUROC, ECE, Brier. Headline: is POST better calibrated than PRE?
  3. The UPDATE (post - pre) — does the model revise DOWN on failures? (self-correction)
  4. SELECTIVE PREDICTION — abstain on low confidence, measure success on the rest.
  5. INTERNAL probes — decode ok/fail from the residual stream at the pre-task
     (no-elicitation) / pre / post read sites; does internal beat the stated number,
     and is there an EARLY (pre-task) usable signal?
  6. WITHIN-PROMPT post calibration (difficulty held fixed) — genuine self-monitoring.

    interp/.venv/bin/python interp/analysis/confidence_temporal.py --act-dir interp/activations/qwen36_temporal
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import warnings

import numpy as np

warnings.filterwarnings("ignore")


def _auroc(scores, y):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return float("nan")
    return float(roc_auc_score(y, scores))


def _auroc_ci(scores, y, n_boot=1000, seed=0):
    """AUROC + bootstrap 95% CI (resample items)."""
    y = np.asarray(y)
    scores = np.asarray(scores)
    base = _auroc(scores, y)
    if np.isnan(base):
        return base, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n = len(y)
    b = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if len(set(y[idx].tolist())) == 2:
            b.append(_auroc(scores[idx], y[idx]))
    if not b:
        return base, float("nan"), float("nan")
    return base, float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def _ece(conf01, y, bins=10):
    conf01 = np.asarray(conf01, float); y = np.asarray(y, float)
    edges = np.linspace(0, 1, bins + 1)
    e, n = 0.0, len(y)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf01 >= lo) & (conf01 < hi if hi < 1 else conf01 <= hi)
        if m.sum():
            e += m.sum() / n * abs(y[m].mean() - conf01[m].mean())
    return float(e)


def _reliability(conf, y, bins=(0, 20, 40, 60, 80, 95, 101)):
    conf = np.asarray(conf, float); y = np.asarray(y, float)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf >= lo) & (conf < hi)
        if m.sum():
            rows.append((f"{lo:>3}-{hi-1:<3}", int(m.sum()), round(float(y[m].mean()), 2),
                         round(float(conf[m].mean()), 1)))
    return rows


def _risk_coverage(conf, y, cov=(1.0, 0.8, 0.6, 0.4, 0.2)):
    """Keep the top-`c` fraction by confidence (abstain on the lowest); success on kept."""
    conf = np.asarray(conf, float); y = np.asarray(y, float)
    order = np.argsort(-conf)
    out = []
    for c in cov:
        k = max(1, int(round(c * len(y))))
        out.append((c, round(float(y[order[:k]].mean()), 3), k))
    return out


def _oof_probe(X, y, groups, pca=50):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return float("nan")
    ns = min(5, len(set(groups)))
    if ns < 2:
        return float("nan")
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(ns).split(X, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        k = min(pca, len(tr) - 1, X.shape[1])
        p = make_pipeline(StandardScaler(), PCA(k, random_state=0),
                          LogisticRegression(max_iter=2000)).fit(X[tr], y[tr])
        oof[te] = p.decision_function(X[te])
    m = ~np.isnan(oof)
    return _auroc(oof[m], y[m]) if m.sum() else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", default="interp/activations/qwen36_temporal")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    D = pathlib.Path(args.act_dir)

    recs = [json.loads(l) for l in (D / "meta.jsonl").read_text().splitlines()]
    base = lambda pid: re.sub(r"_s\d+$", "", pid)
    for r in recs:
        r["ok"] = 1 if r["grade"]["ok"] else 0
        r["base"] = base(r["pid"])

    n = len(recs)
    ok = np.array([r["ok"] for r in recs])
    print(f"=== dataset: {n} records, {len(set(r['base'] for r in recs))} unique prompts, "
          f"pass rate {ok.mean():.2f} ===")
    stages = {}
    for r in recs:
        stages[r["grade"]["stage"]] = stages.get(r["grade"]["stage"], 0) + 1
    print("  stages:", stages)

    def col(key):
        return np.array([(r[key] if r[key] is not None else np.nan) for r in recs], float)

    pre, post = col("pre_conf"), col("post_conf")
    have = ~np.isnan(pre) & ~np.isnan(post)
    pre_v, post_v, ok_v = pre[have], post[have], ok[have]
    print(f"  with both confidences: {have.sum()} | pre mean {np.nanmean(pre_v):.0f} "
          f"post mean {np.nanmean(post_v):.0f}")

    # 2. calibration -------------------------------------------------------
    print("\n=== 2. VERBALIZED CALIBRATION (does low confidence predict failure?) ===")
    # surface control: a trivial answer/construction-length feature — confidence must beat it
    lens = np.array([len((r.get("answer") or r.get("construction") or "")) for r in recs], float)[have]
    sa, slo, shi = _auroc_ci(lens, ok_v)
    print(f"  SURFACE (answer length): AUROC={sa:.3f} [{slo:.3f},{shi:.3f}]  <- confidence must clear this")
    for name, c in [("PRE ", pre_v), ("POST", post_v)]:
        a, lo, hi = _auroc_ci(c, ok_v)
        print(f"  {name}: AUROC={a:.3f} [95% CI {lo:.3f},{hi:.3f}]  "
              f"ECE={_ece(c/100, ok_v):.3f}  Brier={np.mean((c/100 - ok_v)**2):.3f}")
        for lab, cnt, acc, mc in _reliability(c, ok_v):
            print(f"      conf {lab}: n={cnt:>3}  success={acc:.2f}  (mean conf {mc})")

    # 3. the update --------------------------------------------------------
    print("\n=== 3. THE UPDATE (post - pre): does the model revise DOWN on failures? ===")
    delta = post_v - pre_v
    print(f"  mean delta | ok: {delta[ok_v==1].mean():+.1f}   fail: {delta[ok_v==0].mean():+.1f}")
    print(f"  AUROC(downward revision -> failure): {_auroc(-delta, 1 - ok_v):.3f}")

    # 4. selective prediction ---------------------------------------------
    print("\n=== 4. SELECTIVE PREDICTION (abstain on lowest confidence -> success on the rest) ===")
    for name, c in [("PRE ", pre_v), ("POST", post_v)]:
        rc = _risk_coverage(c, ok_v)
        print(f"  {name}: " + "  ".join(f"cov{int(cv*100)}%={acc}" for cv, acc, _ in rc))

    # 5. internal probes ---------------------------------------------------
    print("\n=== 5. INTERNAL PROBES (residual stream vs the stated number) ===")
    sites = {"prompt_dtoken": "PRE (no elicitation)", "pre_dtoken": "PRE (elicited)",
             "post_dtoken": "POST"}
    site_curves = {}
    for key, label in sites.items():
        Xs, ys, gs = [], [], []
        for r in recs:
            f = D / f"{r['pid']}.npz"
            if not f.exists():
                continue
            z = np.load(f)
            if key not in z:
                continue
            Xs.append(z[key])            # [L, Dm]
            ys.append(r["ok"]); gs.append(r["base"])
        if len(Xs) < 20:
            print(f"  {label}: (only {len(Xs)} records with {key}; skip)")
            continue
        A = np.stack(Xs)                 # [N, L, Dm]
        y = np.array(ys); g = np.array(gs)
        curve = [_oof_probe(A[:, L, :], y, g) for L in range(A.shape[1])]  # per-layer AUROC
        site_curves[key] = curve
        bL = int(np.nanargmax(curve)); bA = curve[bL]
        vname = "pre_conf" if "PRE" in label else "post_conf"
        vc = col(vname); vmask = ~np.isnan(vc)
        vA = _auroc(vc[vmask], ok[vmask])
        print(f"  {label}: internal best AUROC={bA:.3f} (layer {bL}/{A.shape[1]-1})"
              f"  vs verbalized {vname}={vA:.3f}  [{len(Xs)} records]")

    # 6. within-prompt post calibration -----------------------------------
    print("\n=== 6. WITHIN-PROMPT post calibration (difficulty fixed) ===")
    from collections import defaultdict
    byp = defaultdict(list)
    for i in np.where(have)[0]:
        byp[recs[i]["base"]].append((post[i], ok[i]))
    diffs = []
    for p, rows in byp.items():
        outs = set(o for _, o in rows)
        if len(outs) == 2:               # mixed-outcome prompt
            cs = [c for c, _ in rows]; os = [o for _, o in rows]
            diffs.append(_auroc(cs, os))
    diffs = [d for d in diffs if not np.isnan(d)]
    if diffs:
        print(f"  mixed-outcome prompts: {len(diffs)} | mean within-prompt AUROC(post->ok): "
              f"{np.mean(diffs):.3f}")
    else:
        print("  (no mixed-outcome prompts yet — need more samples/prompts)")

    out = args.out or str(D / "temporal_analysis.json")
    pathlib.Path(out).write_text(json.dumps({
        "n": n, "pass_rate": float(ok.mean()),
        "pre_auroc": _auroc(pre_v, ok_v), "post_auroc": _auroc(post_v, ok_v),
        "delta_ok": float(delta[ok_v == 1].mean()) if (ok_v == 1).any() else None,
        "delta_fail": float(delta[ok_v == 0].mean()) if (ok_v == 0).any() else None,
        "layer_curves": {k: [None if np.isnan(a) else round(float(a), 3) for a in v]
                         for k, v in site_curves.items()},
    }, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
