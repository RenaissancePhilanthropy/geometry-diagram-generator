"""
Phase 0 capability gate: can Qwen2.5-7B produce valid GeoGen constructions?

Loads a local HF model on MPS (bf16), prompts it with the project's recipe-DSL
system instructions on a sample of GeoGenBench prompts, and grades each output
through the project's real pipeline (parse -> lower -> compile -> check) via
interp.grade. Prints a per-prompt result and an overall valid-construction rate.

The gate: if the rate is too low to build interp on, bump to Qwen2.5-14B or add
few-shot exemplars BEFORE any capture/probe work.

Run from the repo root (downloads ~15 GB on first run):
    python interp/capability_check.py                          # 7B, 20 prompts
    python interp/capability_check.py --model Qwen/Qwen2.5-3B-Instruct --n 10
    python interp/capability_check.py --tier 1 --n 30          # easy tier only
    python interp/capability_check.py --print-output           # dump completions
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# allow `from strategies...` / `from recipe...` / `from interp...` from repo root
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from interp.grade import grade_completion  # noqa: E402

BENCH_YAML = REPO / "benchmark" / "definitions" / "bench_genexam.yaml"

# Fallback prompts if the benchmark YAML can't be loaded.
FALLBACK_PROMPTS = [
    "Draw an acute triangle ABC with angle A = 60 degrees and angle B = 70 "
    "degrees, then draw the altitude from C, meeting AB at H.",
    "In a square ABCD, let E be the midpoint of side BC. Draw segment AE.",
    "Draw a circle with center O and a point P outside it; construct the "
    "tangent from P touching the circle at T.",
]


def load_prompts(n: int, tier: int | None) -> list[tuple[str, str]]:
    """Return [(id, prompt_text), ...] from the GenExam benchmark YAML.

    Falls back to FALLBACK_PROMPTS (with synthetic ids) if the YAML is missing.
    """
    try:
        import yaml

        data = yaml.safe_load(BENCH_YAML.read_text())
        items = data["prompts"]
        if tier is not None:
            items = [p for p in items if p.get("tier") == tier]
        out = [(p["id"], p["prompt"]) for p in items[:n]]
        if out:
            return out
    except Exception as e:  # noqa: BLE001
        print(f"(could not load {BENCH_YAML.name}: {e}; using fallback prompts)")
    return [(f"fallback_{i}", p) for i, p in enumerate(FALLBACK_PROMPTS[:n], 1)]


def _recipe_generation_system() -> str:
    """RECIPE_GENERATION_SYSTEM, loaded WITHOUT importing the `strategies`
    package (whose __init__ pulls in pydantic_ai, absent from this venv).
    instructions_recipe.py is pure strings, so loading it standalone is safe.
    """
    import importlib.util

    path = REPO / "strategies" / "instructions_recipe.py"
    spec = importlib.util.spec_from_file_location("_instructions_recipe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.RECIPE_GENERATION_SYSTEM


def load_catalog_recipes() -> list:
    """Load every recipe object in the default catalog (each carries a worked
    RecipeDSL .example that pins the exact op vocabulary)."""
    from recipe.catalog import load_catalog, load_recipe

    return [load_recipe(s.id, catalog="default") for s in load_catalog("default")]


import re as _re

_WORD = _re.compile(r"[a-z]+")


def _keywords(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def select_recipes(prompt: str, all_recipes: list, mode: str) -> list:
    """Pick few-shot exemplars for one prompt.

    mode="none"        -> [] (bare DSL docs only, use_recipes=False path);
    mode="all"         -> every catalog recipe (OOMs MPS at ~14k tok; fine on GPU);
    mode=<int>         -> the first N catalog recipes (deterministic, prompt-agnostic);
    mode="relevant[:K]"-> the K recipes whose tags/name/description best overlap the
                          prompt's words (default K=4). This is a local stand-in for
                          production's LLM recipe selector — it spends a small
                          exemplar budget on RELEVANT examples (e.g. a "square"
                          prompt pulls square_on_segment) instead of a fixed subset.

    NOTE: every recipe adds ~430 prompt tokens. "all" (20) ~14k tokens OOMs MPS
    attention (O(seq^2)); keep the budget small on Apple Silicon, unlimited on GPU.
    """
    if mode == "none":
        return []
    if mode == "all":
        return all_recipes
    if mode.startswith("relevant"):
        k = int(mode.split(":", 1)[1]) if ":" in mode else 4
        pw = _keywords(prompt)

        def score(r) -> int:
            strong = set(r.tags) | _keywords(r.name)          # tags/name: weight 2
            weak = _keywords(r.description) - strong          # description: weight 1
            return 2 * len(strong & pw) + len(weak & pw)

        ranked = sorted(
            range(len(all_recipes)),
            key=lambda i: (-score(all_recipes[i]), i),        # ties -> catalog order
        )
        top = [all_recipes[i] for i in ranked if score(all_recipes[i]) > 0][:k]
        return top or all_recipes[:k]                         # always provide K
    return all_recipes[: int(mode)]


# Targeted addendum for the recurring schema mistakes observed in capability runs
# (regular_polygon.center as coords, label_* ops, AAA triangles, circle.hradius).
# Appended to the system prompt for the GATE/CAPTURE only — does not touch the
# production RecipeStrategy. Each line corresponds to a real validation failure.
DSL_GOTCHAS = """\

