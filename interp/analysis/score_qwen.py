"""Score Qwen3.6 J-lens (label-free) vs verbalized / P(True) / supervised probe — hybrid arch case."""
import numpy as np, json, pathlib, glob, re, warnings
warnings.filterwarnings("ignore")
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

ROOT = pathlib.Path("/Users/mlc/Code/carnegie/geometry-diagram-generator")
z = np.load(ROOT/"interp/activations/jlens/jlens_readouts_qwen36.npz")
R, fit_layers = z["R"], z["fit_layers"]
n_fail, n_ok = int(z["n_fail"]), int(z["n_ok"])
Li = 1; L = int(fit_layers[Li])                      # deep fit layer (45)
jdir = (R[n_fail:n_fail+n_ok, Li, :].mean(0) - R[:n_fail, Li, :].mean(0)).astype(np.float32)  # toward correct

def auroc(score, y):
    s = np.asarray(score, float); m = np.isfinite(s)
    if m.sum() < 5 or len(set(y[m].tolist())) < 2: return float("nan")
    return roc_auc_score(y[m], s[m])

base = lambda pid: re.sub(r"_s\d+$", "", str(pid))
cells = ["fix_qwen36_math", "fix_qwen36_mmlu_pro", "fix_qwen36_gpqa", "fix_qwen36_temporal"]
print(f"Qwen3.6 J-lens race (read at layer {L}; jdir = ok - fail words)\n" + "="*78)
print(f"{'cell':24s} {'n':>4s} {'pass':>5s} | {'verbal':>7s} {'P(True)':>7s} {'probe':>7s} {'JLENS':>7s} | cos")
for name in cells:
    d = ROOT/"interp/activations"/name
    if not d.exists(): print(f"{name:24s}  (missing)"); continue
    recs = [json.loads(l) for l in (d/"meta.jsonl").read_text().splitlines()]
    X, y, verb, pt, grp = [], [], [], [], []
    for r in recs:
        f = d/f"{r['pid']}.npz"
        if not f.exists(): continue
        try: zz = np.load(f)
        except Exception: continue
        if "post_dtoken" not in zz or "layer_ids" not in zz: continue
        li = zz["layer_ids"].tolist()
        row = li.index(L) if L in li else (L if L < zz["post_dtoken"].shape[0] else -1)
        X.append(zz["post_dtoken"][row].astype(np.float32)); y.append(1 if r["grade"]["ok"] else 0)
        verb.append(r.get("post_conf", np.nan)); pt.append(r.get("p_true", np.nan)); grp.append(base(r["pid"]))
    if not X: print(f"{name:24s}  (no npz)"); continue
    X = np.stack(X); y = np.array(y); verb = np.array(verb, float); pt = np.array(pt, float); grp = np.array(grp)
    jl = X @ jdir
    probe = np.full(len(y), np.nan); cos = float("nan")
    if len(set(y.tolist())) > 1:
        k = max(2, min(5, len(set(grp.tolist()))))
        try:
            pipe = make_pipeline(StandardScaler(), PCA(n_components=min(50, X.shape[0]-1, X.shape[1])),
                                 LogisticRegression(max_iter=2000))
            probe = cross_val_predict(pipe, X, y, cv=GroupKFold(k), groups=grp, method="predict_proba")[:, 1]
        except Exception as e: print("  probe err", e)
        pdir = X[y==1].mean(0) - X[y==0].mean(0)
        cos = float(pdir @ jdir / (np.linalg.norm(pdir)*np.linalg.norm(jdir)+1e-9))
    print(f"{name:24s} {len(y):4d} {y.mean():5.2f} | {auroc(verb,y):7.3f} {auroc(pt,y):7.3f} {auroc(probe,y):7.3f} {auroc(jl,y):7.3f} | {cos:+.3f}")
