"""The temporal series: where in the forward pass does correctness become readable?

Runs the SAME probe pipeline at four sites on the SAME records, in the order the model
passes through them:

  1. before_solving   last prompt token of the bare question, no elicitation at all
  2. prospective      the turn-1 "how likely am I to get this right" digit
  3. answer_end       the final token of the attempt itself      <- the missing one
  4. retrospective    the turn-3 "was that right" digit

Sites 1, 2 and 4 are already in every fix_* capture (prompt_dtoken, pre_dtoken,
post_dtoken). Site 3 comes from capture_answer_site.py. The point of the series: if
correctness is decodable at site 3, before the model is asked anything metacognitive,
that is knowing *before* saying in the literal sense, and much harder to dismiss as
self-evaluation elicited by the confidence prompt.

Also reports:
  - a within-answer trajectory (AUROC at evenly spaced positions across the attempt),
    locating where in the attempt the signal appears
  - cross-site transfer and direction cosine between sites 3 and 4, testing whether the
    retrospective read is the same signal read later or a different one
  - site-3 AUROC after residualizing on answer log-probability and answer length
  - per-record out-of-fold scores at every site

Sanity check: site 4 should reproduce the AUROC already reported for the cell (Mistral
x MATH = 0.834). A mismatch means this pipeline differs from tier1_review.py and the
comparison is not trustworthy.

Usage:
  python -m interp.analysis.answer_site_probe \
      --answer-dir interp/activations/ansite_mistral_math \
      --conf-dir   interp/activations/fix_mistral_math \
      --out interp/results/temporal_sites_mistral_math.json
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

FIXED_DEPTH = 0.7


def _layer_slot(layer_ids) -> int:
    return int(round(FIXED_DEPTH * (len(layer_ids) - 1)))


def _load(act_dir: pathlib.Path, key: str, traj: bool = False):
    """Return dict pid -> (vector at the fixed layer, meta row). `traj` keeps [K, D]."""
    meta = {}
    with (act_dir / "meta.jsonl").open() as f:
        for line in f:
            r = json.loads(line)
            meta[r["pid"]] = r
    out = {}
    for npz_path in sorted(act_dir.glob("*.npz")):
        pid = npz_path.stem
        if pid not in meta:
            continue
        d = np.load(npz_path)
        if key not in d:
            continue
        li = _layer_slot(list(d["layer_ids"]))
        a = d[key]
        out[pid] = (a[li].astype(np.float32), meta[pid])
    return out


def _xy(store, pids):
    X = np.stack([store[p][0] for p in pids])
    y = np.array([1 if store[p][1]["grade"]["ok"] else 0 for p in pids])
    g = np.array([p.split("_s")[0] for p in pids])
    return X, y, g


def _oof(X, y, groups, seed=0, return_dirs=False):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    scores = np.zeros(len(y), float)
    dirs = []
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        pipe = make_pipeline(StandardScaler(),
                             PCA(n_components=min(50, len(tr) - 1, X.shape[1])),
                             LogisticRegression(max_iter=2000, random_state=seed))
        pipe.fit(X[tr], y[tr])
        scores[te] = pipe.predict_proba(X[te])[:, 1]
        if return_dirs:
            pca = pipe.named_steps["pca"]
            coef = pipe.named_steps["logisticregression"].coef_[0]
            dirs.append(coef @ pca.components_)          # back to input space
    return (scores, np.mean(dirs, axis=0)) if return_dirs else scores


def _auroc(s, y):
    from sklearn.metrics import roc_auc_score
    return float("nan") if len(set(y.tolist())) < 2 else float(roc_auc_score(y, s))


def _boot_ci(s, y, n=2000, seed=0):
    rng = np.random.default_rng(seed)
    vals = []
    idx = np.arange(len(y))
    for _ in range(n):
        b = rng.choice(idx, len(idx), replace=True)
        if len(set(y[b].tolist())) < 2:
            continue
        vals.append(_auroc(s[b], y[b]))
    if not vals:
        return [float("nan")] * 2
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def _residualize(s, covariates):
    from sklearn.linear_model import LinearRegression
    C = np.column_stack(covariates)
    keep = np.isfinite(C).all(1)
    out = s.copy()
    if keep.sum() > 10:
        lr = LinearRegression().fit(C[keep], s[keep])
        out[keep] = s[keep] - lr.predict(C[keep])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer-dir", required=True, help="cell from capture_answer_site.py")
    ap.add_argument("--conf-dir", required=True, help="the original fix_* cell")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-traj", action="store_true", help="skip the within-answer trajectory")
    args = ap.parse_args()

    conf_dir, ans_dir = pathlib.Path(args.conf_dir), pathlib.Path(args.answer_dir)
    sites = {
        "before_solving": _load(conf_dir, "prompt_dtoken"),
        "prospective": _load(conf_dir, "pre_dtoken"),
        "answer_end": _load(ans_dir, "answer_last"),
        "retrospective": _load(conf_dir, "post_dtoken"),
    }
    common = sorted(set.intersection(*(set(v) for v in sites.values())))
    print(f"{len(common)} records present at all four sites")
    if len(common) < 50:
        raise SystemExit("too few shared records — check that both cells cover the same pids")

    report = {"n_common": len(common), "fixed_depth": FIXED_DEPTH, "sites": {}}
    per_record, dirs = {}, {}
    for name, store in sites.items():
        X, y, g = _xy(store, common)
        s, w = _oof(X, y, g, return_dirs=True)
        dirs[name] = w
        per_record[name] = {p: float(v) for p, v in zip(common, s)}
        report["sites"][name] = {"auroc": _auroc(s, y), "ci95": _boot_ci(s, y)}
        lo, hi = report["sites"][name]["ci95"]
        print(f"  {name:>15}: AUROC={report['sites'][name]['auroc']:.3f}  [{lo:.3f}, {hi:.3f}]")

    print("  (retrospective should land near 0.834 on Mistral x MATH; if not, this "
          "pipeline differs from tier1_review.py)")

    # is the retrospective read the same signal, read later?
    a, b = dirs["answer_end"], dirs["retrospective"]
    report["answer_vs_retrospective_cosine"] = float(
        a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    print(f"  cosine(answer_end, retrospective) = {report['answer_vs_retrospective_cosine']:.3f}")

    # does the attempt-site signal survive the obvious text-level confounds?
    ans_meta = [sites["answer_end"][p][1] for p in common]
    logp = np.array([m.get("mean_logp_answer") if m.get("mean_logp_answer") is not None
                     else np.nan for m in ans_meta], float)
    length = np.array([m.get("n_answer_tokens", np.nan) for m in ans_meta], float)
    _, y_all, _ = _xy(sites["answer_end"], common)
    s_ans = np.array([per_record["answer_end"][p] for p in common])
    s_res = _residualize(s_ans, [logp, length])
    report["answer_end_residualized"] = {
        "auroc": _auroc(s_res, y_all),
        "covariates": ["mean_logp_answer", "n_answer_tokens"],
    }
    print(f"  answer_end residualized on log-prob + length: "
          f"AUROC={report['answer_end_residualized']['auroc']:.3f}")

    # where inside the attempt does it appear?
    if not args.no_traj:
        traj = []
        metas = {}
        with (ans_dir / "meta.jsonl").open() as f:
            for line in f:
                r = json.loads(line)
                metas[r["pid"]] = r
        arrays, fracs = {}, None
        for pid in common:
            d = np.load(ans_dir / f"{pid}.npz")
            if "answer_traj" not in d:
                arrays = {}
                break
            li = _layer_slot(list(d["layer_ids"]))
            arrays[pid] = d["answer_traj"][li].astype(np.float32)   # [K, D]
            fracs = d["traj_frac"]
        if arrays:
            K = min(v.shape[0] for v in arrays.values())
            for k in range(K):
                Xk = np.stack([arrays[p][k] for p in common])
                _, yk, gk = _xy(sites["answer_end"], common)
                sk = _oof(Xk, yk, gk)
                traj.append({"k": k, "frac": float(fracs[k]) if fracs is not None else None,
                             "auroc": _auroc(sk, yk)})
                print(f"    traj k={k} frac={traj[-1]['frac']} AUROC={traj[-1]['auroc']:.3f}")
            report["within_answer_trajectory"] = traj

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**report, "per_record": per_record}, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
