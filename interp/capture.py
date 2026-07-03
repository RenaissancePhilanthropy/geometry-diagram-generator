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


def _char_offsets(tok, comp_ids: list[int]) -> tuple[list[list[int]], str]:
    """Char span of each completion token within the decoded completion text.

    Built by cumulative decode (O(n^2) but n is small) so it stays exact under
    BPE merges. Special tokens decode to "" -> a zero-width span, which also
    flags them for the probe to drop. skip_special_tokens=True keeps the spans
    consistent with the saved completion text.
    """
    text, offs = "", []
    for k in range(len(comp_ids)):
        s = len(text)
        text = tok.decode(comp_ids[: k + 1], skip_special_tokens=True)
        offs.append([s, len(text)])
    return offs, text


def capture_activations(model, tok, prompt_ids: list[int], completion_ids: list[int],
                        layers, device: str):
    """Pure capture core (no generation): forward [prompt + completion] once over
    the EXACT realized token ids and return the residual stream at ``layers`` for
    the completion positions. Using the realized generated ids (not a re-tokenized
    decode) avoids detok/retok drift, so position p's activation is the one the
    model actually computed for that generated token.

    Returns a dict:
      acts          float16 ndarray [n_layers, n_completion_tokens, d_model]
      layer_ids     list[int]                  the hidden-state indices saved
      tokens        list[str]                  token string per completion position
      offsets       list[[start,end]]          char span in the decoded completion
      is_special    list[bool]                 special-token flag (probe drops these)
      completion    str                         decoded completion text
      prompt_len    int                         # prompt tokens
    """
    import numpy as np
    import torch

    if len(completion_ids) == 0:
        return None  # nothing generated to probe

    input_ids = torch.tensor([list(prompt_ids) + list(completion_ids)], device=device)
    with torch.no_grad():
        out = model(input_ids, output_hidden_states=True, use_cache=False)
    hs = out.hidden_states  # tuple len = n_hidden_states, each [1, seq, d_model]

    p = len(prompt_ids)
    sel = [hs[li][0, p:, :].to(torch.float16).cpu().numpy() for li in layers]
    acts = np.stack(sel, axis=0)           # [n_layers, n_comp_tokens, d_model]

    offsets, completion = _char_offsets(tok, list(completion_ids))
    special = set(tok.all_special_ids)
    return {
        "acts": acts,
        "layer_ids": list(layers),
        "tokens": [tok.convert_ids_to_tokens(t) for t in completion_ids],
        "offsets": offsets,
        "is_special": [int(t in special) for t in completion_ids],
        "completion": completion,
        "prompt_len": p,
    }


