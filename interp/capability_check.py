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


def load_fewshot_recipes(mode: str) -> list:
    """Return recipe objects to include as few-shot exemplars in the user prompt.

    mode="none" -> [] (bare DSL docs only, like RecipeStrategy(use_recipes=False));
    mode="all"  -> every recipe in the default catalog (the production few-shot
                   mechanism, minus the LLM selector);
    mode=<int>  -> the first N catalog recipes — a small, deterministic subset.

    Each recipe carries a worked RecipeDSL .example that pins the exact op
    vocabulary. NOTE: every recipe adds ~430 prompt tokens; "all" (20) pushes
    the prompt to ~14k tokens, which OOMs MPS attention (O(seq^2), fully
    materialized by MPS SDPA). Keep N small (~5) on Apple Silicon.
    """
    if mode == "none":
        return []
    from recipe.catalog import load_catalog, load_recipe

    specs = load_catalog("default")
    if mode != "all":
        specs = specs[: int(mode)]
    return [load_recipe(s.id, catalog="default") for s in specs]


def build_messages(prompt: str, recipes: list | None = None) -> list[dict]:
    """Mirror RecipeStrategy's generation call: system = RECIPE_GENERATION_SYSTEM,
    user = build_generation_prompt(prompt, recipes, DSL_DOCS). With recipes=[] this
    is the use_recipes=False path; with the catalog passed it is the few-shot path
    (production normally selects a relevant subset via a cheap LLM; we pass a fixed
    set to keep the gate local-only).
    """
    from recipe.catalog import DSL_DOCS, build_generation_prompt

    return [
        {"role": "system", "content": _recipe_generation_system()},
        {"role": "user", "content": build_generation_prompt(prompt, recipes or [], DSL_DOCS)},
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--max-new-tokens", type=int, default=2048)
    ap.add_argument("--n", type=int, default=20, help="number of prompts to test")
    ap.add_argument("--tier", type=int, default=None, help="filter by difficulty tier (1/2/3)")
    ap.add_argument("--few-shot", default="none",
                    help="few-shot exemplars: 'none', 'all', or an int N "
                         "(first N catalog recipes; keep small on MPS — ~5)")
    ap.add_argument("--print-output", action="store_true", help="dump each completion")
    args = ap.parse_args()

    prompts = load_prompts(args.n, args.tier)
    recipes = load_fewshot_recipes(args.few_shot)
    print(f"loaded {len(prompts)} prompt(s)" + (f" (tier {args.tier})" if args.tier else "")
          + f"; few-shot={args.few_shot} ({len(recipes)} recipes)")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"loading {args.model} on {args.device} (bf16) — first run downloads ~15 GB ...")
    tok = AutoTokenizer.from_pretrained(args.model)
    # transformers >=5 renamed torch_dtype -> dtype (torch_dtype kept for BC).
    model = (
        AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16)
        .to(args.device)
        .eval()
    )

    n_ok = 0
    stage_counts: dict[str, int] = {}
    for i, (pid, prompt) in enumerate(prompts, 1):
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
