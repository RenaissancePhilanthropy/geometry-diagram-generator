"""Render the leaderboard plots from a directory of result JSONLs.

Produces three figures (PNG + PDF):

* ``pareto.{png,pdf}`` — pass-rate vs cost-per-scenario, log-x, with the
  Pareto frontier traced. Each point = (model, strategy).
* ``per_template_heatmap.{png,pdf}`` — rows = templates, cols = models
  (best strategy per model), cells = pass-rate.
* ``tier_stratified.{png,pdf}`` — strict pass-rate by tier.
* ``failure_modes.{png,pdf}`` — stacked bars of semantic failure buckets per
  (model, strategy).

Usage:
    python evals/leaderboard_plot.py \
        --input-dir evals/results/leaderboard_pilot \
        --output-dir evals/results/leaderboard_pilot/plots
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


_TEMPLATE_RE = re.compile(r"(tpl-t\d-[a-z0-9]+)")

_PRICE_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.1": (5.0, 20.0),
    "gpt-5.1-codex-mini": (1.0, 4.0),
}


def _model_short(model: str) -> str:
    name = model.split(":", 1)[-1]
    return re.sub(r"-\d{8}$", "", name)


def _strict_pass(rec: dict) -> bool:
    return rec.get("gate_status") == "pass"


def _any_pass(rec: dict) -> bool:
    return rec.get("gate_status") in ("pass", "soft_pass")


def _price(model: str, in_tok: int, out_tok: int) -> float:
    short = _model_short(model)
    p_in, p_out = _PRICE_PER_M_TOKENS.get(short, (0.0, 0.0))
    return (in_tok * p_in + out_tok * p_out) / 1_000_000


def _load(input_dir: Path) -> list[dict]:
    out: list[dict] = []
    for jsonl in sorted(input_dir.glob("*.jsonl")):
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _by_combo(records: list[dict]) -> dict[tuple[str, str], list[dict]]:
    d: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in records:
        d[(r.get("model", "?"), r.get("strategy", "?"))].append(r)
    return d


def _combo_label(model: str, strategy: str) -> str:
    model_label = {
        "claude-opus-4-7": "Opus",
        "claude-sonnet-4-6": "Sonnet",
        "claude-haiku-4-5": "Haiku",
        "gpt-5.1": "GPT-5.1",
    }.get(_model_short(model), _model_short(model))
    strategy_label = {
        "raw_code": "Raw",
        "structured": "IR",
        "recipe": "Recipe",
    }.get(strategy, strategy)
    return f"{model_label}\n{strategy_label}"


def _pareto(points: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Return Pareto-optimal points (lower x, higher y is better)."""
    sorted_pts = sorted(points, key=lambda p: (p[0], -p[1]))
    front: list[tuple[float, float, str]] = []
    best_y = -float("inf")
    for x, y, lbl in sorted_pts:
        if y > best_y:
            front.append((x, y, lbl))
            best_y = y
    return front


def plot_pareto(records: list[dict], out_path: Path, strict: bool = True) -> None:
    by_combo = _by_combo(records)
    pass_fn = _strict_pass if strict else _any_pass

    pts: list[tuple[float, float, str, str, str]] = []
    for (model, strategy), recs in by_combo.items():
        n = len(recs) or 1
        passes = sum(1 for r in recs if pass_fn(r))
        pass_rate = passes / n
        costs = [_price(model, r.get("input_tokens") or 0, r.get("output_tokens") or 0) for r in recs]
        mean_cost = statistics.mean(costs) if costs else 0.0
        if mean_cost <= 0:
            continue
        pts.append((mean_cost, pass_rate * 100, _model_short(model), strategy, model))

    if not pts:
        print("no points to plot")
        return

    fig, ax = plt.subplots(figsize=(8, 5.5))

    color_map = {}
    for _, _, m, _, _ in pts:
        if m not in color_map:
            color_map[m] = plt.cm.tab10(len(color_map) % 10)

    marker_map = {"raw_code": "o", "structured": "D", "recipe": "^",
                  "raw_code_with_revise": "s", "plan_and_code": "P"}

    sorted_pts = sorted(pts, key=lambda p: (p[0], p[1]))
    for idx, (x, y, m, s, _) in enumerate(sorted_pts):
        ax.scatter(x, y, s=140, color=color_map[m], marker=marker_map.get(s, "o"),
                   edgecolor="black", linewidth=0.7, zorder=3)
        nearby = [
            (xx, yy)
            for xx, yy, *_ in sorted_pts
            if abs(np.log10(xx) - np.log10(x)) < 0.06 and abs(yy - y) < 6 and (xx, yy) != (x, y)
        ]
        if not nearby:
            dx, dy = 6, 6
            ha = "left"
        else:
            higher = sum(1 for _, yy in nearby if yy > y)
            lower = sum(1 for _, yy in nearby if yy < y)
            if higher > lower:
                dx, dy = 6, -10
                ha = "left"
            elif lower > higher:
                dx, dy = 6, 8
                ha = "left"
            else:
                dx, dy = -8, 0
                ha = "right"
        ax.annotate(
            _combo_label(m, s),
            (x, y),
            fontsize=7,
            xytext=(dx, dy),
            textcoords="offset points",
            ha=ha,
            zorder=4,
        )

    front = _pareto([(x, y, f"{m}/{s}") for x, y, m, s, _ in pts])
    if len(front) >= 2:
        fx = [p[0] for p in front]
        fy = [p[1] for p in front]
        ax.plot(fx, fy, "k--", alpha=0.4, lw=1.2, zorder=2, label="Pareto frontier")

    ax.set_xscale("log")
    ax.set_xlabel("Mean cost per scenario (USD, log scale)")
    ax.set_ylabel(f"{'Strict' if strict else 'Strict+soft'} pass-rate (%)")
    ax.set_title(f"GeoGen leaderboard — pass-rate × cost  ({'strict' if strict else 'strict+soft'} gating)")
    ax.set_ylim(-2, 102)
    ax.grid(True, alpha=0.25)
    if len(front) >= 2:
        ax.legend(loc="lower right")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path.with_suffix(".png"), dpi=160)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  wrote {out_path.with_suffix('.png')}")


