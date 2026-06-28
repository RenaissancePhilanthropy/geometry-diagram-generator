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
LAYER = 21  # coord peak

# build_xy gives per-position X, y(true [x,y]), groups(figure idx)
X,Y,G,_ = build_xy(recs, LAYER, label_point_coord)
Y = np.array([np.asarray(v,float) for v in Y]); G=np.array(G)
tr,te = next(GroupShuffleSplit(1,test_size=0.3,random_state=0).split(X,Y,G))
m = make_pipeline(StandardScaler(), PCA(100), Ridge(1.0)).fit(X[tr],Y[tr])
P = m.predict(X[te])           # decoded positions for held-out points
Yte = Y[te]; Gte = G[te]

def pdist_off(C):              # off-diagonal pairwise distances of a point set
    return np.array([np.linalg.norm(C[i]-C[j]) for i,j in combinations(range(len(C)),2)])

rng = np.random.default_rng(0)
real, null = [], []; nfig=0; abs_r2_num=0; abs_r2_den=0
for g in np.unique(Gte):
    idx = np.where(Gte==g)[0]
    if len(idx) < 4:           # need >=4 points for a meaningful shape
        continue
    nfig += 1
    true_d = pdist_off(Yte[idx]); pred_d = pdist_off(P[idx])
    if true_d.std()<1e-9 or pred_d.std()<1e-9: continue
    real.append(np.corrcoef(true_d, pred_d)[0,1])
    # null: shuffle which decoded point maps to which true point
    perm = rng.permutation(len(idx))
    null.append(np.corrcoef(true_d, pdist_off(P[idx][perm]))[0,1])

real=np.array(real); null=np.array(null)
print(f"figures with >=4 decoded points: {nfig}")
print(f"shape-correlation (true vs decoded pairwise distances):")
print(f"   REAL   mean={real.mean():.3f}  median={np.median(real):.3f}")
print(f"   NULL   mean={null.mean():.3f}  median={np.median(null):.3f}  (shuffled point identities)")
print(f"   figures where REAL>NULL: {(real>null).mean():.0%}")
print(f"   figures with strong shape match (REAL>0.5): {(real>0.5).mean():.0%}")
# absolute per-axis R2 for reference
for ax,name in [(0,'x'),(1,'y')]:
    yt=Yte[:,ax]; pr=P[:,ax]; r2=1-((yt-pr)**2).sum()/((yt-yt.mean())**2).sum()
    print(f"   absolute {name}-coord R2 = {r2:.3f}")
