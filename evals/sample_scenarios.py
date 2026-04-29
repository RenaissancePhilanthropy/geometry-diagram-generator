"""Deterministic stratified sampling from a scenarios YAML.

Picks N_PER_TIER scenarios from each tier, distributing across templates so
every template that exists in a tier is represented. Output is itself a valid
scenarios YAML that can be passed directly to ``evals/run.py --scenarios``.

Usage:
    python evals/sample_scenarios.py \
        --input evals/scenarios_generated.yaml \
        --output evals/scenarios_pilot.yaml \
        --per-tier 10 \
        --seed 42
"""
from __future__ import annotations

import argparse
import collections
import random
import re
from pathlib import Path

import yaml


_TEMPLATE_RE = re.compile(r"(tpl-t\d-[a-z0-9]+)")


def _template_key(scenario_id: str) -> str:
    m = _TEMPLATE_RE.match(scenario_id)
    return m.group(1) if m else "other"


def stratified_sample(
    scenarios: list[dict],
    per_tier: int,
    seed: int = 42,
) -> list[dict]:
    """Return a deterministic stratified sample.

    Within each tier, scenarios are grouped by template prefix and sampled
    round-robin so every template gets at least one representative (subject
    to availability) before any template gets a second.
    """
    rng = random.Random(seed)
    by_tier: dict[int, list[dict]] = collections.defaultdict(list)
    for s in scenarios:
        by_tier[s["tier"]].append(s)

    sampled: list[dict] = []
    for tier in sorted(by_tier):
        tier_scenarios = by_tier[tier]
        by_template: dict[str, list[dict]] = collections.defaultdict(list)
        for s in tier_scenarios:
            by_template[_template_key(s["id"])].append(s)

        for tmpl in by_template:
            rng.shuffle(by_template[tmpl])

        templates = sorted(by_template.keys())
        rng.shuffle(templates)

        picks: list[dict] = []
        idx = 0
        while len(picks) < per_tier and any(by_template[t] for t in templates):
            tmpl = templates[idx % len(templates)]
            if by_template[tmpl]:
                picks.append(by_template[tmpl].pop())
            idx += 1

        sampled.extend(picks)

    return sampled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-tier", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with args.input.open() as f:
        scenarios = yaml.safe_load(f)

    sampled = stratified_sample(scenarios, args.per_tier, args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        yaml.safe_dump(sampled, f, sort_keys=False, width=200)

    by_tier = collections.Counter(s["tier"] for s in sampled)
    by_template = collections.Counter(_template_key(s["id"]) for s in sampled)
    print(f"Wrote {len(sampled)} scenarios to {args.output}")
    print(f"  by tier: {dict(by_tier)}")
    print(f"  templates covered: {len(by_template)} ({sum(by_template.values())} picks)")


if __name__ == "__main__":
    main()
