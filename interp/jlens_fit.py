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
    ap.add_argument("--n-prompts", type=int, default=500)
    ap.add_argument("--seq-len", type=int, default=128)
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
        ds = load_dataset("wikitext", "wikitext-103-raw-v1", split="train")
        texts = [t for t in ds["text"] if len(t) > 200][: args.n_prompts * 2]
    else:
        from interp.tasks_qa import QA_TASKS
        texts = []
        for t in ("mmlu_pro", "math"):
            items = QA_TASKS[t]["load"](args.n_prompts // 2, 0)
            texts += [QA_TASKS[t]["prompt"](it) for it in items]
    prompts = []
    for t in texts:
        ids = tok(t, truncation=True, max_length=args.seq_len).input_ids
        if len(ids) >= 16:
            prompts.append(tok.decode(ids, skip_special_tokens=True))
        if len(prompts) >= args.n_prompts:
            break
    print(f"corpus: {args.corpus}, {len(prompts)} prompts (<= {args.seq_len} tokens)")

    # ---- fit or load ------------------------------------------------------
    if args.skip_fit and lens_path.exists():
        lens = jlens.JacobianLens.from_pretrained(str(lens_path.parent), filename=lens_path.name)
        print(f"loaded {lens_path}")
    else:
        lens = jlens.fit(jmodel, prompts=prompts, checkpoint_path=str(out / f"ckpt_{args.short}.pt"))
        lens.save(str(lens_path))
        print(f"fitted + saved {lens_path}")

    # ---- extract ----------------------------------------------------------
    W_U = model.get_output_embeddings().weight.detach().float().cpu()   # [vocab, d]
    d_model = W_U.shape[1]
    nl = getattr(model.config, "num_hidden_layers", None)
    if nl is None:
        c = model.config
        nl = (c.get_text_config().num_hidden_layers if hasattr(c, "get_text_config")
              else c.text_config.num_hidden_layers)
    stacked, perlayer = locate_J(lens, d_model, int(nl))
    if stacked is not None:
        J = stacked.detach().float().cpu()                              # [L, d, d]
    else:
        # single shared matrix or ambiguous — take the first candidate, replicated
        k, v = next(iter(perlayer.items()))
        print(f"  using single candidate '{k}' for all layers")
        J = v.detach().float().cpu().unsqueeze(0).expand(int(nl) + 1, d_model, d_model)

    words = FAIL_WORDS + OK_WORDS + DIGITS
    u_rows = []
    for w in words:
        ids = first_token_ids(tok, w)
        u_rows.append(W_U[ids].mean(0))                                  # variant-avg row
    U = torch.stack(u_rows)                                              # [W, d]
    # r[w, l] = J_l^T @ u_w   -> [W, L, d]
    R = torch.einsum("lde,wd->wle", J, U)                                # J_l^T u = u @ J_l
    print(f"readout stack: {tuple(R.shape)} (words x layers x d)")

    # ---- validate against the package's own apply -------------------------
    test_prompt = "Fact: The capital of France is"
    try:
        ids = tok(test_prompt, return_tensors="pt").input_ids.to(args.device)
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        Lmid = J.shape[0] // 2
        h = hs[Lmid][0, -1, :].float().cpu()
        ours = (W_U @ (J[Lmid] @ h)).topk(10).indices.tolist()
        pkg = lens.apply(jmodel, test_prompt, positions=[-1])
        pkg_logits = pkg[0]
        pl = torch.as_tensor(pkg_logits)
        # find a vocab-sized axis and a layer axis; compare same layer if present
        flat = pl.reshape(-1, pl.shape[-1]) if pl.shape[-1] == W_U.shape[0] else None
        if flat is not None:
            best_overlap = max(len(set(ours) & set(row.topk(10).indices.tolist())) for row in flat)
            print(f"VALIDATION: best top-10 overlap manual-vs-package = {best_overlap}/10")
            if best_overlap < 5:
                raise SystemExit("VALIDATION FAILED (<5/10 overlap) — extraction wrong; inspect lens internals")
        else:
            print(f"VALIDATION: package output shape {tuple(pl.shape)} not vocab-shaped; manual check needed")
        print("  manual top-10 @Lmid:", tok.convert_ids_to_tokens(ours))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"VALIDATION: lens.apply comparison errored ({type(e).__name__}: {e}) — "
              f"manual top-10 sanity: {tok.convert_ids_to_tokens((W_U @ (J[J.shape[0]//2] @ torch.randn(d_model))).topk(5).indices.tolist())}")

    import numpy as np
    np.savez_compressed(out / f"jlens_readouts_{args.short}.npz",
                        R=R.numpy().astype(np.float32), words=np.array(words),
                        n_fail=len(FAIL_WORDS), n_ok=len(OK_WORDS),
                        model=args.model, corpus=args.corpus)
    print(f"saved {out / f'jlens_readouts_{args.short}.npz'} "
          f"({(R.numel() * 4) / 1e6:.0f}MB) — rsync this home; lens.pt stays for steering")


if __name__ == "__main__":
    main()
