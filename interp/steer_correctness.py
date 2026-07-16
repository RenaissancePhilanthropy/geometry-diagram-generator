"""
H-DRIVER — is the correctness direction a MONITOR or a DRIVER?

steer_confidence.py steers at the turn-3 confidence token (answer already written) and reads
the STATED confidence. This steers the SAME diff-of-means correctness direction *during the
answer generation itself* and measures whether the model's ACTUAL CORRECTNESS moves.

  MONITOR: the direction is a readout — steering changes the report, not the answer.
  DRIVER : the direction is upstream of the answer — steer up (toward 'ok') and accuracy RISES.

The claim with teeth is the UP direction + a norm-matched RANDOM control that does nothing
(you can wreck a model with any big vector; you cannot make it *more accurate* with noise).
Answer-invariance is deliberately DROPPED here (we want the answer to change).

    python interp/steer_correctness.py --act-dir interp/activations/fix_mistral_math \
        --model mistralai/Mistral-Small-24B-Instruct-2501 --task math --device cuda \
        --coeffs="-8,-4,0,4,8" --n-eval 100 --per-turn-think
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _num_hidden_layers(model) -> int:
    c = model.config
    n = getattr(c, "num_hidden_layers", None)
    if n is None and hasattr(c, "get_text_config"):
        n = c.get_text_config().num_hidden_layers
    if n is None and hasattr(c, "text_config"):
        n = c.text_config.num_hidden_layers
    return int(n)


def _blocks(model, n_layers):
    """Arch-agnostic decoder-block list: the ModuleList whose length == layer count."""
    import torch.nn as nn
    for _, m in model.named_modules():
        if isinstance(m, nn.ModuleList) and len(m) == n_layers:
            return m
    raise SystemExit(f"no ModuleList of length {n_layers} found — inspect the arch")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--act-dir", required=True, help="captured cell used to FIT the direction")
    ap.add_argument("--model", required=True)
    ap.add_argument("--task", required=True, help="a QA_TASKS key, or 'geometry'")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--layer", default="fix", help="acts layer index, or 'fix' = round(0.7*n_layers)")
    ap.add_argument("--coeffs", default="-8,-4,0,4,8", help="multiples of the raw diff-of-means vector")
    ap.add_argument("--n-eval", type=int, default=100)
    ap.add_argument("--max-new-tokens", type=int, default=None, help="default 512 (QA) / 2048 (geometry)")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--per-turn-think", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    coeffs = [float(c) for c in args.coeffs.split(",")]
    geo = args.task == "geometry"
    max_new = args.max_new_tokens or (2048 if geo else 512)

    import torch
    from interp.capability_check import load_model
    think = True if args.per_turn_think else (False if args.no_think else None)

    tok, model = load_model(args.model, args.device, args.quant)
    model.eval()
    n_layers = _num_hidden_layers(model)
    Lacts = int(round(0.7 * n_layers)) if args.layer == "fix" else int(args.layer)
    block = _blocks(model, n_layers)[Lacts - 1]        # hidden_states[L] = output of block L-1
    _tmpl = tok
    if getattr(tok, "chat_template", None) is None:
        from transformers import AutoProcessor
        _tmpl = AutoProcessor.from_pretrained(args.model)

    # ---- task plumbing: build the answer prompt + grade ------------------------------
    if geo:
        from interp.capability_check import (build_messages, load_prompts,
                                             load_catalog_recipes, select_recipes)
        from interp.grade import grade_completion
        catalog = load_catalog_recipes()
        items = load_prompts(args.n_eval * 2, None)     # (pid, prompt) pairs
        def build(it):
            pid, prompt = it
            return build_messages(prompt, select_recipes(prompt, catalog, "none")), pid
        def grade(ans, it):
            return bool(grade_completion(ans).ok)
    else:
        from interp.tasks_qa import QA_TASKS
        task = QA_TASKS[args.task]
        sysp = task["system"]()
        items = task["load"](args.n_eval * 2, args.seed)
        def build(it):
            msgs = ([{"role": "system", "content": sysp}] if sysp else [])
            msgs += [{"role": "user", "content": task["prompt"](it) + "\n\n" + task["answer_query"]}]
            return msgs, it["id"]
        def grade(ans, it):
            return bool(task["grade"](ans, it))

    # ---- fit the correctness direction from the cell (held-out eval) -----------------
    d = pathlib.Path(args.act_dir)
    recs = [json.loads(l) for l in (d / "meta.jsonl").read_text().splitlines()]
    base = lambda pid: re.sub(r"_s\d+$", "", pid)
    X, y = [], []
    for r in recs:
        f = d / f"{r['pid']}.npz"
        if not f.exists():
            continue
        try:
            z = np.load(f)
        except (EOFError, OSError, ValueError):
            continue
        if "post_dtoken" in z:
            X.append(z["post_dtoken"][Lacts].astype(np.float32))
            y.append(1 if r["grade"]["ok"] else 0)
    X, y = np.stack(X), np.array(y)
    rng = np.random.default_rng(args.seed)
    if len(set(y.tolist())) < 2:
        raise SystemExit("fit cell is single-class — need both ok and fail to build the direction")
    w = (X[y == 1].mean(0) - X[y == 0].mean(0)).astype(np.float32)      # toward 'ok' = UP
    r = rng.standard_normal(w.shape[0]).astype(np.float32)
    r *= np.linalg.norm(w) / (np.linalg.norm(r) + 1e-8)                 # norm-matched control
    dt = model.dtype if hasattr(model, "dtype") else torch.float32
    print(f"model layers={n_layers}, steer at acts layer {Lacts} (block {Lacts-1}); "
          f"|w|={np.linalg.norm(w):.2f}; coeffs={coeffs}; task={args.task}")

    # ---- steering hook: add coeff*vec at the newest position each forward -------------
    state = {"vec": None}

    def hook(mod, inp, out):
        if state["vec"] is None:
            return out
        h = out[0] if isinstance(out, tuple) else out
        h[:, -1, :] = h[:, -1, :] + state["vec"]       # nudge each generated token
        return out

    handle = block.register_forward_hook(hook)

    def render(msgs):
        text = _tmpl.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True,
                                         **({"enable_thinking": think} if think is not None else {}))
        return tok(text, return_tensors="pt").input_ids.to(args.device)

    def run(msgs, vec_np, coeff):
        state["vec"] = None if coeff == 0.0 else torch.tensor(coeff * vec_np, dtype=dt, device=args.device)
        ids = render(msgs)
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=max_new, do_sample=False)
        return tok.decode(g[0].tolist()[ids.shape[1]:], skip_special_tokens=True)

    # ---- sweep: baseline (c=0), steer (w) and random (r) at each coeff ---------------
    ev = items[: args.n_eval]
    results = {}
    try:
        for dname, vec in (("steer", w), ("random", r)):
            for c in coeffs:
                if c == 0.0 and dname == "random":
                    continue                            # c=0 baseline shared
                oks = []
                for it in ev:
                    msgs, _pid = build(it)
                    ans = run(msgs, vec, c)
                    oks.append(grade(ans, it))
                acc = float(np.mean(oks))
                results[f"{dname}@{c}"] = {"acc": acc, "n": len(oks)}
                print(f"  {dname:>6} c={c:+6.1f} | accuracy={acc:.3f}  (n={len(oks)})")
    finally:
        handle.remove()

    base_acc = results.get("steer@0.0", {}).get("acc")
    up = [(c, results[f"steer@{c}"]["acc"]) for c in coeffs if c > 0 and f"steer@{c}" in results]
    print(f"\nbaseline acc={base_acc}; UP direction: {up}")
    print("STRONG result = accuracy RISES with +coeff while random stays flat.")
    out = args.out or str(d / "steer_correctness.json")
    pathlib.Path(out).write_text(json.dumps({
        "model": args.model, "task": args.task, "layer_acts": Lacts, "coeffs": coeffs,
        "n_eval": len(ev), "baseline_acc": base_acc, "results": results}, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
