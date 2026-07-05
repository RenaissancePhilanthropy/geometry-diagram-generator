"""
3-turn TEMPORAL confidence capture for QA benchmarks (MMLU, MedQA, GSM8K, ...).

Same pre -> answer -> post structure and the SAME meta.jsonl / npz output as
capture_temporal.py (geometry), so interp/analysis/confidence_temporal.py analyzes
both identically. The task (load / prompt / grade) is pulled from
interp.tasks_qa.QA_TASKS[--task]; everything else (confidence turns, residual-stream
reads, resumability) is shared. Arch-agnostic + VLM-aware via load_model.

    interp/.venv/bin/python interp/capture_qa.py --task medqa --device cuda \
        --model Qwen/Qwen3.6-27B --n 250 --samples 2 --no-think \
        --out-dir interp/activations/qwen36_medqa
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
    from interp.capability_check import load_model
    from interp.confidence import (build_pretask_turn, CONFIDENCE_QUERY,
                                   parse_confidence, confidence_read_positions)
    from interp.tasks_qa import QA_TASKS

    task = QA_TASKS[args.task]
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.jsonl"

    items = task["load"](args.n, args.seed)
    tok, model = load_model(args.model, args.device, args.quant)
    n_hs = _num_hidden_layers(model) + 1
    layers = resolve_layers(args.layers, n_hs)
    tmpl = {"enable_thinking": False} if args.no_think else {}
    _tmpl = tok
    if getattr(tok, "chat_template", None) is None:            # VLMs template via the processor
        try:
            from transformers import AutoProcessor
            _tmpl = AutoProcessor.from_pretrained(args.model)
            print("  (no tokenizer chat_template -> using AutoProcessor)")
        except Exception as e:  # noqa: BLE001
            print(f"  (WARN: no processor template: {e})")
    sys_prompt = task["system"]()
    print(f"task={args.task} | {len(items)} items x {args.samples} samples | {n_hs} hidden states")

    def _empty():
        if args.device == "cuda":
            torch.cuda.empty_cache()
        elif args.device == "mps":
            torch.mps.empty_cache()

    def render(msgs):
        text = _tmpl.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **tmpl)
        return tok(text, return_tensors="pt").input_ids

    def gen(ids, max_new):
        ids = ids.to(args.device)
        kw = {"temperature": args.temperature, "top_p": 0.95} if args.samples > 1 else {}
        with torch.no_grad():
            g = model.generate(ids, max_new_tokens=max_new, do_sample=args.samples > 1, **kw)
        out = g[0].tolist()[ids.shape[1]:]
        del g
        return out

    def dtoken(prompt_ids, comp_ids):
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
    with meta_path.open("a") as mf:
        for i, item in enumerate(items, 1):
            base = ([{"role": "system", "content": sys_prompt}] if sys_prompt else [])
            base = base + [{"role": "user", "content": task["prompt"](item)}]
            for s in range(args.samples):
                rid = item["id"] if args.samples == 1 else f'{item["id"]}_s{s}'
                if rid in done:
                    continue
                try:
                    if args.samples > 1:
                        torch.manual_seed(1000 + s)
                    # pre-task, no-elicitation read (last prompt token)
                    base_ids = render(base)
                    with torch.no_grad():
                        hs = model(base_ids.to(args.device), output_hidden_states=True).hidden_states
                    prompt_dtoken = np.stack([hs[L][0, -1, :].float().cpu().numpy()
                                              for L in layers]).astype(np.float16)
                    del hs
                    _empty()
                    # turn 1 — pre-confidence
                    msgs_pre = build_pretask_turn(base)
                    pre_ids = render(msgs_pre)
                    pre_c = gen(pre_ids, args.conf_max_new_tokens)
                    pre_completion = tok.decode(pre_c, skip_special_tokens=True)
                    pre_conf = parse_confidence(pre_completion)
                    pre_dtoken, pre_ok = dtoken(pre_ids[0].tolist(), pre_c)
                    _empty()
                    # turn 2 — answer
                    msgs_task = list(msgs_pre) + [
                        {"role": "assistant", "content": pre_completion},
                        {"role": "user", "content": task["answer_query"]}]
                    task_ids = render(msgs_task)
                    ans_c = gen(task_ids, args.max_new_tokens)
                    answer = tok.decode(ans_c, skip_special_tokens=True)
                    ok = bool(task["grade"](answer, item))
                    _empty()
                    # turn 3 — post-confidence
                    msgs_post = list(msgs_task) + [
                        {"role": "assistant", "content": answer},
                        {"role": "user", "content": CONFIDENCE_QUERY}]
                    post_ids = render(msgs_post)
                    post_c = gen(post_ids, args.conf_max_new_tokens)
                    post_completion = tok.decode(post_c, skip_special_tokens=True)
                    post_conf = parse_confidence(post_completion)
                    post_dtoken, post_ok = dtoken(post_ids[0].tolist(), post_c)
                    _empty()

                    save = {"prompt_dtoken": prompt_dtoken, "layer_ids": np.array(layers)}
                    if pre_dtoken is not None:
                        save["pre_dtoken"] = pre_dtoken
                    if post_dtoken is not None:
                        save["post_dtoken"] = post_dtoken
                    np.savez_compressed(out_dir / f"{rid}.npz", **save)
                    mf.write(json.dumps({
                        "pid": rid, "prompt": task["prompt"](item)[:300],
                        "pre_conf": pre_conf, "post_conf": post_conf,
                        "grade": {"ok": ok, "stage": "correct" if ok else "incorrect", "n_ops": None},
                        "answer": answer[:200], "gold": item.get("answer"),
                        "pre_read_ok": pre_ok, "post_read_ok": post_ok,
                        "ground_truth": {"stage": "na", "entity_relations": {},
                                         "point_coords": {}, "vertex_angles": {}},
                    }) + "\n")
                    mf.flush()
                    n_saved += 1
                    print(f"[{i:>3}/{len(items)}] {rid} ok={ok} pre={pre_conf} post={post_conf}")
                except Exception as e:  # noqa: BLE001
                    print(f"[{i:>3}/{len(items)}] ERROR {rid}: {type(e).__name__}: {e}")
                    _empty()
                    continue
    print(f"\ncaptured {n_saved} record(s) -> {out_dir}")


def main() -> None:
    from interp.tasks_qa import QA_TASKS
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=list(QA_TASKS))
    ap.add_argument("--model", default="Qwen/Qwen3.6-27B")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--max-new-tokens", type=int, default=512)
    ap.add_argument("--conf-max-new-tokens", type=int, default=24)
    ap.add_argument("--layers", default="all")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--out-dir", default="interp/activations/qa")
    ap.add_argument("--seed", type=int, default=0)
    run(ap.parse_args())


if __name__ == "__main__":
    main()
