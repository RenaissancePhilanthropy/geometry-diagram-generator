"""
Phase 3 — activation patching: are the geometric representations CAUSAL?

Decodability (probe.py) shows a property is linearly *present* at a layer. This
asks the stronger question: does the model *use* it? We patch the residual stream
between minimal-pair prompts and measure whether the model's prediction flips.

Design (angle, the strongest signal):
  clean   = "... angle A = 60 degrees, so angle A ="   -> should predict "60"
  corrupt = "... angle A = 70 degrees, so angle A ="   -> should predict "70"
The two prompts are token-aligned and differ at ONE token (the stated angle).
We cache the corrupt run's residual stream, then re-run clean while overwriting,
at layer L and the angle-token position, with the corrupt activation. If the
readout (next-token logit) flips 60->70, layer L causally carries the angle.

Metric per layer = normalized logit-difference recovery, averaged over pairs:
    diff(x)   = logit(clean_ans) - logit(corrupt_ans)  at the readout position
    effect(L) = (diff_clean - diff_patched) / (diff_clean - diff_corrupt)
    0 = patch did nothing ; 1 = patch fully flipped the prediction to corrupt.

Runs on CUDA (or CPU for the offline mechanics test).
    python interp/patch.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Angle pairs (clean, corrupt). Both run in each direction for balance.
ANGLE_VALUES = [(60, 70), (70, 60), (50, 80), (80, 50), (40, 100),
                (100, 40), (45, 75), (75, 45), (30, 120), (120, 30)]

# Templates with two {a} slots: the stated fact, then the cued echo. The model
# predicts the angle right after the final "= ". Different surface forms average
# out template-specific quirks.
TEMPLATES = [
    "In triangle ABC, angle A = {a} degrees, so angle A = {a}",
    "Given: angle A is {a} degrees. Therefore angle A is {a}",
    "The angle A measures {a} degrees. Hence A = {a}",
]


def _build_pair(tok, template: str, clean_a: int, corrupt_a: int):
    """Return token ids for clean/corrupt prompts (prefix up to the final echo),
    the patch position (the stated-angle token), and the answer token ids — or
    None if the pair doesn't token-align (different lengths / multi-token angle)."""
    # text up to BUT NOT INCLUDING the final echoed number (that's the readout)
    head = template[: template.rfind("{a}")]
    clean_head = head.format(a=clean_a)
    corrupt_head = head.format(a=corrupt_a)
    ci = tok(clean_head, add_special_tokens=False).input_ids
    di = tok(corrupt_head, add_special_tokens=False).input_ids
    if len(ci) != len(di):
        return None
    diff = [k for k in range(len(ci)) if ci[k] != di[k]]
    if len(diff) != 1:                      # exactly one differing token (the angle)
        return None
    # answer = the token that actually continues each head in context (the readout
    # position predicts this). Tokenize head+number, take the token after the head.
    full_c = tok(clean_head + str(clean_a), add_special_tokens=False).input_ids
    full_d = tok(corrupt_head + str(corrupt_a), add_special_tokens=False).input_ids
    if len(full_c) <= len(ci) or len(full_d) <= len(di):
        return None
    ca, da = full_c[len(ci)], full_d[len(di)]
    if ca == da:                            # readout can't distinguish -> skip
        return None
    return {"clean_ids": ci, "corrupt_ids": di, "patch_pos": diff[0],
            "clean_ans": ca, "corrupt_ans": da}


def _layers(model):
    return model.model.layers


def run_patching(model, tok, device: str):
    import torch

    layers = _layers(model)
    n_layers = len(layers)

    pairs = []
    for template in TEMPLATES:
        for clean_a, corrupt_a in ANGLE_VALUES:
            p = _build_pair(tok, template, clean_a, corrupt_a)
            if p is not None:
                pairs.append(p)
    if not pairs:
        raise SystemExit("no token-aligned minimal pairs built")
    print(f"{len(pairs)} minimal pairs, {n_layers} layers")

    # effect[L] accumulates the normalized recovery over pairs
    effect_sum = [0.0] * n_layers
    n_used = 0

    for p in pairs:
        clean = torch.tensor([p["clean_ids"]], device=device)
        corrupt = torch.tensor([p["corrupt_ids"]], device=device)
        pos = p["patch_pos"]
        ca, da = p["clean_ans"], p["corrupt_ans"]

        # 1) cache corrupt residual stream (output of every layer) at the patch pos
        cache = {}
        handles = []
        for li, layer in enumerate(layers):
            def mk(li):
                def hook(mod, inp, out):
                    hs = out[0] if isinstance(out, tuple) else out
                    cache[li] = hs[:, pos, :].detach().clone()
                return hook
            handles.append(layer.register_forward_hook(mk(li)))
        with torch.no_grad():
            model(corrupt)
        for h in handles:
            h.remove()

        # 2) clean & corrupt baseline logit diffs at the readout (last position)
        with torch.no_grad():
            clean_logits = model(clean).logits[0, -1]
            corrupt_logits = model(corrupt).logits[0, -1]
        diff_clean = (clean_logits[ca] - clean_logits[da]).item()
        diff_corrupt = (corrupt_logits[ca] - corrupt_logits[da]).item()
        denom = diff_clean - diff_corrupt
        if abs(denom) < 1e-6:               # model doesn't distinguish -> skip pair
            continue
        n_used += 1

        # 3) patch clean at each layer (one layer at a time) and re-read
        for li in range(n_layers):
            def patch_hook(mod, inp, out, li=li):
                hs = out[0] if isinstance(out, tuple) else out
                hs[:, pos, :] = cache[li]
                return (hs,) + tuple(out[1:]) if isinstance(out, tuple) else hs
            h = layers[li].register_forward_hook(patch_hook)
            with torch.no_grad():
                patched = model(clean).logits[0, -1]
            h.remove()
            diff_patched = (patched[ca] - patched[da]).item()
            effect_sum[li] += (diff_clean - diff_patched) / denom

    if n_used == 0:
        raise SystemExit("no usable pairs (model didn't separate clean/corrupt)")

    curve = [{"layer": li, "effect": round(effect_sum[li] / n_used, 4)}
             for li in range(n_layers)]
    return {"n_pairs": n_used, "n_layers": n_layers, "curve": curve}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit"), default="none",
                    help="'4bit' = NF4 quant (fits big models on 48GB; muddies activations)")
    ap.add_argument("--out", default="interp/activations/patch_angle.json")
    args = ap.parse_args()

    from interp.capability_check import load_model
    tok, model = load_model(args.model, args.device, args.quant)

    out = run_patching(model, tok, args.device)
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\n{out['n_pairs']} usable pairs; causal effect by layer "
          "(1.0 = patch fully flips prediction):")
    for c in out["curve"]:
        bar = "#" * max(0, int(c["effect"] * 40))
        print(f"  L{c['layer']:>2}: {c['effect']:+.3f}  {bar}")
    best = max(out["curve"], key=lambda c: c["effect"])
    print(f"peak causal layer: L{best['layer']} effect={best['effect']:.3f} -> {args.out}")


if __name__ == "__main__":
    main()
