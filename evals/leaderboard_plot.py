"""Render the leaderboard plots from a directory of result JSONLs.

Produces three figures (PNG + PDF):

* ``pareto.{png,pdf}`` — pass-rate vs cost-per-scenario, log-x, with the
  Pareto frontier traced. Each point = (model, strategy).
* ``per_template_heatmap.{png,pdf}`` — rows = templates, cols = models
  (best strategy per model), cells = pass-rate.
* ``failure_modes.{png,pdf}`` — stacked bars of gate-failure buckets per
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

    for x, y, m, s, _ in pts:
        ax.scatter(x, y, s=140, color=color_map[m], marker=marker_map.get(s, "o"),
                   edgecolor="black", linewidth=0.7, zorder=3)
        ax.annotate(f"{m}\n{s}", (x, y), fontsize=7,
                    xytext=(5, 5), textcoords="offset points", zorder=4)

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


def plot_per_template_heatmap(records: list[dict], out_path: Path) -> None:
    by_combo = _by_combo(records)
    by_model: dict[str, dict[str, list[dict]]] = collections.defaultdict(dict)
    for (model, strategy), recs in by_combo.items():
        by_model[model][strategy] = recs

    # best strategy per model = the one with most strict-passes
    best_by_model: dict[str, list[dict]] = {}
    for model, strats in by_model.items():
        best = max(strats.items(),
                   key=lambda kv: sum(1 for r in kv[1] if _strict_pass(r)))
        best_by_model[model] = best[1]

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

    fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(model_list)),
                                    max(6, 0.32 * len(template_list))))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    ax.set_xticks(range(len(model_list)))
    ax.set_xticklabels([_model_short(m) for m in model_list], rotation=20, ha="right")
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
                bucket = f.split(":", 1)[0]
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
    labels = [f"{_model_short(m)}\n{s}" for m, s in combos]
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
    plot_per_template_heatmap(records, out_dir / "per_template_heatmap")
    plot_failure_modes(records, out_dir / "failure_modes")
    print(f"\nAll plots in {out_dir}")


if __name__ == "__main__":
    main()
