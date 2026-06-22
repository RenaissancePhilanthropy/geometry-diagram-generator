"""
Phase 0 capability gate: can Qwen2.5-7B produce valid GeoGen constructions?

SCAFFOLD — run/verify on the big (>=32 GB) Apple-Silicon machine; it has NOT
been executed yet. Loads Qwen2.5-7B-Instruct on MPS (bf16), prompts it with the
project's recipe-DSL system instructions on a few geometry prompts, and prints
the output. The automated parse -> lower -> compile -> check grade is left as a
clearly-marked TODO (module pointers below); first just eyeball whether the
output looks like a valid RecipeDSL.

Run from the repo root:
    python interp/capability_check.py
    python interp/capability_check.py --model Qwen/Qwen2.5-3B-Instruct
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# allow `from strategies...` / `from recipe...` when run from the repo root
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# A few representative GeoGenBench-style prompts. Once the auto-grade is wired,
# load the real set from benchmark/definitions/bench_genexam.yaml instead.
PROMPTS = [
    "Draw an acute triangle ABC with angle A = 60 degrees and angle B = 70 "
    "degrees, then draw the altitude from C, meeting AB at H.",
    "In a square ABCD, let E be the midpoint of side BC. Draw segment AE.",
    "Draw a circle with center O and a point P outside it; construct the "
    "tangent from P touching the circle at T.",
]


def build_messages(prompt: str) -> list[dict]:
    # confirmed exported names in strategies/instructions_recipe.py
    from strategies.instructions_recipe import (
        RECIPE_DSL_QUICK_REF,
        RECIPE_GENERATION_SYSTEM,
    )

    system = RECIPE_GENERATION_SYSTEM + "\n\n" + RECIPE_DSL_QUICK_REF
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"loading {args.model} on {args.device} (bf16) — first run downloads ~15 GB ...")
    tok = AutoTokenizer.from_pretrained(args.model)
    model = (
        AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16)
        .to(args.device)
        .eval()
    )

    for i, prompt in enumerate(PROMPTS, 1):
        text = tok.apply_chat_template(
            build_messages(prompt), tokenize=False, add_generation_prompt=True
        )
        inputs = tok(text, return_tensors="pt").to(args.device)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens, do_sample=False
            )
        completion = tok.decode(
            out[0][inputs.input_ids.shape[1] :], skip_special_tokens=True
        )
        print(f"\n{'=' * 72}\n[{i}] PROMPT: {prompt}\n{'-' * 72}\n{completion}\n")

    # TODO (wire the auto-grade -> valid-construction rate over the benchmark):
    #   from recipe.dsl import RecipeDSL        # parse the model's JSON output
    #   from recipe.lower import <lower fn>     # RecipeDSL -> DiagramIR
    #   from ir.to_sympy import compile_defs    # DiagramIR -> SymPy symbol table
    #   from ir.checks import run_checks        # -> pass/fail per predicate
    # Inspect recipe/lower.py and strategies/recipe.py for the exact call order
    # (the API-based RecipeStrategy already does parse->lower->compile->check;
    #  reuse that path, just swapping the LLM call for this local model).


if __name__ == "__main__":
    main()
