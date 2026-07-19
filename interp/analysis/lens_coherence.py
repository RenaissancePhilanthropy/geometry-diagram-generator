import numpy as np, pathlib
ROOT = pathlib.Path("/Users/mlc/Code/carnegie/geometry-diagram-generator/interp/activations/jlens")
def norm(M): return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
def mean_pairwise_cos(M):  # M: rows = unit vectors
    C = M @ M.T; iu = np.triu_indices(len(M), 1); return float(C[iu].mean())
print(f"{'model':10s} {'arch':16s} | {'within-FAIL':>11s} {'within-OK':>10s} {'OK-vs-FAIL':>11s} | verdict")
print("-"*78)
info = {"mistral":"dense-attn","q25":"dense-attn","qwen36":"Mamba-hybrid","glm":"MoE"}
for m in ["mistral","q25","qwen36","glm"]:
    f = ROOT/f"jlens_readouts_{m}.npz"
    if not f.exists(): print(f"{m:10s} (no readout)"); continue
    z = np.load(f); R = z["R"]; nf, no = int(z["n_fail"]), int(z["n_ok"]); Li = 1
    fail = norm(R[:nf, Li, :]); ok = norm(R[nf:nf+no, Li, :])
    wf, wo = mean_pairwise_cos(fail), mean_pairwise_cos(ok)
    sep = float(norm(ok.mean(0,keepdims=True))[0] @ norm(fail.mean(0,keepdims=True))[0])
    # faithful lens: within-group high(+), ok-vs-fail low/negative (they oppose)
    coherent = (wf>0.15 and wo>0.15); opposed = sep<0.5
    verdict = "coherent+separated" if (coherent and opposed) else ("COLLAPSED (ok≈fail)" if sep>0.8 else "incoherent")
    print(f"{m:10s} {info[m]:16s} | {wf:+11.3f} {wo:+10.3f} {sep:+11.3f} | {verdict}")
print("\nfaithful lens -> within-FAIL & within-OK positive (words cluster),")
print("                OK-vs-FAIL low/negative (opposite meanings separate).")
print("broken lens   -> readouts collapse (OK-vs-FAIL ~1) or scatter (within ~0).")
