"""Read the residual stream DURING the attempt, not at the confidence token.

The reviewer objection this answers: probing at the confidence digit shows the model
has an error judgment available *when asked for one*. It does not show the judgment
existed while the model was solving. This script adds the missing read site.

It needs no generation. An existing cell's meta.jsonl stores the full turn-2 context
and the full answer text, so we rebuild the exact conversation, teacher-force the
answer, and read at:

  answer_last  the final answer token (the natural "during the attempt" site)
  answer_traj  N evenly spaced positions across the answer span, so a layer x token
               trajectory can be plotted and the signal's onset located

One forward pass per record. On Mistral-Small-24B x MATH (750 records) this is well
under an hour, against 5.4 h for the original generate-three-turns capture.

CAVEAT, stated here and in the paper: the original capture saved activations from the
*realized* generated token ids, while this script re-tokenizes the decoded answer text.
Detok/retok drift means a given position may not correspond to exactly the same token
the model generated. The final-token read is robust to this (the answer's last token is
stable); the trajectory should be read as approximate. Re-running capture_qa.py with an
answer-site read built in would remove the caveat and cost a full recapture.

Usage:
  python -m interp.capture_answer_site \
      --meta interp/activations/fix_mistral_math/meta.jsonl \
      --task math --model mistralai/Mistral-Small-24B-Instruct-2501 \
      --per-turn-think --out-dir interp/activations/ansite_mistral_math
"""
from __future__ import annotations

import argparse
import json
import pathlib


def _num_hidden_layers(model) -> int:
    cfg = model.config
    for k in ("num_hidden_layers", "n_layer", "num_layers"):
        if hasattr(cfg, k):
            return int(getattr(cfg, k))
    raise RuntimeError("cannot determine layer count")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True, help="meta.jsonl of an existing capture cell")
    ap.add_argument("--task", required=True, help="a QA_TASKS key")
    ap.add_argument("--model", required=True)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none")
    ap.add_argument("--layers", default="all")
    ap.add_argument("--n-traj", type=int, default=16,
                    help="evenly spaced positions across the answer to keep (0 = last token only)")
    ap.add_argument("--limit", type=int, default=0, help="cap records (0 = all)")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--per-turn-think", action="store_true")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    import numpy as np
    import torch

    from interp.capture import capture_activations, resolve_layers
    from interp.capability_check import load_model
    from interp.tasks_qa import QA_TASKS, QA_PRETASK_QUERY

    task = QA_TASKS[args.task]
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_out = out_dir / "meta.jsonl"

    records = [json.loads(l) for l in pathlib.Path(args.meta).open()]
    if args.limit:
        records = records[: args.limit]

    tok, model = load_model(args.model, args.device, args.quant)
    n_hs = _num_hidden_layers(model) + 1
    layers = resolve_layers(args.layers, n_hs)
    answer_think = True if args.per_turn_think else (False if args.no_think else None)

    _tmpl = tok
    if getattr(tok, "chat_template", None) is None:
        from transformers import AutoProcessor
        _tmpl = AutoProcessor.from_pretrained(args.model)

    sys_prompt = task["system"]()
    pre_q = task.get("pretask_query", QA_PRETASK_QUERY)

    def render_ids(msgs):
        kw = {} if answer_think is None else {"enable_thinking": answer_think}
        text = _tmpl.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **kw)
        return tok(text, return_tensors="pt").input_ids[0].tolist()

    done = {p.stem for p in out_dir.glob("*.npz")}
    print(f"{len(records)} records | {n_hs} hidden states | {len(layers)} layers kept "
          f"| resuming past {len(done)}")

    n_saved = 0
    with meta_out.open("a") as mf:
        for i, rec in enumerate(records, 1):
            rid = rec["pid"]
            if rid in done:
                continue
            answer = rec.get("answer") or ""
            if not answer.strip():
                print(f"[{i:>3}/{len(records)}] {rid} SKIP (no answer text)")
                continue
            try:
                # exactly the turn-2 context capture_qa.py built
                base = ([{"role": "system", "content": sys_prompt}] if sys_prompt else [])
                base = base + [{"role": "user", "content": rec["prompt"]}]
                msgs_pre = [dict(m) for m in base]
                msgs_pre[-1]["content"] = (msgs_pre[-1]["content"] or "") + "\n\n" + pre_q
                msgs_task = list(msgs_pre) + [
                    {"role": "assistant", "content": rec.get("pre_completion") or ""},
                    {"role": "user", "content": task["answer_query"]}]

                prompt_ids = render_ids(msgs_task)
                comp_ids = tok(answer, add_special_tokens=False).input_ids
                cap = capture_activations(model, tok, prompt_ids, comp_ids, layers, args.device)
                if cap is None:
                    print(f"[{i:>3}/{len(records)}] {rid} SKIP (empty completion)")
                    continue

                acts = cap["acts"]                       # [n_layers, n_tokens, d]
                n_tok = acts.shape[1]
                save = {"answer_last": acts[:, -1, :].astype(np.float16),
                        "layer_ids": np.array(layers),
                        "n_answer_tokens": np.array(n_tok)}
                if args.n_traj > 0 and n_tok > 1:
                    idx = np.unique(np.linspace(0, n_tok - 1, args.n_traj).round().astype(int))
                    save["answer_traj"] = acts[:, idx, :].astype(np.float16)
                    save["traj_pos"] = idx
                    save["traj_frac"] = (idx / max(n_tok - 1, 1)).astype(np.float32)
                np.savez_compressed(out_dir / f"{rid}.npz", **save)

                mf.write(json.dumps({
                    "pid": rid,
                    "grade": rec["grade"],
                    "post_conf": rec.get("post_conf"),
                    "pre_conf": rec.get("pre_conf"),
                    "p_true": rec.get("p_true"),
                    "mean_logp_answer": rec.get("mean_logp_answer"),
                    "n_answer_tokens": int(n_tok),
                    "answer_chars": len(answer),
                    "site": "answer",
                }) + "\n")
                mf.flush()
                n_saved += 1
                print(f"[{i:>3}/{len(records)}] {rid} tokens={n_tok} ok={rec['grade']['ok']}")
                if args.device == "cuda":
                    torch.cuda.empty_cache()
            except Exception as e:  # noqa: BLE001 — never lose the run over one record
                print(f"[{i:>3}/{len(records)}] ERROR {rid}: {type(e).__name__}: {e}")
                continue

    print(f"saved {n_saved} records -> {out_dir}")


if __name__ == "__main__":
    main()