def plot_tier_stratified(records: list[dict], out_path: Path) -> None:
    by_combo = _by_combo(records)
    combos = sorted(by_combo.keys())
    if not combos:
        return

    tiers = [1, 2, 3]
    matrix = np.zeros((len(combos), len(tiers)))
    for i, combo in enumerate(combos):
        recs = by_combo[combo]
        for j, tier in enumerate(tiers):
            rs = [r for r in recs if r.get("tier") == tier]
            matrix[i, j] = (
                sum(1 for r in rs if _strict_pass(r)) / len(rs) * 100
                if rs
                else np.nan
            )

    x = np.arange(len(combos))
    width = 0.24
    colors = ["#4C78A8", "#F58518", "#E45756"]

    fig, ax = plt.subplots(figsize=(max(8, 0.9 * len(combos)), 5.2))
    for j, tier in enumerate(tiers):
        offsets = x + (j - 1) * width
        heights = matrix[:, j]
        ax.bar(offsets, np.nan_to_num(heights), width, label=f"Tier {tier}", color=colors[j])
        for xi, h in zip(offsets, heights):
            if not np.isnan(h):
                ax.text(xi, h + 1.5, f"{h:.0f}", ha="center", va="bottom", fontsize=7)

    labels = [_combo_label(m, s) for m, s in combos]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Strict pass-rate (%)")
    ax.set_title("GeoGen pilot strict pass-rate by difficulty tier")
    ax.legend(loc="lower left", ncol=3, fontsize=8)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path.with_suffix(".png"), dpi=180)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  wrote {out_path.with_suffix('.png')}")


def plot_per_template_heatmap(records: list[dict], out_path: Path) -> None:
    by_combo = _by_combo(records)
    by_model: dict[str, dict[str, list[dict]]] = collections.defaultdict(dict)
    for (model, strategy), recs in by_combo.items():
        by_model[model][strategy] = recs

    # best strategy per model = highest strict-pass rate (ties broken by larger N
    # so combos with very small samples don't dominate when they happen to hit 100%).
    best_by_model: dict[str, list[dict]] = {}
    best_strategy_by_model: dict[str, str] = {}
    for model, strats in by_model.items():
        def _key(kv):
            recs = kv[1]
            n = len(recs) or 1
            rate = sum(1 for r in recs if _strict_pass(r)) / n
            return (rate, n)
        best = max(strats.items(), key=_key)
        best_by_model[model] = best[1]
        best_strategy_by_model[model] = best[0]

    templates: set[str] = set()
    for recs in best_by_model.values():
        for r in recs:
            m = _TEMPLATE_RE.match(r.get("scenario_id", ""))
            if m:
                templates.add(m.group(1))
    template_list = sorted(templates)
    model_list = sorted(best_by_model.keys())

    if not template_list or not model_list:
        print("no templates or models to plot")
        return

    matrix = np.full((len(template_list), len(model_list)), np.nan)
    for j, model in enumerate(model_list):
        recs = best_by_model[model]
        by_t: dict[str, list[dict]] = collections.defaultdict(list)
        for r in recs:
            m = _TEMPLATE_RE.match(r.get("scenario_id", ""))
            if m:
                by_t[m.group(1)].append(r)
        for i, tpl in enumerate(template_list):
            rs = by_t.get(tpl, [])
            if rs:
                matrix[i, j] = sum(1 for r in rs if _strict_pass(r)) / len(rs) * 100

    fig, ax = plt.subplots(figsize=(max(6, 1.7 * len(model_list)),
                                    max(6, 0.32 * len(template_list))))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)

    strategy_short = {"raw_code": "raw", "structured": "IR", "recipe": "recipe"}
    col_labels = []
    for m in model_list:
        strat = best_strategy_by_model.get(m, "?")
        col_labels.append(f"{_model_short(m)}\n({strategy_short.get(strat, strat)})")
    ax.set_xticks(range(len(model_list)))
    ax.set_xticklabels(col_labels, rotation=20, ha="right", fontsize=9)
    ax.set_yticks(range(len(template_list)))
    ax.set_yticklabels(template_list, fontsize=8)
    ax.set_title("Per-template strict-pass rate (best strategy per model)")
    for i in range(len(template_list)):
        for j in range(len(model_list)):
            v = matrix[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="black" if 25 < v < 75 else "white")
    fig.colorbar(im, ax=ax, label="pass-rate (%)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path.with_suffix(".png"), dpi=160)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  wrote {out_path.with_suffix('.png')}")


