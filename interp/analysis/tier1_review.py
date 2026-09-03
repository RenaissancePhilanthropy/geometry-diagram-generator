#!/usr/bin/env python
r"""Tier-1 offline analyses from the 2026-07-07 expert review — no GPU, runs entirely on
the already-captured matrix (12 QA cells + 4 geometry temporal runs).

Per cell (site reads: prompt_dtoken = clean no-elicitation PRE, post_dtoken = POST;
fixed a-priori layer = 0.7 * depth, early = 0.15 * depth):

  SURFACE    incremental-validity control the matrix never had: grouped-OOF AUROC of
             surface-features-only vs activation-only vs surface+activation. Also the
             early-layer probe, to diagnose the early-peak cells (does early = surface?).
  DECOMP     residualize OOF post-scores on OOF pre-scores; the residual is the
             attempt-specific component. Within-question AUROC of the INTERNAL post
             score and of the residual (verbalized within-q as reference).
  SELECTIVE  risk-coverage: abstain on lowest-confidence; internal OOF score vs
             verbalized post_conf.
  STATS      paired bootstrap on AUROC(internal) - AUROC(verbalized); layer-0
             pooled-vs-per-fold AUROC (is the 0.39 layer-0 reading a fold-pooling
             artifact rather than a leak?).

Per model (within model only — hidden dims differ across models):

  TRANSFER   cross-domain probe transfer at the fixed layer: train on domain A's
             post-site activations (per-domain standardization), test on domain B.
             Diagonal = grouped-OOF in-domain. Plus diff-of-means direction cosines
             and a cross-SITE transfer (train POST -> test clean-PRE, held-out groups):
             is there ONE domain-general / time-general correctness direction?

Caches per-cell layer slices to <cell>/tier1_cache.npz (delete to rebuild). Saves
interp/activations/tier1_review.json.

    interp/.venv/bin/python interp/analysis/tier1_review.py [--cells mtx_gemma4_math ...]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import warnings
from collections import defaultdict

import numpy as np

warnings.filterwarnings("ignore")

MODELS = ["gemma4", "qwen36", "glm", "mistral"]
QA = ["mmlu_pro", "gsm8k", "math", "gpqa"]
CELLS = [(f"mtx_{m}_{b}", m, b) for m in MODELS for b in QA] + \
        [(f"{m}_temporal", m, "geometry") for m in MODELS]
COVS = (1.0, 0.8, 0.6, 0.4, 0.2)


def _auroc(scores, y):
    from sklearn.metrics import roc_auc_score
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return float("nan")
    return float(roc_auc_score(y, scores))


def _pipe(k):
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    return make_pipeline(StandardScaler(), PCA(k, random_state=0),
                         LogisticRegression(max_iter=2000))


def oof_scores(X, y, groups, pca=50, folds=5):
    """Grouped out-of-fold decision scores + fold ids (-1 = unscored)."""
    from sklearn.model_selection import GroupKFold
    X = np.asarray(X, np.float32); y = np.asarray(y)
    scores = np.full(len(y), np.nan); fold = np.full(len(y), -1)
    ns = min(folds, len(set(groups.tolist())))
    if ns < 2 or len(set(y.tolist())) < 2:
        return scores, fold
    for fi, (tr, te) in enumerate(GroupKFold(ns).split(X, y, groups)):
        if len(set(y[tr].tolist())) < 2:
            continue
        k = min(pca, len(tr) - 1, X.shape[1])
        p = _pipe(k).fit(X[tr], y[tr])
        scores[te] = p.decision_function(X[te]); fold[te] = fi
    return scores, fold


def oof_surf_act(Xact, S, y, groups, pca=50, folds=5):
    """Grouped-OOF scores for surface-only and surface+activation (concat after
    per-fold scaling/PCA)."""
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    Xact = np.asarray(Xact, np.float32); S = np.asarray(S, np.float32); y = np.asarray(y)
    s_surf = np.full(len(y), np.nan); s_both = np.full(len(y), np.nan)
    ns = min(folds, len(set(groups.tolist())))
    if ns < 2 or len(set(y.tolist())) < 2:
        return s_surf, s_both
    for tr, te in GroupKFold(ns).split(Xact, y, groups):
        if len(set(y[tr].tolist())) < 2:
            continue
        ss = StandardScaler().fit(S[tr])
        lr = LogisticRegression(max_iter=2000).fit(ss.transform(S[tr]), y[tr])
        s_surf[te] = lr.decision_function(ss.transform(S[te]))
        sx = StandardScaler().fit(Xact[tr])
        k = min(pca, len(tr) - 1, Xact.shape[1])
        pc = PCA(k, random_state=0).fit(sx.transform(Xact[tr]))
        Ztr = np.hstack([pc.transform(sx.transform(Xact[tr])), ss.transform(S[tr])])
        Zte = np.hstack([pc.transform(sx.transform(Xact[te])), ss.transform(S[te])])
        lr2 = LogisticRegression(max_iter=2000).fit(Ztr, y[tr])
        s_both[te] = lr2.decision_function(Zte)
    return s_surf, s_both


def per_fold_auroc(scores, fold, y):
    """Mean AUROC computed *within* each fold's test set (kills the fold-pooling
    offset artifact that can drag a pooled OOF AUROC off 0.5)."""
    out = []
    for fi in sorted(set(fold.tolist())):
        if fi < 0:
            continue
        m = fold == fi
        a = _auroc(scores[m], y[m])
        if not np.isnan(a):
            out.append(a)
    return float(np.mean(out)) if out else float("nan")


def within_q(scores, y, groups):
    per = defaultdict(list)
    for s, yy, g in zip(scores, y, groups):
        if not np.isnan(s):
            per[g].append((s, yy))
    aucs = [a for rows in per.values() if len({r[1] for r in rows}) == 2
            for a in [_auroc([r[0] for r in rows], [r[1] for r in rows])] if not np.isnan(a)]
    return (float(np.mean(aucs)), len(aucs)) if aucs else (float("nan"), 0)


def risk_cov(scores, y):
    order = np.argsort(-np.asarray(scores))
    return {c: float(np.mean(np.asarray(y)[order[:max(1, int(round(c * len(y))))]]))
            for c in COVS}


def paired_boot(si, sv, y, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    si, sv, y = map(np.asarray, (si, sv, y))
    d = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if len(set(y[idx].tolist())) == 2:
            d.append(_auroc(si[idx], y[idx]) - _auroc(sv[idx], y[idx]))
    return (float(np.mean(d)), float(np.percentile(d, 2.5)),
            float(np.percentile(d, 97.5))) if d else (float("nan"),) * 3


def surface_feats(meta):
    """Compile-independent surface features of the in-context answer. NOTE: QA answers
    are stored truncated to 200 chars (capture_qa), so length is right-censored — a
    weaker control than geometry's full-text; flagged in the report."""
    out = []
    for r in meta:
        t = r.get("answer") or r.get("construction") or ""
        out.append([len(t), sum(c.isdigit() for c in t), t.count("\n"),
                    len(t.split()), t.count("{")])
    return np.array(out, np.float32)


