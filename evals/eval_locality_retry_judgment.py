"""Targeted eval for retry_on_locality_violation's judgment call, isolated
from the rest of the edit pipeline (see evals/scenarios_locality_judgment.yaml
for the fixture bank and design rationale).

Full edit-chain sweeps (evals/run_edit_chains.py) sample this judgment
extremely inefficiently: a real locality violation only shows up on ~1-5%
of turns, so hundreds of chain turns buy only a handful of real signal
events. This script instead constructs the exact decision point directly —
a diagnosed violation, paired with ground truth for whether it was real
corruption or a legitimate deletion/move — and puts a real model in front
of ONLY that decision, every single fixture, every single call.

Mechanism: turn 1 is a mocked PythonFullStrategy.run returning a REAL
StructuredRunResult computed by actually executing the fixture's
prior_script through _run_from_script (no LLM call — this just materializes
the "before" state). Turn 2's FIRST generate_search_replace call is
scripted to deterministically transform prior_script into the fixture's
edited_script (again no LLM call — we already know this transformation
violates locality, that's the fixture's whole premise). The RETRY —
the second generate_search_replace call, which only fires because
retry_on_locality_violation=True — is NOT scripted: it calls the real
model. That's the one call this script is testing.

Usage:
    python -m evals.eval_locality_retry_judgment [--scenarios PATH]
                                                   [--models M [M ...]]
                                                   [--output PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.strategies.base import DEFAULT_AGENT_MODEL
from geometry_diagrams.strategies import python_full as pf_module
from geometry_diagrams.strategies.python_full import PythonFullStrategy

# The exact marker text build_agent() puts in a locality-violation retry
# request (see python_full.py) — used here to detect "this call is the
# retry" versus "this call is the scripted first attempt", since both
# arrive through the same monkeypatched generate_search_replace.
_RETRY_MARKER = "Your previous edit also changed things this request never mentioned"


def _load_fixtures(scenarios_path: str) -> list[dict]:
    with open(scenarios_path) as f:
        fixtures = yaml.safe_load(f)
    for fx in fixtures:
        if fx["category"] not in ("legitimate", "illegitimate"):
            raise ValueError(f"fixture {fx['id']!r}: category must be 'legitimate' or 'illegitimate'")
    return fixtures


def _closure_stack(render_tool):
    fn = render_tool.coroutine
    idx = fn.__code__.co_freevars.index("_stack")
    return fn.__closure__[idx].cell_contents


async def run_fixture(fixture: dict, model: str) -> dict:
    """Runs one fixture against one model. Returns a result record — never
    raises on a model/pipeline failure, since one bad fixture/model combo
    shouldn't abort the whole sweep (mirrors run_edit_chains.py's own
    per-turn failure isolation)."""
    real_generate_search_replace = pf_module.generate_search_replace

    try:
        prior_result = await pf_module._run_from_script(fixture["prior_script"], SVGRenderer())
    except Exception as e:
        return {
            "fixture_id": fixture["id"], "category": fixture["category"], "model": model,
            "error": f"prior_script failed to execute: {e}", "passed": None,
        }

    async def fake_run(self, prompt, model="test", renderer=None, sandbox_timeout_seconds=2.5):
        return prior_result

    call_count = {"n": 0}

    async def scripted_then_real(prompt, model, enable_cache=False):
        if _RETRY_MARKER in prompt:
            return await real_generate_search_replace(prompt, model, enable_cache=enable_cache)
        call_count["n"] += 1
        return [{
            "old_string": prior_result.script,
            "new_string": fixture["edited_script"],
        }], 0, 0, None

    original_run = PythonFullStrategy.run
    original_generate = pf_module.generate_search_replace
    PythonFullStrategy.run = fake_run
    pf_module.generate_search_replace = scripted_then_real
    try:
        strategy = PythonFullStrategy()
        graph = strategy.build_agent(
            model=model, edit_generation_mode="search_replace",
            retry_on_locality_violation=True,
        )
        tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
        render_tool = tools_by_name["render_diagram"]

        await render_tool.ainvoke({"request": "draw the starting diagram"})
        raw = await render_tool.ainvoke({"request": fixture["request"]})
        parsed = json.loads(raw)

        if "error" in parsed:
            return {
                "fixture_id": fixture["id"], "category": fixture["category"], "model": model,
                "error": parsed["error"], "passed": None,
            }

        top = _closure_stack(render_tool)[-1]
        diagnostic = top["locality_diagnostic"]
        actual_unmatched = sorted(diagnostic.unmatched_old_names) if diagnostic else []
        expected_unmatched = sorted(fixture.get("expect_still_unmatched") or [])

        return {
            "fixture_id": fixture["id"], "category": fixture["category"], "model": model,
            "error": None,
            "locality_retry_fired": top.get("locality_retry_fired", False),
            "expected_still_unmatched": expected_unmatched,
            "actual_still_unmatched": actual_unmatched,
            "passed": actual_unmatched == expected_unmatched,
        }
    finally:
        PythonFullStrategy.run = original_run
        pf_module.generate_search_replace = original_generate


async def run_all(fixtures: list[dict], models: list[str]) -> list[dict]:
    results = []
    for fixture in fixtures:
        for model in models:
            results.append(await run_fixture(fixture, model))
    return results


def summarize(results: list[dict]) -> dict:
    by_category: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        d = by_category.setdefault(cat, {"total": 0, "passed": 0, "errored": 0})
        d["total"] += 1
        if r["passed"] is None:
            d["errored"] += 1
        elif r["passed"]:
            d["passed"] += 1
    return by_category


async def main() -> None:
    parser = argparse.ArgumentParser(description="Targeted eval for retry_on_locality_violation's judgment call")
    parser.add_argument("--scenarios", default="evals/scenarios_locality_judgment.yaml")
    parser.add_argument("--models", nargs="+", default=[DEFAULT_AGENT_MODEL])
    parser.add_argument("--output", default=None, help="Optional path to write per-case JSONL results")
    args = parser.parse_args()

    fixtures = _load_fixtures(args.scenarios)
    print(f"Running {len(fixtures)} fixtures x {len(args.models)} models "
          f"({sum(1 for f in fixtures if f['category'] == 'illegitimate')} illegitimate, "
          f"{sum(1 for f in fixtures if f['category'] == 'legitimate')} legitimate)")

    results = await run_all(fixtures, args.models)

    if args.output:
        with open(args.output, "w") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"Per-case results written to {args.output}")

    print()
    for r in results:
        status = "ERROR" if r["passed"] is None else ("PASS" if r["passed"] else "FAIL")
        print(f"[{status}] {r['fixture_id']} / {r['model']}"
              + (f" — {r['error']}" if r.get("error") else
                 f" — expected_unmatched={r['expected_still_unmatched']} actual={r['actual_still_unmatched']}"))

    print("\n=== Summary by category ===")
    summary = summarize(results)
    for cat, d in summary.items():
        rate = d["passed"] / d["total"] if d["total"] else 0.0
        label = "recall (real corruption fixed)" if cat == "illegitimate" else "specificity (legit deletions preserved)"
        print(f"{cat:14s} {label:42s} {d['passed']}/{d['total']} ({rate:.0%}), {d['errored']} errored")


if __name__ == "__main__":
    asyncio.run(main())