_GEOMETRIC_PREDICATE_TYPES = {
    "right_angle",
    "parallel",
    "perpendicular",
    "equal_lengths",
    "point_on_circle",
    "point_on_segment",
    "point_on_line",
    "centroid",
    "angle_bisector",
    "equidistant_from_sides",
    "angle_equal",
    "tangent",
    "collinear",
    "intersects",
    "midpoint",
    "opposite_side",
    "same_side",
    "not_between",
}


def _failure_bucket(rec: dict, failure_name: str) -> str:
    checks = rec.get("tikz_checks") or {}
    check = checks.get(failure_name)
    if isinstance(check, dict):
        ptype = check.get("type")
        if ptype:
            if ptype in _GEOMETRIC_PREDICATE_TYPES:
                return "geometric predicate"
            if ptype in {"mark_present", "label_present"}:
                return "mark / label"
            return str(ptype)

    if failure_name in {"required_labels", "required_entities"}:
        return "label / entity"
    if failure_name.startswith("canvas:"):
        return "canvas"
    if "marked" in failure_name or "label" in failure_name:
        return "mark / label"
    return "geometric predicate"


def plot_failure_modes(records: list[dict], out_path: Path) -> None:
    by_combo = _by_combo(records)
    combos = sorted(by_combo.keys())
    if not combos:
        return

    bucket_set: set[str] = set()
    bucketed: dict[tuple[str, str], collections.Counter] = {}
    for k, recs in by_combo.items():
        c: collections.Counter = collections.Counter()
        for r in recs:
            if r.get("gate_status") != "fail":
                continue
            for f in r.get("gate_failures", []):
                bucket = _failure_bucket(r, f.split(":", 1)[0])
                c[bucket] += 1
        bucketed[k] = c
        bucket_set.update(c.keys())

    buckets = sorted(bucket_set)
    if not buckets:
        print("no failure-mode data to plot")
        return

    x = np.arange(len(combos))
    bottom = np.zeros(len(combos))
    fig, ax = plt.subplots(figsize=(max(7, 0.9 * len(combos)), 5))
    for bucket in buckets:
        heights = np.array([bucketed[k][bucket] for k in combos], dtype=float)
        ax.bar(x, heights, bottom=bottom, label=bucket)
        bottom += heights
    labels = [_combo_label(m, s) for m, s in combos]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("# failed scenarios")
    ax.set_title("Failure modes by (model, strategy)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path.with_suffix(".png"), dpi=160)
    fig.savefig(out_path.with_suffix(".pdf"))
    plt.close(fig)
    print(f"  wrote {out_path.with_suffix('.png')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True,
                        help="Use strict pass (no soft_pass). Default: True.")
    args = parser.parse_args()

    out_dir = args.output_dir or (args.input_dir / "plots")
    records = _load(args.input_dir)
    if not records:
        print(f"No records in {args.input_dir}")
        return

    print(f"Loaded {len(records)} records from {args.input_dir}")
    plot_pareto(records, out_dir / "pareto", strict=args.strict)
    plot_tier_stratified(records, out_dir / "tier_stratified")
    plot_per_template_heatmap(records, out_dir / "per_template_heatmap")
    plot_failure_modes(records, out_dir / "failure_modes")
    print(f"\nAll plots in {out_dir}")


if __name__ == "__main__":
    main()
