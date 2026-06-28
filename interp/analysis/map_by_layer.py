import sys, pathlib, numpy as np
from itertools import combinations
sys.path.insert(0,".")
from interp.probe import load_dataset, build_xy, label_point_coord
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge

recs = load_dataset(pathlib.Path("interp/activations/big30"))
nL = recs[0]["acts"].shape[0]
def pdoff(C): return np.array([np.linalg.norm(C[i]-C[j]) for i,j in combinations(range(len(C)),2)])
rng = np.random.default_rng(0)

print(f"layer  %depth   shape-corr   null    absR2")
for L in range(0, nL, 3):
    X,Y,G,_ = build_xy(recs, L, label_point_coord)
    Y=np.array([np.asarray(v,float) for v in Y]); G=np.array(G)
    tr,te=next(GroupShuffleSplit(1,test_size=0.3,random_state=0).split(X,Y,G))
    m=make_pipeline(StandardScaler(),PCA(100),Ridge(1.0)).fit(X[tr],Y[tr])
    P=m.predict(X[te]); Yte=Y[te]; Gte=G[te]
    real=[]; null=[]
    for g in np.unique(Gte):
        idx=np.where(Gte==g)[0]
        if len(idx)<4: continue
        td=pdoff(Yte[idx]); pd=pdoff(P[idx])
        if td.std()<1e-9 or pd.std()<1e-9: continue
        real.append(np.corrcoef(td,pd)[0,1])
        null.append(np.corrcoef(td,pdoff(P[idx][rng.permutation(len(idx))]))[0,1])
    absr2=1-((Yte-P)**2).sum()/((Yte-Yte.mean(0))**2).sum()
    print(f"{L:>4} {L/(nL-1):>7.0%} {np.mean(real):>11.3f} {np.mean(null):>7.3f} {absr2:>8.3f}")
