import re, sys, pathlib, statistics, numpy as np
from itertools import combinations
from collections import defaultdict
sys.path.insert(0,".")
from interp.probe import load_dataset, label_point_coord, label_entity_relation
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge, LogisticRegression

recs = load_dataset(pathlib.Path("interp/activations/big30"))

# ---- 1) per-prompt consistency = mean pairwise Jaccard of relation-TYPE sets ----
def base_of(pid): return re.sub(r"_s\d+$","",pid)
sigs = defaultdict(list)
for r in recs:
    rels = frozenset((r["meta"].get("ground_truth") or {}).get("entity_relations",{}).values())
    if rels: sigs[base_of(r["pid"])].append(rels)
def jacc(a,b): return 1.0 if a==b else len(a&b)/len(a|b)
cons={b:statistics.mean([jacc(x,y) for x,y in combinations(S,2)]) for b,S in sigs.items() if len(S)>=3}
v=list(cons.values())
print(f"prompts scored (>=3 relation-bearing samples): {len(cons)}")
print(f"consistency: mean={statistics.mean(v):.2f} median={statistics.median(v):.2f} | perfect(=1.0): {sum(x>=0.999 for x in v)} | low(<0.5): {sum(x<0.5 for x in v)}")

# ---- 2) decodability split by consistency (median) ----
def gather(labeler, L):
    X,Y,C,G=[],[],[],[]
    for r in recs:
        b=base_of(r["pid"])
        if b not in cons: continue
        acts=r["acts"]; pm=r.get("pos_map"); P=acts.shape[1]; sp=r["meta"].get("is_special") or []
        for pos,lab in labeler(r).items():
            if sp and pos<len(sp) and sp[pos]: continue
            ai=pos if pm is None else pm.get(pos)
            if ai is None or ai>=P: continue
            X.append(acts[L,ai,:].astype("float32")); Y.append(lab); C.append(cons[b]); G.append(b)
    return np.array(X),Y,np.array(C),np.array(G)

def split_eval(labeler,L,kind):
    X,Y,C,G=gather(labeler,L)
    if kind=="reg": Y=np.array([np.asarray(z,float) for z in Y])
    else: Y=np.array(Y)
    tr,te=next(GroupShuffleSplit(1,test_size=0.3,random_state=0).split(X,Y,G))
    est=Ridge(1.0) if kind=="reg" else LogisticRegression(max_iter=4000)
    m=make_pipeline(StandardScaler(),PCA(100),est); m.fit(X[tr],Y[tr])
    med=np.median(C[te]); hi=te[C[te]>=med]; lo=te[C[te]<med]
    def score(idx):
        if kind=="reg":
            p=m.predict(X[idx]); yt=Y[idx]; return 1-((yt-p)**2).sum()/((yt-yt.mean(0))**2).sum()
        return (m.predict(X[idx])==Y[idx]).mean()
    metric="R2" if kind=="reg" else "acc"
    print(f"  {kind} {metric}:  HIGH-consistency={score(hi):.3f} (n={len(hi)})   LOW-consistency={score(lo):.3f} (n={len(lo)})   median-cons={med:.2f}")

print("\npoint_coord @ L21 (does confidence -> cleaner coords?):")
split_eval(label_point_coord,21,"reg")
print("entity_relation @ L14:")
split_eval(label_entity_relation,14,"clf")
