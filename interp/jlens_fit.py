"""
Fit Anthropic's Jacobian lens on one of our models and extract WORD-READOUT VECTORS
for the metacognition study (task #16). Box-side half of the J-lens adapter; the
offline half is interp/analysis/jlens_score.py.

The lens (github.com/anthropics/jacobian-lens, Apache-2.0):
    lens_l(h) = unembed( J_l @ h ),   J_l = E[ dh_final / dh_l ]
i.e. a per-layer linear transport of a residual vector into the output basis. For a
word w with unembedding row u_w, the score of "disposed to say w later" collapses to
    score_w(h) = u_w · (J_l h) = (J_lᵀ u_w) · h  =  r_{w,l} · h
so all we need offline is the small stack of readout vectors r_{w,l} for our word set
(failure/success words + digits) — one dot product per saved activation record.

Pipeline here: fit (or load) lens -> locate the per-layer J matrices by shape
introspection -> build r vectors -> VALIDATE against the package's own lens.apply on
a test prompt (top-k overlap; hard-fails if extraction is wrong) -> save
jlens_readouts_<short>.npz (~15MB, rsync home) + keep lens.pt on the box for steering.

    /venv/main/bin/python interp/jlens_fit.py --model mistralai/Mistral-Small-24B-Instruct-2501 \
        --short mistral --device cuda --corpus wikitext --n-prompts 500
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FAIL_WORDS = ["wrong", "incorrect", "error", "mistake", "false", "flawed"]
OK_WORDS = ["correct", "right", "true", "valid", "accurate"]
DIGITS = [str(i) for i in range(10)]
# Geometry-domain vocabulary: enables (a) mid-construction thought-trajectories on the
# geometry cells' task_acts (entity-token snapshots) and (b) a zero-shot replication of
# the supervised entity_relation probe ("is it thinking 'midpoint' at point M?").
GEO_WORDS = ["perpendicular", "parallel", "midpoint", "circle", "tangent", "angle",
             "triangle", "segment", "intersection", "bisector", "radius", "vertex"]


def first_token_ids(tok, word):
    """First-token ids of 'word' and ' word' (tokenizer-robust variant set)."""
    out = set()
    for s in (word, " " + word):
        t = tok(s, add_special_tokens=False).input_ids
        if t:
            out.add(t[0])
    return sorted(out)


def locate_J(lens, d_model, n_layers):
    """Find the per-layer (d,d) Jacobian transport matrices inside the fitted lens by
    shape introspection (the repo is a reference impl; attribute names may vary).
    Returns a dict layer->tensor OR a stacked [L,d,d] tensor. Prints what it finds."""
    import torch
    state = {}
    if hasattr(lens, "state_dict"):
        try:
            state.update(lens.state_dict())
        except Exception:  # noqa: BLE001
            pass
    state.update({k: v for k, v in vars(lens).items() if not k.startswith("_")})
    stacked, perlayer = None, {}
    for k, v in state.items():
        if not hasattr(v, "shape"):
            continue
        if tuple(v.shape) == (n_layers + 1, d_model, d_model) or \
           tuple(v.shape) == (n_layers, d_model, d_model):
            stacked = v
            print(f"  found stacked J: '{k}' {tuple(v.shape)}")
        elif tuple(v.shape) == (d_model, d_model):
            perlayer[k] = v
            print(f"  found (d,d) candidate: '{k}'")
    if stacked is None and not perlayer:
        print("  !! no (L,d,d) or (d,d) tensors found. Lens attributes:")
        for k, v in state.items():
            print(f"     {k}: {tuple(v.shape) if hasattr(v, 'shape') else type(v).__name__}")
        raise SystemExit("cannot locate J matrices — inspect the printout and adapt locate_J()")
    return stacked, perlayer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--short", required=True, help="gemma4|qwen36|glm|mistral — output naming")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--corpus", choices=("wikitext", "task"), default="wikitext",
                    help="wikitext = generic (as Anthropic); task = our benchmark prompts")
    ap.add_argument("--n-prompts", type=int, default=200)
    ap.add_argument("--seq-len", type=int, default=128)
    ap.add_argument("--source-layers", default="0.7",
                    help="comma fractions of depth to fit, e.g. '0.15,0.7' (fitting all layers is ~L x slower)")
    ap.add_argument("--skip-first", type=int, default=16)
    ap.add_argument("--no-resume", action="store_true", help="discard any checkpoint and refit")
    ap.add_argument("--out-dir", default="interp/activations/jlens")
    ap.add_argument("--skip-fit", action="store_true", help="reuse saved lens.pt")
    ap.add_argument("--no-think", action="store_true")
    args = ap.parse_args()
    out = pathlib.Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    lens_path = out / f"lens_{args.short}.pt"

    import torch
    try:
        import jlens
    except ImportError:
        raise SystemExit("jlens not installed — pip install git+https://github.com/anthropics/jacobian-lens")
    from interp.capability_check import load_model

    tok, model = load_model(args.model, args.device, args.quant)
    model.eval()
    jmodel = jlens.from_hf(model, tok)

    # ---- corpus -----------------------------------------------------------
    if args.corpus == "wikitext":
        from datasets import load_dataset
        try:
            ds = load_dataset("Salesforce/wikitext", "wikitext-103-raw-v1", split="train")
        except Exception as e:  # noqa: BLE001 — corpus must never kill the queue again
            print(f"WARN: wikitext unavailable ({type(e).__name__}) — falling back to task corpus")
            args.corpus = "task"
        else:
            texts = [t for t in ds["text"] if len(t) > 200][: args.n_prompts * 2]
    if args.corpus == "task":
        from interp.tasks_qa import QA_TASKS
        texts = []
        for t in ("mmlu_pro", "math"):
            items = QA_TASKS[t]["load"](args.n_prompts // 2, 0)
            texts += [QA_TASKS[t]["prompt"](it) for it in items]
    prompts = []
    for t in texts:
        ids = tok(t, truncation=True, max_length=args.seq_len).input_ids
        if len(ids) > args.skip_first + 1:          # jlens discards skip_first warmup positions
            prompts.append(tok.decode(ids, skip_special_tokens=True))
        if len(prompts) >= args.n_prompts:
            break
    print(f"corpus: {args.corpus}, {len(prompts)} prompts (> {args.skip_first+1} tokens)")

    # ---- which source layers to fit (fractions of depth; fitting only what we read
    #      is ~L x faster than the whole model) --------------------------------------
    import numpy as np
    nl = getattr(model.config, "num_hidden_layers", None)
    if nl is None:
        c = model.config
        nl = (c.get_text_config().num_hidden_layers if hasattr(c, "get_text_config")
              else c.text_config.num_hidden_layers)
    nl = int(nl)
    layer_idxs = sorted({min(nl - 1, max(0, round(float(f) * nl))) for f in args.source_layers.split(",")})
    print(f"model layers={nl}; fitting source layers {layer_idxs}")

    # ---- fit or load ------------------------------------------------------
    ckpt = str(out / f"ckpt_{args.short}.pt")
    if args.skip_fit and lens_path.exists():
        lens = None
        for loader in (lambda: jlens.JacobianLens.load(str(lens_path)),            # this one works locally
                       lambda: torch.load(str(lens_path), map_location="cpu", weights_only=False),
                       lambda: jlens.JacobianLens.from_pretrained(str(lens_path.parent),
                                                                  filename=lens_path.name)):
            try:
                lens = loader(); break
            except Exception as e:  # noqa: BLE001
                print(f"  (loader failed: {type(e).__name__}: {str(e)[:80]})")
        if lens is None:
            raise SystemExit(f"could not load {lens_path}")
        print(f"loaded {lens_path} ({type(lens).__name__})")
    else:
        lens = jlens.fit(jmodel, prompts=prompts, source_layers=layer_idxs,
                         skip_first=args.skip_first, max_seq_len=args.seq_len,
                         resume=not args.no_resume, checkpoint_path=ckpt)
        lens.save(str(lens_path))
        print(f"fitted + saved {lens_path}")

    # ---- extract: lens.jacobians is a dict {source_layer: [d, d]} ----------
    W_U = model.get_output_embeddings().weight.detach().float().cpu()   # [vocab, d]
    d_model = W_U.shape[1]
    jac = lens.jacobians if isinstance(lens.jacobians, dict) else dict(enumerate(lens.jacobians))
    fit_layers = sorted(jac.keys())
    print(f"lens.jacobians source layers: {fit_layers}")

    words = FAIL_WORDS + OK_WORDS + DIGITS + GEO_WORDS
    U = torch.stack([W_U[first_token_ids(tok, w)].mean(0) for w in words])   # [W, d]
    # lens logit for word w at layer L is  u_w . (J_L h)  =>  readout r_{w,L} = J_L^T u_w,
    # and score = r . h. So R[w, L] = (U @ J_L) row-wise.
    R = np.zeros((len(words), len(fit_layers), d_model), np.float32)
    for li, L in enumerate(fit_layers):
        R[:, li, :] = (U @ jac[L].detach().float().cpu()).numpy()
    print(f"readout stack: {R.shape} (words x fit-layers x d)")

    # ---- validate against the package's own apply (correct orientation: W_U(J h)) --
    test = "Fact: The capital of France is one of the largest cities in Europe."
    try:
        ids = tok(test, return_tensors="pt").input_ids.to(args.device)
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        Lv = fit_layers[len(fit_layers) // 2]
        h = hs[Lv][0, -1, :].float().cpu()
        ours = (W_U @ (jac[Lv].detach().float().cpu() @ h)).topk(10).indices.tolist()
        pkg = lens.apply(jmodel, test, positions=[-1])
        pl = pkg[0][Lv] if isinstance(pkg[0], dict) else pkg[0]
        pl = torch.as_tensor(pl).flatten().float()[:W_U.shape[0]]
        ov = len(set(ours) & set(pl.topk(10).indices.tolist()))
        print(f"VALIDATION @layer{Lv}: manual-vs-package top-10 overlap = {ov}/10")
        print("  manual top-10:", tok.convert_ids_to_tokens(ours))
        if ov < 5:
            raise SystemExit("VALIDATION FAILED (<5/10) — extraction orientation wrong")
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"VALIDATION errored ({type(e).__name__}: {str(e)[:100]}) — gate skipped, inspect manually")

    np.savez_compressed(out / f"jlens_readouts_{args.short}.npz",
                        R=R, words=np.array(words), fit_layers=np.array(fit_layers),
                        n_fail=len(FAIL_WORDS), n_ok=len(OK_WORDS),
                        n_digits=len(DIGITS), n_geo=len(GEO_WORDS),
                        model=args.model, corpus=args.corpus)
    print(f"saved {out / f'jlens_readouts_{args.short}.npz'} ({R.nbytes/1e6:.0f}MB); "
          f"lens.pt stays for steering")


if __name__ == "__main__":
    main()
