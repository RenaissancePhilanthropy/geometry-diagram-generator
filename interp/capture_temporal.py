"""
3-turn TEMPORAL confidence capture: pre-task -> task -> post-task.

For each prompt we run three turns and record everything the calibration /
self-correction analyses need:

  Turn 1  pre-task  : "before you attempt it, how confident (0-100)?"  -> pre_conf
  Turn 2  task      : produce the construction                          -> grade ok/fail
  Turn 3  post-task : "now how confident that it's correct?"            -> post_conf

The headline analyses (does low confidence predict failure? is post better
calibrated than pre? does the model revise DOWN on failures?) need only the two
numbers + the grade — always recorded to meta.jsonl. Residual-stream reads are
captured too, at content-neutral "Confidence:" decision tokens:
  - prompt_dtoken : last task-prompt token BEFORE any generation (pre-task
                    internal signal with NO elicitation -> no anchoring)
  - pre_dtoken    : the turn-1 pre-confidence decision token
  - post_dtoken   : the turn-3 post-confidence decision token
  - (optional) construction entity tokens for the during-trajectory

Arch-agnostic (uses output_hidden_states); works on Qwen3.6 (hybrid), GLM, Qwen2.5.
Run on a GPU box:
    interp/.venv/bin/python interp/capture_temporal.py --device cuda \
        --model Qwen/Qwen3.6-27B --n 200 --samples 2 --no-think \
        --out-dir interp/activations/qwen36_temporal
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

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


def run(args) -> None:
    import numpy as np
    import torch

    from interp.capture import capture_activations, resolve_layers
    from interp.capability_check import (build_messages, load_catalog_recipes,
                                         load_model, load_prompts, select_recipes)
    from interp.confidence import (build_pretask_turn, build_task_turn,
                                   build_posttask_turn, parse_confidence,
                                   confidence_read_positions)
    from interp.grade import grade_completion, extract_recipe_json
    from interp.geometry_labels import ground_truth, entity_ids, id_positions

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.jsonl"

    prompts = load_prompts(args.n, args.tier)
    all_recipes = [] if args.few_shot == "none" else load_catalog_recipes()
    tok, model = load_model(args.model, args.device, args.quant)
    n_hs = _num_hidden_layers(model) + 1
    layers = resolve_layers(args.layers, n_hs)
    tmpl = {"enable_thinking": False} if args.no_think else {}
    _tmpl_obj = tok                                   # VLMs template via the processor, not the tokenizer
    if getattr(tok, "chat_template", None) is None:
        try:
            from transformers import AutoProcessor
            _tmpl_obj = AutoProcessor.from_pretrained(args.model)
            print("  (no tokenizer chat_template -> using AutoProcessor for chat templating)")
        except Exception as e:  # noqa: BLE001
            print(f"  (WARN: no processor chat template available: {e})")
    print(f"{len(prompts)} prompts x {args.samples} samples | {n_hs} hidden states; "
          f"layers {layers[:3]}..{layers[-1]} | no_think={args.no_think} | keep={args.keep_positions}")

    def _empty():
        if args.device == "cuda":
            torch.cuda.empty_cache()
        elif args.device == "mps":
            torch.mps.empty_cache()

    def render(msgs) -> list[int]:
        text = _tmpl_obj.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **tmpl)
        return tok(text, return_tensors="pt").input_ids

    def generate(ids, max_new: int) -> list[int]:
        ids = ids.to(args.device)
        with torch.no_grad():
            if args.samples > 1:
                g = model.generate(ids, max_new_tokens=max_new, do_sample=True,
                                   temperature=args.temperature, top_p=0.95)
            else:
                g = model.generate(ids, max_new_tokens=max_new, do_sample=False)
        out = g[0].tolist()[ids.shape[1]:]
        del g
        return out

    def decision_acts(prompt_ids, comp_ids):
        """Capture at the 'Confidence:' decision token of a completion. Returns
        ([L, D] float16 or None, ok_bool)."""
        cap = capture_activations(model, tok, prompt_ids, comp_ids, layers, args.device)
        if cap is None:
            return None, False
        dpos, _ = confidence_read_positions(cap["completion"], cap["offsets"])
        n = cap["acts"].shape[1]
        if dpos is None or not (0 <= dpos < n):
            return None, False
        return cap["acts"][:, dpos, :].astype(np.float16), True

    done = {p.stem for p in out_dir.glob("*.npz")}
    if done:
        print(f"resuming: {len(done)} records already present, skipping them")
    n_saved = 0
    with meta_path.open("a") as meta_f:
        for i, (pid, prompt) in enumerate(prompts, 1):
            recipes = select_recipes(prompt, all_recipes, args.few_shot)
            base = build_messages(prompt, recipes)
            for s in range(args.samples):
                rid = pid if args.samples == 1 else f"{pid}_s{s}"
                if rid in done:
                    continue
                try:
                    if args.samples > 1:
                        torch.manual_seed(1000 + s)

                    # pre-task internal signal WITHOUT elicitation: last prompt token
                    base_ids = render(base)
                    with torch.no_grad():
                        hs = model(base_ids.to(args.device), output_hidden_states=True).hidden_states
                    prompt_dtoken = np.stack([h[0, -1, :].float().cpu().numpy()
                                              for h in [hs[L] for L in layers]]).astype(np.float16)
                    del hs
                    _empty()

                    # TURN 1 — pre-task confidence
                    msgs_pre = build_pretask_turn(base)
                    pre_ids = render(msgs_pre)
                    pre_comp = generate(pre_ids, args.conf_max_new_tokens)
                    pre_completion = tok.decode(pre_comp, skip_special_tokens=True)
                    pre_conf = parse_confidence(pre_completion)
                    pre_dtoken, pre_ok = decision_acts(pre_ids[0].tolist(), pre_comp)
                    _empty()

                    # TURN 2 — construction
                    msgs_task = build_task_turn(msgs_pre, pre_completion)
                    task_ids = render(msgs_task)
                    task_comp = generate(task_ids, args.max_new_tokens)
                    construction = tok.decode(task_comp, skip_special_tokens=True)
                    grade = grade_completion(construction)
                    obj = extract_recipe_json(construction)
                    gt = ground_truth(obj)
                    _empty()

                    # optional construction reads (entity tokens) for the trajectory
                    task_acts = None
                    task_positions = None
                    if args.keep_positions in ("entities", "all"):
                        tcap = capture_activations(model, tok, task_ids[0].tolist(), task_comp,
                                                   layers, args.device)
                        if tcap is not None:
                            if args.keep_positions == "all":
                                keep = list(range(tcap["acts"].shape[1]))
                            else:
                                keep = sorted({p for eid in entity_ids(gt)
                                               for p in id_positions(tcap["completion"],
                                                                     tcap["offsets"], eid)
                                               if 0 <= p < tcap["acts"].shape[1]})
                            if keep:
                                task_acts = tcap["acts"][:, keep, :].astype(np.float16)
                                task_positions = np.array(keep)
                        _empty()

                    # TURN 3 — post-task confidence
                    msgs_post = build_posttask_turn(msgs_task, construction)
                    post_ids = render(msgs_post)
                    post_comp = generate(post_ids, args.conf_max_new_tokens)
                    post_completion = tok.decode(post_comp, skip_special_tokens=True)
                    post_conf = parse_confidence(post_completion)
                    post_dtoken, post_ok = decision_acts(post_ids[0].tolist(), post_comp)
                    _empty()

                    save = {"prompt_dtoken": prompt_dtoken, "layer_ids": np.array(layers)}
                    if pre_dtoken is not None:
                        save["pre_dtoken"] = pre_dtoken
                    if post_dtoken is not None:
                        save["post_dtoken"] = post_dtoken
                    if task_acts is not None:
                        save["task_acts"] = task_acts
                        save["task_positions"] = task_positions
                    np.savez_compressed(out_dir / f"{rid}.npz", **save)

                    meta_f.write(json.dumps({
                        "pid": rid, "prompt": prompt,
                        "pre_conf": pre_conf, "post_conf": post_conf,
                        "grade": {"ok": grade.ok, "stage": grade.stage, "n_ops": grade.n_ops},
                        "pre_completion": pre_completion[:200],
                        "construction": construction,
                        "post_completion": post_completion[:200],
                        "pre_read_ok": pre_ok, "post_read_ok": post_ok,
                        "ground_truth": {
                            "stage": gt["stage"],
                            "entity_relations": gt["entity_relations"],
                            "point_coords": gt["point_coords"],
                            "vertex_angles": gt.get("vertex_angles", {}),
                        },
                    }) + "\n")
                    meta_f.flush()
                    n_saved += 1
                    print(f"[{i:>3}/{len(prompts)}] {rid}  grade={'OK' if grade.ok else grade.stage}"
                          f"  pre={pre_conf} post={post_conf}")
                except Exception as e:  # noqa: BLE001 — log & skip
                    print(f"[{i:>3}/{len(prompts)}] ERROR {rid}: {type(e).__name__}: {e}")
                    _empty()
                    continue

    print(f"\ncaptured {n_saved} record(s) -> {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.6-27B")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--few-shot", default="none")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--conf-max-new-tokens", type=int, default=24)
    ap.add_argument("--layers", default="all")
    ap.add_argument("--keep-positions", choices=("decisions", "entities", "all"), default="entities")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--out-dir", default="interp/activations/temporal")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
