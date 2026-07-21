import numpy as np, json, pathlib, warnings
warnings.filterwarnings("ignore")
from sklearn.metrics import roc_auc_score
ROOT = pathlib.Path("/Users/mlc/Code/carnegie/geometry-diagram-generator/interp/activations")
def ece(conf, y, bins=10):
    conf=np.asarray(conf,float); y=np.asarray(y,float)
    m=np.isfinite(conf); conf,y=conf[m],y[m]
    if conf.max()>1.5: conf=conf/100.0
    edges=np.linspace(0,1,bins+1); e=0.0; N=len(y)
    rows=[]
    for b in range(bins):
        lo,hi=edges[b],edges[b+1]
        sel=(conf>=lo)&(conf<hi) if b<bins-1 else (conf>=lo)&(conf<=hi)
        nb=sel.sum()
        if nb==0: continue
        acc=y[sel].mean(); cf=conf[sel].mean()
        e+=nb/N*abs(acc-cf)
        if nb>=5: rows.append((f"{lo:.1f}-{hi:.1f}",nb,round(cf,2),round(acc,2)))
    return e, conf.mean(), y.mean(), rows
cells=["fix_mistral_math","fix_glm_math","fix_qwen36_math","fix_mistral_mmlu_pro","mistral_temporal"]
print(f"{'cell':22s} {'n':>4s} {'pass':>5s} {'meanConf':>8s} {'ECE':>6s} {'AUROC(verb)':>11s}")
for c in cells:
    d=ROOT/c
    if not (d/"meta.jsonl").exists(): print(f"{c:22s} (missing)"); continue
    recs=[json.loads(l) for l in (d/"meta.jsonl").read_text().splitlines()]
    conf=[r.get("post_conf",np.nan) for r in recs]; y=[1 if r["grade"]["ok"] else 0 for r in recs]
    e,mc,pr,rows=ece(conf,y)
    cf=np.array(conf,float); yy=np.array(y); mm=np.isfinite(cf)
    au=roc_auc_score(yy[mm],cf[mm]) if len(set(yy[mm].tolist()))>1 else float("nan")
    print(f"{c:22s} {len(y):4d} {pr:5.2f} {mc:8.2f} {e:6.3f} {au:11.3f}")
# show reliability bins for one telling cell
print("\nreliability table — fix_qwen36_math (confidence bin: says X%, actually right Y%):")
d=ROOT/"fix_qwen36_math"; recs=[json.loads(l) for l in (d/"meta.jsonl").read_text().splitlines()]
_,_,_,rows=ece([r.get("post_conf",np.nan) for r in recs],[1 if r["grade"]["ok"] else 0 for r in recs])
print(f"  {'conf bin':10s} {'n':>4s} {'says':>6s} {'right':>6s}")
for lbl,nb,cf,acc in rows: print(f"  {lbl:10s} {nb:4d} {cf:6.2f} {acc:6.2f}")
