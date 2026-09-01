"""
Reading-mode activation capture — no generation.

Forward-passes externally-authored construction texts (from build_corpus.py)
through a HF model and saves the residual stream at entity-name token
positions, in the exact .npz + meta.jsonl schema interp/probe.py consumes.

The text sits in the assistant slot after a short fixed user instruction, the
same regime as the original captures (which forward-passed [prompt +
self-generated completion]); the instruction is identical across formats so
format is the only varying factor.

One capture dir is written per format: <out>/<format>/{meta.jsonl, <pid>.npz}.
pid = figure_id (no _s suffix), so probe grouping by base prompt = grouping by
figure, consistent across formats.

Usage (pilot):
  interp/.venv/bin/python interp/transfer/capture_reading.py \
      --corpus interp/transfer/corpus --out interp/activations/transfer_q15 \
      --model Qwen/Qwen2.5-1.5B-Instruct --device mps
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

INSTRUCTION = ("Read the following geometric construction carefully and "
               "understand the figure it describes.")

FORMATS = ("recipe", "tikz", "svg", "english")


def _empty_cache(device: str) -> None:
    import torch
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()


def tokenize_item(tok, text: str):
    """Tokenize original text with exact char offsets (fast tokenizer)."""
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    return enc["input_ids"], [list(o) for o in enc["offset_mapping"]]


def spans_to_positions(id_spans: dict, offsets) -> list[int]:
    """Token indices overlapping any recorded entity-id char span."""
    keep = set()
    spans = [tuple(s) for lst in id_spans.values() for s in lst]
    for pos, (s, e) in enumerate(offsets):
        if s == e:
            continue
        if any(s < ce and e > cs for (cs, ce) in spans):
            keep.add(pos)
    return sorted(keep)


def capture_item(model, tok, prompt_ids, comp_ids, device: str):
    """One forward pass; residual stream at all hidden states, completion
    positions only. Mirrors interp.capture.capture_activations."""
    import torch
    input_ids = torch.tensor([prompt_ids + comp_ids], device=device)
    with torch.no_grad():
        out = model(input_ids, output_hidden_states=True, use_cache=False)
    p = len(prompt_ids)
    acts = torch.stack([h[0, p:, :] for h in out.hidden_states])  # [L+1, T, d]
    return acts.to(torch.float16).cpu().numpy()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--limit", type=int, default=0, help="max figures (0=all)")
    ap.add_argument("--max-tokens", type=int, default=3072,
                    help="skip items whose text exceeds this many tokens")
    args = ap.parse_args()

    from interp.capability_check import load_model

    corpus = pathlib.Path(args.corpus)
    figures = {f["figure_id"]: f
               for f in map(json.loads, open(corpus / "figures.jsonl"))}
    items = [json.loads(l) for l in open(corpus / "items.jsonl")]
    formats = [f for f in args.formats.split(",") if f]

    print(f"loading {args.model} on {args.device} ...", flush=True)
    tok, model = load_model(args.model, args.device)

    # fixed prompt: chat prefix up to (and including) the assistant header
    msgs = [{"role": "user", "content": INSTRUCTION}]
    prompt_text = tok.apply_chat_template(msgs, tokenize=False,
                                          add_generation_prompt=True)
    prompt_ids = tok(prompt_text, add_special_tokens=False)["input_ids"]

    n_states = model.config.num_hidden_layers + 1
    layer_ids = list(range(n_states))

    for fmt in formats:
        fmt_items = [it for it in items if it["format"] == fmt]
        if args.limit:
            fmt_items = fmt_items[: args.limit]
        out_dir = pathlib.Path(args.out) / fmt
        out_dir.mkdir(parents=True, exist_ok=True)
        meta_f = open(out_dir / "meta.jsonl", "w")
        kept = skipped = 0
        for it in fmt_items:
            fid, text = it["figure_id"], it["text"]
            comp_ids, offsets = tokenize_item(tok, text)
            if len(comp_ids) > args.max_tokens or not it["id_spans"]:
                skipped += 1
                continue
            positions = spans_to_positions(it["id_spans"], offsets)
            if not positions:
                skipped += 1
                continue
            acts = capture_item(model, tok, prompt_ids, comp_ids, args.device)
            _empty_cache(args.device)
            fig = figures[fid]
            np.savez_compressed(
                out_dir / f"{fid}.npz",
                acts=acts[:, positions, :],
                layer_ids=np.array(layer_ids),
                offsets=np.array(offsets),
                is_special=np.zeros(len(comp_ids), dtype=np.int8),
                positions=np.array(positions))
            gt = fig["ground_truth"]
            meta_f.write(json.dumps({
                "pid": fid,
                "prompt": prompt_text,
                "completion": text,
                "format": fmt,
                "template": fig["template"],
                "id_spans": it["id_spans"],
                "tokens": tok.convert_ids_to_tokens(comp_ids),
                "is_special": [0] * len(comp_ids),
                "grade": {"ok": True, "stage": "success",
                          "n_ops": len(fig["construction"]["construction"])},
                "conf_value": None, "conf_positions": [],
                "conf_decision_pos": None,
                "construction": fig["construction"]["construction"],
                "ground_truth": {
                    "stage": gt.get("stage"),
                    "entity_relations": gt.get("entity_relations", {}),
                    "point_coords": gt.get("point_coords", {}),
                    "vertex_angles": gt.get("vertex_angles", {}),
                    "relation_facts": gt.get("relation_facts", []),
                },
                "acts_shape": list(acts.shape),
                "layer_ids": layer_ids,
            }) + "\n")
            meta_f.flush()
            kept += 1
            if kept % 25 == 0:
                print(f"  [{fmt}] {kept}/{len(fmt_items)}", flush=True)
        meta_f.close()
        print(f"[{fmt}] captured {kept}, skipped {skipped} -> {out_dir}",
              flush=True)


if __name__ == "__main__":
    main()
