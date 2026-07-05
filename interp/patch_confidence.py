"""
RQ8 — causal activation-steering test: does the model USE its internal
"am I correct?" direction to set its stated confidence?

probe.py shows the correctness direction is *present* (decodable) at the
confidence decision token. This asks the stronger question: if we ADD that
direction to the residual stream at that site, does the model shift toward
stating higher confidence? Control: a random direction of equal norm.

READOUT — a log-prob difference, NOT the decoded number. Qwen's stated
confidence is mode-collapsed at ~100 (verbalized AUROC ~0.52), so the decoded
integer is saturated. Instead we score, at the decision token,
    logP("<high>") - logP("<low>")   (teacher-forced)
which has dynamic range even when the argmax stays pinned.

Sweeps LAYERS x COEFFICIENTS (one model load). For each layer L the steering
vector is the diff-of-means (ok-fail) of the decision-token activation at L;
coefficients are multiples of that raw vector. Runs locally on Qwen-7B.

    interp/.venv/bin/python interp/patch_confidence.py --device mps
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", default="interp/activations/qwen7_2turn")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--layers", default="14,22,26",
                    help="comma list of acts/hidden-state layers (>=1); steers block (L-1)")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--alphas", default="-64,-32,-16,0,16,32,64",
                    help="coefficients on the raw diff-of-means vector")
    ap.add_argument("--high", default="100")
    ap.add_argument("--low", default="30")
    ap.add_argument("--few-shot", default="none")
    ap.add_argument("--out", default="interp/activations/patch_confidence.json")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    layers = [int(x) for x in args.layers.split(",")]
    if any(L < 1 for L in layers):
        raise SystemExit("--layers must be >= 1 (layer 0 is the embedding)")
    alphas = [float(a) for a in args.alphas.split(",")]

    import torch
    from interp.probe import load_dataset, build_xy, label_correctness_conf
    from interp.confidence import build_confidence_followup
    from interp.capability_check import (build_messages, select_recipes,
                                         load_catalog_recipes, load_model)

    recs = load_dataset(pathlib.Path(args.act_dir))

    def _m(rc):
        return rc.get("meta") or {}
    usable = [rc for rc in recs
              if (rc.get("completion") or _m(rc).get("completion"))
              and _m(rc).get("prompt") and _m(rc).get("conf_decision_pos") is not None
              and isinstance(_m(rc).get("grade"), dict)]
    ok_recs = [rc for rc in usable if _m(rc)["grade"].get("ok")]
    bad_recs = [rc for rc in usable if not _m(rc)["grade"].get("ok")]
    sel, i = [], 0
    while len(sel) < min(args.n, len(usable)) and (ok_recs or bad_recs):
        take_bad = (i % 2 == 0 and bad_recs) or not ok_recs
        sel.append((bad_recs if take_bad else ok_recs).pop(0))
        i += 1
    print(f"selected {len(sel)} records ({sum(bool(_m(rc)['grade'].get('ok')) for rc in sel)} ok); "
          f"layers={layers} alphas={alphas}")

    tok, model = load_model(args.model, args.device, "none")
    model.eval()
    catalog = load_catalog_recipes()
    high_ids = tok(args.high, add_special_tokens=False).input_ids
    low_ids = tok(args.low, add_special_tokens=False).input_ids

    def build_inputs(rc, few_shot):
        m = rc["meta"]
        recipes = select_recipes(m["prompt"], catalog, few_shot)
        construction = rc.get("completion") or m.get("completion", "")
        msgs = build_confidence_followup(build_messages(m["prompt"], recipes), construction)
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) + "Confidence: "
        return tok(text, return_tensors="pt").to(args.device)["input_ids"]

    # precompute prompts once (reused across layers)
    base_list = []
    for rc in sel:
        ids = build_inputs(rc, args.few_shot)
        if args.device == "mps" and ids.shape[1] > 4096:
            ids = build_inputs(rc, "none")
        base_list.append(ids)

    def cand_logprob(block, base_ids, cand_ids, vec, coeff):
        plen = base_ids.shape[1]
        full = torch.cat([base_ids, torch.tensor([cand_ids], device=args.device)], dim=1)
        add = None if coeff == 0.0 else torch.tensor(coeff * vec, dtype=model.dtype,
                                                     device=args.device)

        def hook(mod, inp, out):
            h = out[0] if isinstance(out, tuple) else out
            h[:, plen - 1, :] = h[:, plen - 1, :] + add   # steer AT the decision token
            return out

        handle = block.register_forward_hook(hook) if add is not None else None
        try:
            with torch.no_grad():
                hs = model.model(input_ids=full, use_cache=False).last_hidden_state[0]
                rows = hs[plen - 1: plen - 1 + len(cand_ids)]     # only the positions we score
                logits = model.lm_head(rows).float()              # [len(cand), vocab]
        finally:
            if handle is not None:
                handle.remove()
        lp = torch.log_softmax(logits, dim=-1)
        return float(sum(lp[j, t].item() for j, t in enumerate(cand_ids)))

    def readout(block, base_ids, vec, coeff):
        return (cand_logprob(block, base_ids, high_ids, vec, coeff)
                - cand_logprob(block, base_ids, low_ids, vec, coeff))

    results = {}
    any_causal = False
    for L in layers:
        X, y, _, _ = build_xy(recs, L, label_correctness_conf)
        ok = (y == "ok")
        w = (X[ok].mean(0) - X[~ok].mean(0)).astype(np.float32)
        wn = float(np.linalg.norm(w))
        s = float(np.median(np.linalg.norm(X, axis=1)))
        rng = np.random.default_rng(args.seed)
        r = rng.standard_normal(w.shape[0]).astype(np.float32)
        r *= wn / (float(np.linalg.norm(r)) + 1e-8)
        block = model.model.layers[L - 1]
        steer = {a: [] for a in alphas}
        rand = {a: [] for a in alphas}
        for base_ids in base_list:
            for a in alphas:
                steer[a].append(readout(block, base_ids, w, a))
                rand[a].append(readout(block, base_ids, r, a))
        steer_means = [float(np.mean(steer[a])) for a in alphas]
        rand_means = [float(np.mean(rand[a])) for a in alphas]
        steer_slope = float(np.polyfit(alphas, steer_means, 1)[0])
        rand_slope = float(np.polyfit(alphas, rand_means, 1)[0])
        delta = steer_means[-1] - steer_means[0]
        causal = steer_slope > 0 and abs(steer_slope) > 3 * abs(rand_slope) and delta >= 0.5
        any_causal = any_causal or causal
        results[L] = {"steer_means": steer_means, "rand_means": rand_means,
                      "steer_slope": steer_slope, "rand_slope": rand_slope,
                      "delta": delta, "causal": causal, "diff_means_norm": wn,
                      "median_act_norm": s,
                      "steer_raw": {str(a): steer[a] for a in alphas},
                      "rand_raw": {str(a): rand[a] for a in alphas}}
        print(f"\n=== layer {L}  (|w|={wn:.2f}, median|act|={s:.1f}; coeff*|w| reaches "
              f"{max(abs(a) for a in alphas)*wn:.0f} = {max(abs(a) for a in alphas)*wn/s:.1f}x act) ===")
        print("  alpha |  steer logP(hi)-logP(lo) | random")
        for a, sm, rm in zip(alphas, steer_means, rand_means):
            print(f"  {a:+7.1f} |        {sm:+8.2f}       | {rm:+8.2f}")
        print(f"  slope steer={steer_slope:+.4f}  random={rand_slope:+.4f}  delta={delta:+.2f} nats  "
              f"-> {'CAUSAL' if causal else 'no effect'}")

    print("\n" + "=" * 60)
    print("OVERALL VERDICT:", "CAUSAL at >=1 layer — the correctness direction is used"
          if any_causal else
          "NO causal effect at any tested layer/scale — the direction is DECODABLE BUT NOT USED here")

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps({
        "model": args.model, "layers": layers, "alphas": alphas,
        "high": args.high, "low": args.low, "n_records": len(sel),
        "any_causal": any_causal, "by_layer": {str(L): results[L] for L in layers},
    }, indent=2))
    print("saved", args.out)


if __name__ == "__main__":
    main()