def run_capture(args) -> None:
    import numpy as np
    import torch  # noqa: F401  (used in the capture loop)

    from interp.capability_check import (
        build_messages,
        load_catalog_recipes,
        load_model,
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

    tok, model = load_model(args.model, args.device, args.quant)
    n_hs = model.config.num_hidden_layers + 1
    layers = resolve_layers(args.layers, n_hs)
    print(f"model has {n_hs} hidden states; saving layers {layers}")

    from interp.grade import extract_recipe_json
    from interp.geometry_labels import ground_truth

    def _empty_cache():
        if args.device == "mps":
            torch.mps.empty_cache()
        elif args.device == "cuda":
            torch.cuda.empty_cache()

    def _usable(gt: dict) -> bool:
        return bool(gt["entity_relations"] or gt["point_coords"]
                    or gt.get("vertex_angles"))

    n_saved = 0
    with meta_path.open("w") as meta_f:
        for i, (pid, prompt) in enumerate(prompts, 1):
            recipes = select_recipes(prompt, all_recipes, args.few_shot)
            messages = build_messages(prompt, recipes)
            if args.elicit_confidence:
                from interp.confidence import add_confidence_request
                messages = add_confidence_request(messages)
            # enable_thinking=False pre-closes the <think> block on hybrid reasoners
            # (GLM-4.x) so they answer directly; harmlessly ignored by templates that
            # don't use it (e.g. Qwen2.5).
            tmpl_kwargs = {"enable_thinking": False} if args.no_think else {}
            text = tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, **tmpl_kwargs
            )
            inputs = tok(text, return_tensors="pt").to(args.device)
            prompt_ids = inputs.input_ids[0].tolist()

            for s in range(args.samples):
                rid = pid if args.samples == 1 else f"{pid}_s{s}"
                try:                            # one bad sample must not kill the run
                    with torch.no_grad():
                        if args.samples == 1:
                            gen = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                                                 do_sample=False)
                        else:                   # diverse samples -> more probe data
                            torch.manual_seed(1000 + s)
                            gen = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                                                 do_sample=True, temperature=args.temperature,
                                                 top_p=0.95)
                    completion_ids = gen[0].tolist()[len(prompt_ids):]
                    completion = tok.decode(completion_ids, skip_special_tokens=True)
                    del gen
                    _empty_cache()

                    grade = grade_completion(completion)
                    if args.only_valid and not grade.ok:
                        print(f"[{i:>3}/{len(prompts)}] skip {rid} (grade {grade.stage})")
                        continue
                    obj = extract_recipe_json(completion)
                    gt = ground_truth(obj)
                    if args.require_ground_truth and not _usable(gt):
                        print(f"[{i:>3}/{len(prompts)}] skip {rid} (no ground truth)")
                        continue

                    if args.confidence_followup:
                        # TWO-TURN (clean): turn 1 (the construction above) stays
                        # uncontaminated; now elicit confidence in a 2nd turn with the
                        # construction in context, and capture activations at the
                        # confidence token there. Decouples the read from construction
                        # generation (no trailing-instruction truncation) and gives a
                        # fixed, content-neutral read site.
                        from interp.confidence import build_confidence_followup
                        msgs2 = build_confidence_followup(messages, completion)
                        text2 = tok.apply_chat_template(
                            msgs2, tokenize=False, add_generation_prompt=True, **tmpl_kwargs)
                        inputs2 = tok(text2, return_tensors="pt").to(args.device)
                        pids2 = inputs2.input_ids[0].tolist()
                        with torch.no_grad():
                            gen2 = model.generate(**inputs2, max_new_tokens=32, do_sample=False)
                        conf_ids = gen2[0].tolist()[len(pids2):]
                        del gen2, inputs2
                        _empty_cache()
                        cap = capture_activations(model, tok, pids2, conf_ids,
                                                  layers, args.device)
                    else:
                        cap = capture_activations(model, tok, prompt_ids, completion_ids,
                                                  layers, args.device)
                    if cap is None:
                        print(f"[{i:>3}/{len(prompts)}] skip {rid} (empty completion)")
                        continue
                    conf_completion = cap["completion"] if args.confidence_followup else None

                    # Verbalized confidence (if elicited): stated value + read sites.
                    # decision_pos = the token that GENERATES the number (content-
                    # neutral, causal readout); digits = state after committing it.
                    # For two-turn, cap["completion"] IS the turn-2 confidence answer.
                    conf_positions, conf_decision_pos, conf_value = [], None, None
                    if args.elicit_confidence or args.confidence_followup:
                        from interp.confidence import confidence_read_positions, parse_confidence
                        conf_value = parse_confidence(cap["completion"])
                        _n = cap["acts"].shape[1]
                        _dpos, _digits = confidence_read_positions(cap["completion"], cap["offsets"])
                        conf_positions = [p for p in _digits if 0 <= p < _n]
                        conf_decision_pos = _dpos if (_dpos is not None and 0 <= _dpos < _n) else None

                    # Keep only the token positions a probe will read (entity-name
                    # tokens + the confidence slot) — ~25x smaller on disk, so we can
                    # afford many --samples.
                    save_kwargs = {}
                    acts_to_save = cap["acts"]
                    if args.keep_positions == "entities":
                        from interp.geometry_labels import entity_ids, id_positions
                        keep = set(conf_positions)         # always keep the confidence slot(s)
                        if conf_decision_pos is not None:
                            keep.add(conf_decision_pos)
                        for eid in entity_ids(gt):
                            keep.update(id_positions(cap["completion"], cap["offsets"], eid))
                        keep = sorted(p for p in keep if 0 <= p < acts_to_save.shape[1])
                        if not keep:
                            print(f"[{i:>3}/{len(prompts)}] skip {rid} (no entity/conf positions)")
                            continue
                        acts_to_save = acts_to_save[:, keep, :]
                        save_kwargs["positions"] = np.array(keep)

                    np.savez_compressed(
                        out_dir / f"{rid}.npz",
                        acts=acts_to_save,
                        layer_ids=np.array(cap["layer_ids"]),
                        offsets=np.array(cap["offsets"]),
                        is_special=np.array(cap["is_special"]),
                        **save_kwargs,
                    )
                    meta_f.write(json.dumps({
                        "pid": rid,
                        "prompt": prompt,
                        "completion": completion,
                        "tokens": cap["tokens"],
                        "is_special": cap["is_special"],
                        "grade": {"ok": grade.ok, "stage": grade.stage, "n_ops": grade.n_ops},
                        "conf_value": conf_value,
                        "conf_positions": conf_positions,
                        "conf_decision_pos": conf_decision_pos,
                        "conf_completion": conf_completion,
                        "construction": obj.get("construction") if isinstance(obj, dict) else None,
                        # ground-truth geometry for non-trivial probing (geometry_labels)
                        "ground_truth": {
                            "stage": gt["stage"],
                            "entity_relations": gt["entity_relations"],
                            "point_coords": gt["point_coords"],
                            "vertex_angles": gt.get("vertex_angles", {}),
                            "relation_facts": gt["relation_facts"],
                        },
                        "acts_shape": list(cap["acts"].shape),
                        "layer_ids": cap["layer_ids"],
                    }) + "\n")
                    meta_f.flush()
                    n_saved += 1
                    print(f"[{i:>3}/{len(prompts)}] saved {rid}  acts={acts_to_save.shape}  "
                          f"grade={'OK' if grade.ok else grade.stage}")
                except Exception as e:  # noqa: BLE001 — log & skip, never abort the run
                    print(f"[{i:>3}/{len(prompts)}] ERROR {rid}: {type(e).__name__}: {e}")
                    _empty_cache()
                    continue

            del inputs
            _empty_cache()

    print(f"\ncaptured {n_saved} record(s) -> {out_dir} (+ {meta_path.name})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none",
                    help="'4bit' = NF4 quant (fits big models on 48GB; muddies activations)")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--tier", type=int, default=None)
    ap.add_argument("--few-shot", default="relevant:4",
                    help="exemplar selection (see capability_check.select_recipes)")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--layers", default="all",
                    help="'all' | 'even' | 'every:K' | comma list of hidden-state indices")
    ap.add_argument("--only-valid", action="store_true",
                    help="capture only completions that grade OK (clean probe set)")
    ap.add_argument("--require-ground-truth", action="store_true",
                    help="skip records with no usable ground truth (lean disk; "
                         "keeps only constructions that lowered to defs/coords/angles)")
    ap.add_argument("--keep-positions", choices=("all", "entities"), default="all",
                    help="'entities' stores only entity-name token positions "
                         "(~25x less disk -> afford many --samples); 'all' keeps every token")
    ap.add_argument("--elicit-confidence", action="store_true",
                    help="append a 'Confidence: N' request to the prompt and store the "
                         "stated value + digit-token positions (a fixed, content-neutral "
                         "read site for the correctness probe)")
    ap.add_argument("--no-think", action="store_true",
                    help="pass enable_thinking=False to the chat template — disables the "
                         "<think> reasoning block on hybrid reasoners (GLM-4.x)")
    ap.add_argument("--confidence-followup", action="store_true",
                    help="TWO-TURN confidence: generate the construction cleanly, then "
                         "elicit 'Confidence: N' in a second turn and capture activations "
                         "at that fixed token (avoids the single-turn --elicit-confidence "
                         "instruction truncating the construction JSON)")
    ap.add_argument("--samples", type=int, default=1,
                    help="completions per prompt (>1 samples at temperature for more "
                         "probe data; each saved as <pid>_s<k>)")
    ap.add_argument("--temperature", type=float, default=0.8,
                    help="sampling temperature when --samples > 1")
    ap.add_argument("--out-dir", default="interp/activations/run")
    args = ap.parse_args()
    run_capture(args)


if __name__ == "__main__":
    main()
