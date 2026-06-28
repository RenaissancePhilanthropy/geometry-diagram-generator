import sys, io, contextlib, pathlib, numpy as np, statistics
sys.path.insert(0,".")
from interp.probe import run_probe
SEEDS=[0,1,2,3]
def onset_and_peak(d, lab, seed):
    with contextlib.redirect_stdout(io.StringIO()):
        out=run_probe(pathlib.Path(f"interp/activations/{d}"),lab,0.3,seed)
    L=np.array([c["layer"] for c in out["curve"]]); S=np.array([c["score"] for c in out["curve"]])
    nL=L.max(); fr=L/nL
    peak=S.max()
    onset=fr[np.argmax(S>=0.9*peak)]      # shallowest frac depth reaching 90% of peak
    l0=S[fr.argmin()]                      # input-layer score (naming/given level)
    return onset, peak, l0
for tag,d in [("7B-bf16","big30"),("32B-AWQ","q32_awq")]:
    print(f"\n===== {tag} =====")
    print(f"{'concept':16}{'onset depth':>16}{'peak score':>14}{'input(L0)':>11}")
    rows=[]
    for lab in ["entity_relation","angle","point_coord"]:
        on=[]; pk=[]; l0=[]
        for s in SEEDS:
            o,p,z=onset_and_peak(d,lab,s); on.append(o); pk.append(p); l0.append(z)
        rows.append((lab, statistics.mean(on), statistics.pstdev(on), statistics.mean(pk), statistics.pstdev(pk), statistics.mean(l0)))
        print(f"{lab:16}{statistics.mean(on):>9.0%} ±{statistics.pstdev(on):>4.0%}{statistics.mean(pk):>10.2f} ±{statistics.pstdev(pk):.2f}{statistics.mean(l0):>11.2f}")