Avoid these common mistakes (they fail validation):
- Labels are NOT construction ops. Do not emit `label_point`, `label_angle`, or
  `angle` ops. Put labels in the `annotations` block instead.
- `regular_polygon` / `polygon` `center` must be a POINT ID (a string like "O"),
  never a coordinate pair. Define the center point first, then reference its id.
- A `triangle` `spec` needs at least one SIDE length (SSS/SAS/ASA/AAS). Angles
  alone (AAA) are rejected. Use only fields: side_AB, side_BC, side_CA, angle_A,
  angle_B, angle_C, right_angle_at.
- A `circle` uses `radius` (not `hradius`/`vradius` — those are for `ellipse`).
- Only reference ids you have already defined earlier in the construction.
"""


def build_messages(prompt: str, recipes: list | None = None,
                   gotchas: bool = True) -> list[dict]:
    """Mirror RecipeStrategy's generation call: system = RECIPE_GENERATION_SYSTEM,
    user = build_generation_prompt(prompt, recipes, DSL_DOCS). With recipes=[] this
    is the use_recipes=False path; with the catalog passed it is the few-shot path
    (production normally selects a relevant subset via a cheap LLM; we pass a fixed
    set to keep the gate local-only). ``gotchas`` appends DSL_GOTCHAS to the system
    prompt to suppress the recurring schema slips (gate/capture only).
    """
    from recipe.catalog import DSL_DOCS, build_generation_prompt

    system = _recipe_generation_system() + (DSL_GOTCHAS if gotchas else "")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": build_generation_prompt(prompt, recipes or [], DSL_DOCS)},
    ]


def load_model(model_name: str, device: str, quant: str = "none"):
    """Load tokenizer + model. quant='none' -> bf16 (clean activations, preferred
    for probing); quant='4bit' -> NF4 4-bit via bitsandbytes (compute in bf16) so
    big models fit a single 48GB card. NOTE: 4-bit distorts activations — use only
    for capability tests or size comparisons WITH a 4-bit control, never as the
    sole basis for a representation claim. CUDA only for 4-bit."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_name)
    if quant == "awq":
        # Pre-quantized AWQ 4-bit checkpoint (e.g. Qwen/Qwen3-32B-AWQ): ~18GB on
        # disk (vs ~66GB bf16), so it fits a 32GB disk. Quant config is baked in;
        # just load directly (needs autoawq). fp16 compute.
        print(f"loading {model_name} (AWQ 4-bit, prequantized) ...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=torch.float16, device_map={"": 0}).eval()
    elif quant == "4bit":
        from transformers import BitsAndBytesConfig
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                 bnb_4bit_compute_dtype=torch.bfloat16,
                                 bnb_4bit_use_double_quant=True)
        print(f"loading {model_name} in 4-bit (NF4, bf16 compute) ...")
        model = AutoModelForCausalLM.from_pretrained(
            model_name, quantization_config=bnb, device_map={"": 0}).eval()
    else:
        print(f"loading {model_name} on {device} (bf16) ...")
        try:
            model = AutoModelForCausalLM.from_pretrained(model_name, dtype=torch.bfloat16)
        except (ValueError, KeyError) as e:            # VLM configs (Gemma3/4, Mistral3, ...)
            from transformers import AutoModelForImageTextToText
            print(f"  (not a CausalLM config [{type(e).__name__}]; "
                  "loading as VLM / ImageTextToText, text-only)")
            model = AutoModelForImageTextToText.from_pretrained(model_name, dtype=torch.bfloat16)
        model = model.to(device).eval()
    return tok, model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--quant", choices=("none", "4bit", "awq"), default="none",
                    help="'4bit' = NF4 quant (fits big models on 48GB; muddies activations)")
    ap.add_argument("--max-new-tokens", type=int, default=2048)
    ap.add_argument("--n", type=int, default=20, help="number of prompts to test")
    ap.add_argument("--tier", type=int, default=None, help="filter by difficulty tier (1/2/3)")
    ap.add_argument("--few-shot", default="none",
                    help="few-shot exemplars: 'none', 'all', an int N (first N "
                         "catalog recipes), or 'relevant[:K]' (top-K by prompt "
                         "relevance, default K=4). 'all' OOMs MPS — use on GPU.")
    ap.add_argument("--print-output", action="store_true", help="dump each completion")
    args = ap.parse_args()

    prompts = load_prompts(args.n, args.tier)
    all_recipes = [] if args.few_shot == "none" else load_catalog_recipes()
    print(f"loaded {len(prompts)} prompt(s)" + (f" (tier {args.tier})" if args.tier else "")
          + f"; few-shot={args.few_shot} (catalog of {len(all_recipes)} recipes)")

    import torch  # noqa: F401  (used in the generation loop below)
    tok, model = load_model(args.model, args.device, args.quant)

    n_ok = 0
    stage_counts: dict[str, int] = {}
    for i, (pid, prompt) in enumerate(prompts, 1):
        recipes = select_recipes(prompt, all_recipes, args.few_shot)
        text = tok.apply_chat_template(
            build_messages(prompt, recipes), tokenize=False, add_generation_prompt=True
        )
        inputs = tok(text, return_tensors="pt").to(args.device)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=args.max_new_tokens, do_sample=False
            )
        completion = tok.decode(
            out[0][inputs.input_ids.shape[1] :], skip_special_tokens=True
        )

        # Release this iteration's device tensors and reclaim the MPS pool.
        # Without this the allocator accumulates KV-cache/activation buffers
        # across prompts and eventually OOMs mid-prefill (esp. 7B + long
        # few-shot prompts) even when physical RAM is free. See PLAN.md risks.
        del out, inputs
        if args.device == "mps":
            torch.mps.empty_cache()
        elif args.device == "cuda":
            torch.cuda.empty_cache()

        grade = grade_completion(completion)
        n_ok += int(grade.ok)
        stage_counts[grade.stage] = stage_counts.get(grade.stage, 0) + 1

        flag = "✓" if grade.ok else "✗"
        print(f"[{i:>3}/{len(prompts)}] {flag} {pid:<24} {grade.summary}")
        if args.print_output:
            print(f"{'-' * 72}\n{completion}\n{'-' * 72}")

    total = len(prompts)
    rate = n_ok / total if total else 0.0
    print(f"\n{'=' * 72}")
    print(f"valid-construction rate: {n_ok}/{total} = {rate:.0%}")
    print("stage breakdown (furthest stage reached): " +
          ", ".join(f"{k}={v}" for k, v in sorted(stage_counts.items())))


if __name__ == "__main__":
    main()
