"""Score GLM J-lens (label-free) vs verbalized / P(True) / supervised probe, per cell.
Mirrors the Mistral race: read at the deep fit layer; jlens direction = ok-words - fail-words."""
import numpy as np, json, pathlib, glob, re, warnings
warnings.filterwarnings("ignore")
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

ROOT = pathlib.Path("/Users/mlc/Code/carnegie/geometry-diagram-generator")
z = np.load(ROOT/"interp/activations/jlens/jlens_readouts_glm.npz")
R, fit_layers = z["R"], z["fit_layers"]              # R:[33,2,2048]
n_fail, n_ok = int(z["n_fail"]), int(z["n_ok"])
Li = 1                                                # deep fit layer = fit_layers[1] (=33)
L = int(fit_layers[Li])
ok = R[n_fail:n_fail+n_ok, Li, :].mean(0)
fail = R[:n_fail, Li, :].mean(0)
jdir = (ok - fail).astype(np.float32)                # toward "correct"

def auroc(score, y):
    if len(set(y.tolist())) < 2: return float("nan")
    s = np.asarray(score, float)
    m = np.isfinite(s)
    if m.sum() < 5 or len(set(y[m].tolist())) < 2: return float("nan")
    return roc_auc_score(y[m], s[m])

base = lambda pid: re.sub(r"_s\d+$", "", str(pid))
cells = ["fix_glm_math", "fix_glm_mmlu_pro", "fix_glm_gpqa", "glm_temporal"]

print(f"GLM J-lens race  (read at layer {L}; jlens dir = ok-words - fail-words)\n" + "="*78)
print(f"{'cell':22s} {'n':>4s} {'pass':>5s} | {'verbal':>7s} {'P(True)':>7s} {'probe':>7s} {'JLENS':>7s} | cos(probe,j)")
for name in cells:
    d = ROOT/"interp/activations"/name
    if not d.exists():
        print(f"{name:22s}  (missing)"); continue
    recs = [json.loads(l) for l in (d/"meta.jsonl").read_text().splitlines()]
    X, y, verb, pt, grp = [], [], [], [], []
    for r in recs:
        f = d/f"{r['pid']}.npz"
        if not f.exists(): continue
        try: zz = np.load(f)
        except Exception: continue
        li = zz["layer_ids"].tolist()
        row = li.index(L) if L in li else (L if L < zz["post_dtoken"].shape[0] else -1)
        h = zz["post_dtoken"][row].astype(np.float32)
        X.append(h); y.append(1 if r["grade"]["ok"] else 0)
        verb.append(r.get("post_conf", np.nan)); pt.append(r.get("p_true", np.nan))
        grp.append(base(r["pid"]))
    X = np.stack(X); y = np.array(y); verb = np.array(verb, float); pt = np.array(pt, float)
    grp = np.array(grp)
    jl = X @ jdir
    # supervised probe, grouped-OOF
    probe = np.full(len(y), np.nan)
    if len(set(y.tolist())) > 1:
        ng = len(set(grp.tolist()))
        k = max(2, min(5, ng))
        try:
            pipe = make_pipeline(StandardScaler(), PCA(n_components=min(50, X.shape[0]-1, X.shape[1])),
                                 LogisticRegression(max_iter=2000, C=1.0))
            probe = cross_val_predict(pipe, X, y, cv=GroupKFold(k), groups=grp, method="predict_proba")[:, 1]
        except Exception as e:
            print("  probe err", e)
    # probe direction (fit on all, for cosine vs jlens)
    cos = float("nan")
    if np.isfinite(probe).any():
        pdir = X[y == 1].mean(0) - X[y == 0].mean(0)
        cos = float(pdir @ jdir / (np.linalg.norm(pdir)*np.linalg.norm(jdir) + 1e-9))
    print(f"{name:22s} {len(y):4d} {y.mean():5.2f} | {auroc(verb,y):7.3f} {auroc(pt,y):7.3f} "
          f"{auroc(probe,y):7.3f} {auroc(jl,y):7.3f} | {cos:+.3f}")
