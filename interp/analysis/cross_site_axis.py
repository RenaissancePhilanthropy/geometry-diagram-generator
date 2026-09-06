"""Same direction, or genuinely different representations?

The cross-site probe test is confounded: a probe carries a standardizer and PCA basis fitted
at one site, so it fails at another site whether or not the underlying direction is shared.
This removes that confound. Each site is z-scored with ITS OWN statistics, the class
difference-of-means is computed inside each site's own whitened space, and we compare the
resulting axes. A shared representation should give a substantial cosine even though the raw
activations live in different regions; genuinely different encodings should not.

Null distribution: cosine between the real axis and axes from label-shuffled data, same
geometry, so "how big is 0.1 here" is answerable rather than eyeballed.
"""
import json, re, sys, pathlib, numpy as np

task = sys.argv[1]
ans = pathlib.Path(f"interp/activations/ansite_mistral_{task}")
conf = pathlib.Path(f"interp/activations/fix_mistral_{task}")
meta = [json.loads(l) for l in (conf / "meta.jsonl").read_text().splitlines()]

L = 28
A, C, y = [], [], []
for r in meta:
    fa, fc = ans / f"{r['pid']}.npz", conf / f"{r['pid']}.npz"
    if not (fa.exists() and fc.exists()):
        continue
    za, zc = np.load(fa), np.load(fc)
    if "answer_last" not in za or "post_dtoken" not in zc:
        continue
    va, vc = za["answer_last"], zc["post_dtoken"]
    A.append((va[L] if va.ndim == 2 else va).astype(np.float32))
    C.append((vc[L] if vc.ndim == 2 else vc).astype(np.float32))
    y.append(1 if r["grade"]["ok"] else 0)
A, C, y = np.stack(A), np.stack(C), np.array(y)

def axis(X, lab):
    Z = (X - X.mean(0)) / (X.std(0) + 1e-6)          # each site whitened by its own stats
    w = Z[lab == 1].mean(0) - Z[lab == 0].mean(0)
    return w / (np.linalg.norm(w) + 1e-12)

wa, wc = axis(A, y), axis(C, y)
real = float(wa @ wc)

rng = np.random.default_rng(0)
null = []
for _ in range(200):
    ys = rng.permutation(y)
    null.append(float(axis(A, ys) @ axis(C, ys)))
null = np.abs(np.array(null))

print(f"{task}: n={len(y)}  dim={A.shape[1]}")
print(f"  cosine(answer-end axis, confidence-token axis), each site self-whitened = {real:+.3f}")
print(f"  label-shuffled null: mean |cos| {null.mean():.3f}, 95th pct {np.percentile(null,95):.3f}")
print(f"  -> {'ABOVE the null: the axes share real structure' if abs(real) > np.percentile(null,95) else 'INSIDE the null: no evidence of a shared axis'}")
# how much correctness signal does each axis carry at the OTHER site?
from sklearn.metrics import roc_auc_score
Za = (A - A.mean(0)) / (A.std(0) + 1e-6)
Zc = (C - C.mean(0)) / (C.std(0) + 1e-6)
print(f"  answer-end axis scoring confidence-token vectors: AUROC {roc_auc_score(y, Zc @ wa):.3f}")
print(f"  confidence-token axis scoring answer-end vectors:  AUROC {roc_auc_score(y, Za @ wc):.3f}")
print(f"  (each axis at its own site: {roc_auc_score(y, Za @ wa):.3f} / {roc_auc_score(y, Zc @ wc):.3f}, in-sample)")