def load_cell(d: pathlib.Path, rebuild=False):
    """Aligned (meta, arrays) for one cell; caches the 3-layer slices."""
    meta_all = [json.loads(l) for l in (d / "meta.jsonl").read_text().splitlines()]
    meta = [r for r in meta_all if (d / f"{r['pid']}.npz").exists()]
    cache = d / "tier1_cache.npz"
    if cache.exists() and not rebuild:
        z = np.load(cache)
        if int(z["n"]) == len(meta):
            return meta, {k: z[k] for k in z.files if k != "n"}
    first = np.load(d / f"{meta[0]['pid']}.npz")
    L = first["prompt_dtoken"].shape[0]
    idx = {"0": 0, "e": int(round(0.15 * (L - 1))), "f": int(round(0.7 * (L - 1)))}
    Dm = first["prompt_dtoken"].shape[1]
    arr = {f"{s}{k}": np.full((len(meta), Dm), np.nan, np.float16)
           for s in ("p", "q") for k in idx}          # p = prompt (clean PRE), q = post
    for i, r in enumerate(meta):
        z = np.load(d / f"{r['pid']}.npz")
        for k, li in idx.items():
            arr[f"p{k}"][i] = z["prompt_dtoken"][li]
            if "post_dtoken" in z:
                arr[f"q{k}"][i] = z["post_dtoken"][li]
        if i % 200 == 0:
            print(f"    ..{d.name} {i}/{len(meta)}", flush=True)
    np.savez_compressed(cache, n=len(meta), **arr)
    return meta, arr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-root", default="interp/activations")
    ap.add_argument("--cells", nargs="*", default=None, help="restrict to these cell dirs")
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()
    root = pathlib.Path(args.act_root)

    results = {"cells": {}, "transfer": {}}
    permodel = defaultdict(dict)                       # model -> domain -> (Xf, y, g, diag)

    print("=" * 100)
    print("TIER-1 PER-CELL: surface-incremental | decomposition/within-q | selective | stats")
    print("=" * 100)
    for cell, model, domain in CELLS:
        if args.cells and cell not in args.cells:
            continue
        d = root / cell
        if not (d / "meta.jsonl").exists():
            print(f"{cell}: missing — skip")
            continue
        meta, arr = load_cell(d, args.rebuild_cache)
        y = np.array([1 if r["grade"]["ok"] else 0 for r in meta])
        g = np.array([re.sub(r"_s\d+$", "", r["pid"]) for r in meta])
        pconf = np.array([r["post_conf"] if r["post_conf"] is not None else np.nan
                          for r in meta], float)
        S = surface_feats(meta)
        hasq = ~np.isnan(arr["qf"][:, 0])
        r = {"n": len(meta), "pass": float(y.mean())}

        # OOF scores at the sites/layers everything below reuses
        s_pre, f_pre = oof_scores(arr["pf"], y, g)                       # clean PRE, fix layer
        s_post, f_post = oof_scores(arr["qf"][hasq], y[hasq], g[hasq])   # POST, fix layer
        s_post_e, _ = oof_scores(arr["qe"][hasq], y[hasq], g[hasq])     # POST, early layer
        s_post_0, f_post_0 = oof_scores(arr["q0"][hasq], y[hasq], g[hasq])  # POST, layer 0

        # 2. surface-incremental
        s_surf, s_both = oof_surf_act(arr["qf"][hasq], S[hasq], y[hasq], g[hasq])
        vs = ~np.isnan(s_surf)
        a = {"surf": _auroc(s_surf[vs], y[hasq][vs]),
             "act": _auroc(s_post[vs], y[hasq][vs]),
             "act_early": _auroc(s_post_e[vs], y[hasq][vs]),
             "both": _auroc(s_both[vs], y[hasq][vs])}
        a["increment"] = a["both"] - a["surf"]
        r["surface"] = a

        # 3. decomposition + within-question INTERNAL
        both_m = hasq.copy()
        sp_full = np.full(len(meta), np.nan); sp_full[hasq] = s_post
        vm = both_m & ~np.isnan(s_pre) & ~np.isnan(sp_full)
        if vm.sum() > 20:
            b = np.polyfit(s_pre[vm], sp_full[vm], 1)
            resid = sp_full[vm] - np.polyval(b, s_pre[vm])
            wq_int, nq1 = within_q(sp_full[vm], y[vm], g[vm])
            wq_res, _ = within_q(resid, y[vm], g[vm])
            cm = vm & ~np.isnan(pconf)
            wq_verb, nq2 = within_q(pconf[cm], y[cm], g[cm])
            r["decomp"] = {"auroc_pre_internal": _auroc(s_pre[vm], y[vm]),
                           "auroc_post_internal": _auroc(sp_full[vm], y[vm]),
                           "auroc_resid": _auroc(resid, y[vm]),
                           "within_q_internal": wq_int, "within_q_resid": wq_res,
                           "within_q_verbalized": wq_verb, "n_mixed": nq1}

        # 4. selective prediction (records with both internal score + verbalized)
        sm = vm & ~np.isnan(pconf)
        if sm.sum() > 20:
            r["selective"] = {"internal": risk_cov(sp_full[sm], y[sm]),
                              "verbalized": risk_cov(pconf[sm], y[sm])}

        # 5. stats: paired bootstrap + layer-0 pooling diagnosis
        if sm.sum() > 20:
            mb, lo, hi = paired_boot(sp_full[sm], pconf[sm], y[sm])
            r["boot_int_minus_verb"] = {"mean": mb, "lo": lo, "hi": hi,
                                        "significant": bool(lo > 0)}
        r["layer0"] = {"pooled": _auroc(s_post_0[~np.isnan(s_post_0)],
                                        y[hasq][~np.isnan(s_post_0)]),
                       "per_fold": per_fold_auroc(s_post_0, f_post_0, y[hasq]),
                       "fix_pooled": _auroc(s_post[~np.isnan(s_post)],
                                            y[hasq][~np.isnan(s_post)]),
                       "fix_per_fold": per_fold_auroc(s_post, f_post, y[hasq])}

        results["cells"][cell] = r
        permodel[model][domain] = (np.asarray(arr["qf"][hasq], np.float32), y[hasq], g[hasq],
                                   r["layer0"]["fix_pooled"],
                                   np.asarray(arr["pf"], np.float32), y, g)

        f3 = lambda x: "  nan" if x is None or np.isnan(x) else f"{x:.3f}"
        print(f"\n--- {cell}  (n={r['n']}, pass={r['pass']:.2f}) ---")
        print(f"  surface: surf-only={f3(a['surf'])}  act-only={f3(a['act'])}  "
              f"act-early={f3(a['act_early'])}  surf+act={f3(a['both'])}  "
              f"increment={a['increment']:+.3f}")
        if "decomp" in r:
            dd = r["decomp"]
            print(f"  decomp : internal pre={f3(dd['auroc_pre_internal'])} "
                  f"post={f3(dd['auroc_post_internal'])} resid={f3(dd['auroc_resid'])} | "
                  f"within-q int={f3(dd['within_q_internal'])} resid={f3(dd['within_q_resid'])} "
                  f"verb={f3(dd['within_q_verbalized'])} (n_mixed={dd['n_mixed']})")
        if "selective" in r:
            se = r["selective"]
            print("  select : " + "  ".join(
                f"cov{int(c*100)}% int={se['internal'][c]:.2f}/verb={se['verbalized'][c]:.2f}"
                for c in COVS))
        if "boot_int_minus_verb" in r:
            bb = r["boot_int_minus_verb"]
            print(f"  boot   : internal-verbalized = {bb['mean']:+.3f} "
                  f"[{bb['lo']:+.3f},{bb['hi']:+.3f}] "
                  f"{'SIGNIFICANT' if bb['significant'] else 'ns'}")
        l0 = r["layer0"]
        print(f"  layer0 : pooled={f3(l0['pooled'])} per-fold={f3(l0['per_fold'])} | "
              f"fix: pooled={f3(l0['fix_pooled'])} per-fold={f3(l0['fix_per_fold'])}")

    # ---- per-model transfer matrices --------------------------------------
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    print("\n" + "=" * 100)
    print("TIER-1 TRANSFER: train on domain A (POST site, fixed layer) -> test on domain B")
    print("   diagonal = grouped-OOF in-domain; per-domain standardization; PCA(50) fit on train")
    print("=" * 100)
    for model, doms in permodel.items():
        names = [dm for dm in ["geometry", "mmlu_pro", "gsm8k", "math", "gpqa"] if dm in doms]
        if len(names) < 2:
            continue
        T, cos = {}, {}
        fitted = {}
        for A in names:
            XA, yA, gA = doms[A][0], doms[A][1], doms[A][2]
            sA = StandardScaler().fit(XA)
            ZA = sA.transform(XA)
            k = min(50, len(yA) - 1, XA.shape[1])
            pcaA = PCA(k, random_state=0).fit(ZA)
            lrA = LogisticRegression(max_iter=2000).fit(pcaA.transform(ZA), yA)
            wA = ZA[yA == 1].mean(0) - ZA[yA == 0].mean(0)
            fitted[A] = (sA, pcaA, lrA, wA)
        for A in names:
            sA, pcaA, lrA, wA = fitted[A]
            for B in names:
                if A == B:
                    T[(A, B)] = doms[A][3]           # in-domain OOF reference
                else:
                    XB, yB = doms[B][0], doms[B][1]
                    ZB = sA.transform(XB)
                    T[(A, B)] = _auroc(lrA.decision_function(pcaA.transform(ZB)), yB)
                    wB = fitted[B][3]
                    cos[(A, B)] = float(np.dot(wA, wB) /
                                        (np.linalg.norm(wA) * np.linalg.norm(wB) + 1e-8))
        # cross-site: train POST -> test clean-PRE (held-out groups), per domain
        xsite = {}
        for A in names:
            Xq, yq, gq = doms[A][0], doms[A][1], doms[A][2]
            Xp_all, yp_all, gp_all = doms[A][4], doms[A][5], doms[A][6]
            ns = min(5, len(set(gq.tolist())))
            if ns < 2:
                continue
            sc = []
            yy = []
            for tr, te in GroupKFold(ns).split(Xq, yq, gq):
                if len(set(yq[tr].tolist())) < 2:
                    continue
                sq = StandardScaler().fit(Xq[tr])
                k = min(50, len(tr) - 1, Xq.shape[1])
                pc = PCA(k, random_state=0).fit(sq.transform(Xq[tr]))
                lr = LogisticRegression(max_iter=2000).fit(pc.transform(sq.transform(Xq[tr])), yq[tr])
                te_groups = set(gq[te].tolist())
                pm = np.isin(gp_all, list(te_groups))
                train_pm = ~pm
                if not train_pm.any() or not pm.any():
                    continue
                sp = StandardScaler().fit(Xp_all[train_pm])
                sc.extend(lr.decision_function(pc.transform(sp.transform(Xp_all[pm]))))
                yy.extend(yp_all[pm])
            xsite[A] = _auroc(sc, yy) if yy else float("nan")
        results["transfer"][model] = {
            "matrix": {f"{A}->{B}": (None if np.isnan(T[(A, B)]) else round(T[(A, B)], 3))
                       for A in names for B in names},
            "cosines": {f"{A}~{B}": round(c, 3) for (A, B), c in cos.items()},
            "cross_site_post_to_pre": {A: (None if np.isnan(v) else round(v, 3))
                                       for A, v in xsite.items()},
        }
        print(f"\n--- {model} ---")
        print("          " + "".join(f"{B[:9]:>10}" for B in names))
        for A in names:
            print(f"  {A[:8]:<8}" + "".join(f"{T[(A, B)]:>10.3f}" for B in names))
        offd = [T[(A, B)] for A in names for B in names
                if A != B and not np.isnan(T[(A, B)])]
        diag = [T[(A, A)] for A in names if not np.isnan(T[(A, A)])]
        print(f"  mean diagonal (in-domain OOF) = {np.mean(diag):.3f} | "
              f"mean off-diagonal (transfer) = {np.mean(offd):.3f}")
        if cos:
            print("  direction cosines: " + "  ".join(f"{A[:4]}~{B[:4]}={c:+.2f}"
                                                      for (A, B), c in sorted(cos.items())))
        print("  cross-site POST->cleanPRE: " + "  ".join(f"{A[:6]}={v:.3f}"
                                                          for A, v in xsite.items()
                                                          if not np.isnan(v)))

    out = root / "tier1_review.json"
    out.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nsaved {out}")
    print("NOTE: QA surface features use the truncated (200-char) stored answer — "
          "length is right-censored; geometry uses the full construction text.")


if __name__ == "__main__":
    main()
