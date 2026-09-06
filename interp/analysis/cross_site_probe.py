"""Does the confidence-token probe transfer to the answer-end site?

If one correctness direction is carried from the answer to the confidence token, a probe
trained at the confidence token should read the answer-end vector. If the near-zero cosine
between the two probe directions reflects genuinely different representations rather than
the usual fact that different token positions occupy different regions, it will collapse.
Both directions tested, on held-out questions.
"""
import json, re, sys, pathlib, numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

task = sys.argv[1]
ans = pathlib.Path(f"interp/activations/ansite_mistral_{task}")
conf = pathlib.Path(f"interp/activations/fix_mistral_{task}")
meta = [json.loads(l) for l in (conf / "meta.jsonl").read_text().splitlines()]

L = 28
A, C, y, g = [], [], [], []
for r in meta:
    fa, fc = ans / f"{r['pid']}.npz", conf / f"{r['pid']}.npz"
    if not (fa.exists() and fc.exists()):
        continue
    za, zc = np.load(fa), np.load(fc)
    if "answer_last" not in za or "post_dtoken" not in zc:
        continue
    va = za["answer_last"]; vc = zc["post_dtoken"]
    va = va[L] if va.ndim == 2 else va
    vc = vc[L] if vc.ndim == 2 else vc
    A.append(va.astype(np.float32)); C.append(vc.astype(np.float32))
    y.append(1 if r["grade"]["ok"] else 0); g.append(re.sub(r"_s\d+$", "", r["pid"]))
A, C, y, g = np.stack(A), np.stack(C), np.array(y), np.array(g)
print(f"{task}: {len(y)} records aligned at both sites, dim {A.shape[1]}, pass {y.mean():.2f}")

def run(Xtr, Xte, tag):
    s = np.full(len(y), np.nan)
    for tr, te in GroupKFold(5).split(Xtr, y, g):
        p = make_pipeline(StandardScaler(), PCA(50, random_state=0),
                          LogisticRegression(max_iter=2000)).fit(Xtr[tr], y[tr])
        s[te] = p.decision_function(Xte[te])
    m = ~np.isnan(s)
    print(f"  {tag:44} {roc_auc_score(y[m], s[m]):.3f}")

run(C, C, "confidence-token probe, read at its own site")
run(A, A, "answer-end probe, read at its own site")
run(C, A, "confidence-token probe -> READ AT ANSWER END")
run(A, C, "answer-end probe -> READ AT CONFIDENCE TOKEN")
