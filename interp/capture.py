"""
Phase 1 — activation capture harness.

For each geometry prompt: generate a construction with the local model, grade it
through the render-free pipeline (interp.grade), then run ONE forward pass over
[prompt + completion] and save the residual stream at every (or a chosen subset
of) layer, for the completion token positions. Each saved record carries enough
metadata — per-token char offsets + the parsed RecipeDSL + the grade — for the
probe stage (interp.probe) to derive per-position geometric labels offline.

Design notes
------------
* Residual stream is read from ``output_hidden_states=True`` (the model's own
  per-layer hidden states: embeddings + one tensor per decoder layer). No manual
  hooks needed, and it works for any HF CausalLM (incl. Qwen2.5).
* ALIGNMENT: we decode the generated text, then re-tokenize it with
  ``return_offsets_mapping`` and run the capture forward pass over THOSE ids.
  This guarantees the activation at position p corresponds to the token whose
  char span we stored — detokenize/retokenize drift can't desync labels.
* We save only the COMPLETION positions by default (where the model writes the
  construction); the long few-shot prompt prefix is not what we probe.
* Storage: float16, one ``.npz`` per prompt + a single ``meta.jsonl``.

Runs on CPU/MPS/CUDA; the real (many-prompt, all-layer) capture is a GPU job.
    python interp/capture.py --device cuda --tier 1 --n 100 --few-shot relevant:4 \
        --only-valid --out-dir interp/activations/tier1
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from interp.grade import grade_completion  # noqa: E402


def resolve_layers(spec: str, n_hidden_states: int) -> list[int]:
    """Turn a --layers spec into concrete hidden-state indices.

    n_hidden_states = num_hidden_layers + 1 (index 0 = embeddings, i = layer i out).
    spec: "all" | "even" | comma list like "0,8,16,24" | "every:4".
    """
    last = n_hidden_states - 1
    if spec == "all":
        return list(range(n_hidden_states))
    if spec == "even":
        return list(range(0, n_hidden_states, 2))
    if spec.startswith("every:"):
        step = int(spec.split(":", 1)[1])
        return list(range(0, n_hidden_states, step))
    out = sorted({int(x) for x in spec.split(",") if x.strip() != ""})
    bad = [i for i in out if not (0 <= i <= last)]
    if bad:
        raise ValueError(f"layer indices out of range 0..{last}: {bad}")
    return out


def capture_activations(model, tok, prompt_text: str, completion_text: str,
                        layers, device: str):
    """Pure capture core (no generation): forward [prompt + completion] once and
    return the residual stream at ``layers`` for the completion positions.

    Returns a dict:
      acts          float16 ndarray [n_layers, n_completion_tokens, d_model]
      layer_ids     list[int]                  the hidden-state indices saved
      tokens        list[str]                  decoded piece per completion token
      offsets       list[[start,end]]          char span of each token in completion_text
      prompt_len    int                        # prompt tokens (completion starts after)
    """
    import numpy as np
    import torch

    prompt_ids = tok(prompt_text, add_special_tokens=False).input_ids
    comp_enc = tok(completion_text, add_special_tokens=False, return_offsets_mapping=True)
    comp_ids = comp_enc.input_ids
    offsets = [list(o) for o in comp_enc["offset_mapping"]]
    if len(comp_ids) == 0:
        return None  # nothing generated to probe

    input_ids = torch.tensor([prompt_ids + comp_ids], device=device)
    with torch.no_grad():
        out = model(input_ids, output_hidden_states=True, use_cache=False)
    hs = out.hidden_states  # tuple len = n_hidden_states, each [1, seq, d_model]

    p = len(prompt_ids)
    sel = []
    for li in layers:
        layer = hs[li][0, p:, :]           # [n_completion_tokens, d_model]
        sel.append(layer.to(torch.float16).cpu().numpy())
    acts = np.stack(sel, axis=0)           # [n_layers, n_comp_tokens, d_model]

    tokens = [tok.convert_ids_to_tokens(t) for t in comp_ids]
    return {
        "acts": acts,
        "layer_ids": list(layers),
        "tokens": tokens,
        "offsets": offsets,
        "prompt_len": p,
    }


def run_capture(args) -> None:
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from interp.capability_check import (
        build_messages,
        load_catalog_recipes,
        load_prompts,
        select_recipes,
    )

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.jsonl"

    prompts = load_prompts(args.n, args.tier)
    all_recipes = [] if args.few_shot == "none" else load_catalog_recipes()
    print(f"capturing from {len(prompts)} prompt(s)"
          + (f" (tier {args.tier})" if args.tier else "")
          + f"; few-shot={args.few_shot}; out={out_dir}")

    print(f"loading {args.model} on {args.device} (bf16) ...")
    tok = AutoTokenizer.from_pretrained(args.model)
    model = (
        AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16)
        .to(args.device)
        .eval()
    )
    n_hs = model.config.num_hidden_layers + 1
    layers = resolve_layers(args.layers, n_hs)
    print(f"model has {n_hs} hidden states; saving layers {layers}")

    n_saved = 0
    with meta_path.open("w") as meta_f:
        for i, (pid, prompt) in enumerate(prompts, 1):
            recipes = select_recipes(prompt, all_recipes, args.few_shot)
            text = tok.apply_chat_template(
                build_messages(prompt, recipes), tokenize=False, add_generation_prompt=True
            )
            inputs = tok(text, return_tensors="pt").to(args.device)
            with torch.no_grad():
                gen = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                                     do_sample=False)
            completion = tok.decode(gen[0][inputs.input_ids.shape[1]:],
                                    skip_special_tokens=True)
            del gen, inputs
            if args.device == "mps":
                torch.mps.empty_cache()
            elif args.device == "cuda":
                torch.cuda.empty_cache()

            grade = grade_completion(completion)
            if args.only_valid and not grade.ok:
                print(f"[{i:>3}/{len(prompts)}] skip {pid} (grade {grade.stage})")
                continue

            cap = capture_activations(model, tok, text, completion, layers, args.device)
            if cap is None:
                print(f"[{i:>3}/{len(prompts)}] skip {pid} (empty completion)")
                continue

            np.savez_compressed(
                out_dir / f"{pid}.npz",
                acts=cap["acts"],
                layer_ids=np.array(cap["layer_ids"]),
                offsets=np.array(cap["offsets"]),
            )
            meta_f.write(json.dumps({
                "pid": pid,
                "prompt": prompt,
                "completion": completion,
                "tokens": cap["tokens"],
                "grade": {"ok": grade.ok, "stage": grade.stage, "n_ops": grade.n_ops},
                "construction": _safe_construction(completion),
                "acts_shape": list(cap["acts"].shape),
                "layer_ids": cap["layer_ids"],
            }) + "\n")
            meta_f.flush()
            n_saved += 1
            print(f"[{i:>3}/{len(prompts)}] saved {pid}  acts={cap['acts'].shape}  "
                  f"grade={'OK' if grade.ok else grade.stage}")

    print(f"\ncaptured {n_saved} prompt(s) -> {out_dir} (+ {meta_path.name})")


def _safe_construction(completion: str):
    """The parsed RecipeDSL construction list, or None — for offline labeling."""
    try:
        from interp.grade import extract_recipe_json
        obj = extract_recipe_json(completion)
        return obj.get("construction") if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--few-shot", default="relevant:4",
                    help="exemplar selection (see capability_check.select_recipes)")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--layers", default="all",
                    help="'all' | 'even' | 'every:K' | comma list of hidden-state indices")
    ap.add_argument("--only-valid", action="store_true",
                    help="capture only completions that grade OK (clean probe set)")
    ap.add_argument("--out-dir", default="interp/activations/run")
    args = ap.parse_args()
    run_capture(args)


if __name__ == "__main__":
    main()
