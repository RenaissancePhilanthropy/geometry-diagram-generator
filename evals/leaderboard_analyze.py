"""Aggregate leaderboard JSONLs into a comparison table.

Reads every ``*.jsonl`` under ``--input-dir`` (the harness writes one per
``model x strategy`` invocation) and produces:

* a top-line markdown table (model x strategy: pass-rate, mean tokens, mean
  latency, mean cost-estimate),
* per-tier breakdowns,
* per-template breakdowns,
* a CSV dump of all aggregated rows for further analysis.

Usage:
    python evals/leaderboard_analyze.py \
        --input-dir evals/results/leaderboard_pilot \
        --output-md evals/results/leaderboard_pilot/REPORT.md
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import statistics
from pathlib import Path

# Indicative pricing per 1M tokens (USD). Approximate; safe to be wrong since
# we're using this only for relative cost comparison, not invoicing.
_PRICE_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input_price, output_price)
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-5.1": (5.0, 20.0),
    "gpt-5.1-codex-mini": (1.0, 4.0),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
}


_TEMPLATE_RE = re.compile(r"(tpl-t\d-[a-z0-9]+)")


def _model_short(model: str) -> str:
    """Strip provider prefix and any date suffix."""
    name = model.split(":", 1)[-1]
    name = re.sub(r"-\d{8}$", "", name)
    return name


def _price(model: str, in_tok: int, out_tok: int) -> float:
    short = _model_short(model)
    p_in, p_out = _PRICE_PER_M_TOKENS.get(short, (0.0, 0.0))
    return (in_tok * p_in + out_tok * p_out) / 1_000_000


def _gate_pass(rec: dict) -> bool | None:
    """Loose pass: counts both strict and soft pass. Used for the headline."""
    gs = rec.get("gate_status")
    if gs == "pass":
        return True
    if gs == "soft_pass":
        return True
    if gs == "fail":
        return False
    return None


def _gate_strict(rec: dict) -> bool | None:
    """Strict pass: requires every check to actually pass (no skipped)."""
    gs = rec.get("gate_status")
    if gs == "pass":
        return True
    if gs in {"soft_pass", "fail"}:
        return False
    return None


def _load_records(input_dir: Path) -> list[dict]:
    records: list[dict] = []
    for jsonl in sorted(input_dir.glob("*.jsonl")):
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _aggregate(records: list[dict]) -> dict:
    by_combo: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in records:
        key = (r.get("model", "?"), r.get("strategy", "?"))
        by_combo[key].append(r)
    return by_combo


def _summary_row(model: str, strategy: str, recs: list[dict]) -> dict:
    n = len(recs)
    passes = sum(1 for r in recs if _gate_pass(r) is True)
    strict = sum(1 for r in recs if _gate_strict(r) is True)
    soft = sum(1 for r in recs if r.get("gate_status") == "soft_pass")
    fails = sum(1 for r in recs if _gate_pass(r) is False)
    skipped = n - passes - fails

    in_toks = [r.get("input_tokens") or 0 for r in recs]
    out_toks = [r.get("output_tokens") or 0 for r in recs]
    durs = [r.get("duration_s") or 0.0 for r in recs]
    costs = [_price(model, i, o) for i, o in zip(in_toks, out_toks)]

    return {
        "model": _model_short(model),
        "strategy": strategy,
        "n": n,
        "pass": passes,
        "strict": strict,
        "soft": soft,
        "fail": fails,
        "skip": skipped,
        "pass_rate": (passes / n) if n else 0.0,
        "strict_rate": (strict / n) if n else 0.0,
        "mean_in_tok": statistics.mean(in_toks) if in_toks else 0,
        "mean_out_tok": statistics.mean(out_toks) if out_toks else 0,
        "mean_dur_s": statistics.mean(durs) if durs else 0.0,
        "mean_cost_usd": statistics.mean(costs) if costs else 0.0,
        "total_cost_usd": sum(costs),
    }


def _by_tier_pass_rate(recs: list[dict], *, strict: bool = False) -> dict[int, float]:
    pred = _gate_strict if strict else _gate_pass
    by_tier: dict[int, list[dict]] = collections.defaultdict(list)
    for r in recs:
        by_tier[r.get("tier")].append(r)
    return {
        t: (sum(1 for r in rs if pred(r) is True) / len(rs)) if rs else 0.0
        for t, rs in by_tier.items()
    }


def _by_template_pass_rate(recs: list[dict]) -> dict[str, tuple[int, int]]:
    by_t: dict[str, list[dict]] = collections.defaultdict(list)
    for r in recs:
        m = _TEMPLATE_RE.match(r.get("scenario_id", ""))
        if not m:
            continue
        by_t[m.group(1)].append(r)
    return {
        t: (sum(1 for r in rs if _gate_pass(r) is True), len(rs))
        for t, rs in by_t.items()
    }


def _failure_modes(recs: list[dict]) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for r in recs:
        if _gate_pass(r) is False:
            for f in r.get("gate_failures", []):
                bucket = f.split(":", 1)[0]
                c[bucket] += 1
    return c


def _markdown_report(by_combo: dict, all_records: list[dict]) -> str:
    out: list[str] = []
    out.append("# GeoGen Leaderboard Pilot\n")
    out.append(f"Total records: **{len(all_records)}** across "
               f"**{len({r.get('model') for r in all_records})}** model(s) "
               f"× **{len({r.get('strategy') for r in all_records})}** strategy(ies).\n")

    rows = sorted(
        (_summary_row(m, s, recs) for (m, s), recs in by_combo.items()),
        key=lambda r: (-r["pass_rate"], r["mean_cost_usd"]),
    )

    out.append("## Headline: pass-rate × cost\n")
    out.append("Strict = every check passed (no skipped/soft); Loose = strict + soft_pass (the predicate did fire but was marked skipped, e.g. `mark_present` checks).\n")
    out.append("| model | strategy | N | strict | soft | fail | strict-rate | loose-rate | mean dur (s) | mean $ | total $ |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows_strict = sorted(
        rows,
        key=lambda r: (-r["strict_rate"], r["mean_cost_usd"]),
    )
    for r in rows_strict:
        out.append(
            f"| `{r['model']}` | `{r['strategy']}` | {r['n']} | {r['strict']} | {r['soft']} | {r['fail']} | "
            f"**{r['strict_rate']*100:.1f}%** | {r['pass_rate']*100:.1f}% | "
            f"{r['mean_dur_s']:.1f} | ${r['mean_cost_usd']:.3f} | ${r['total_cost_usd']:.2f} |"
        )

    out.append("\n## Per-tier strict pass rate\n")
    out.append("| model | strategy | T1 (easy) | T2 (medium) | T3 (hard) |")
    out.append("|---|---|---:|---:|---:|")
    for (model, strategy), recs in sorted(by_combo.items()):
        bt = _by_tier_pass_rate(recs, strict=True)
        out.append(
            f"| `{_model_short(model)}` | `{strategy}` | "
            f"{bt.get(1, 0)*100:.0f}% | {bt.get(2, 0)*100:.0f}% | {bt.get(3, 0)*100:.0f}% |"
        )

    out.append("\n## Failure-mode buckets (gate_failures prefix)\n")
    out.append("| model | strategy | top failures |")
    out.append("|---|---|---|")
    for (model, strategy), recs in sorted(by_combo.items()):
        c = _failure_modes(recs)
        top = ", ".join(f"{k}={v}" for k, v in c.most_common(5)) or "—"
        out.append(f"| `{_model_short(model)}` | `{strategy}` | {top} |")

    out.append("\n## Per-template pass rate (best strategy per model)\n")
    by_model: dict[str, dict[str, list[dict]]] = collections.defaultdict(dict)
    for (model, strategy), recs in by_combo.items():
        by_model[model][strategy] = recs
    for model, strats in sorted(by_model.items()):
        best_strat = max(
            strats.items(),
            key=lambda kv: sum(1 for r in kv[1] if _gate_pass(r) is True),
        )[0]
        out.append(f"\n### `{_model_short(model)}` (best strategy: `{best_strat}`)\n")
        out.append("| template | pass | n | rate |")
        out.append("|---|---:|---:|---:|")
        bt = _by_template_pass_rate(strats[best_strat])
        for tmpl, (pas, tot) in sorted(bt.items()):
            out.append(f"| `{tmpl}` | {pas} | {tot} | {pas/tot*100:.0f}% |")

    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    records = _load_records(args.input_dir)
    if not records:
        print(f"No records found in {args.input_dir}")
        return

    by_combo = _aggregate(records)
    rows = sorted(
        (_summary_row(m, s, recs) for (m, s), recs in by_combo.items()),
        key=lambda r: (-r["pass_rate"], r["mean_cost_usd"]),
    )

    md_path = args.output_md or (args.input_dir / "REPORT.md")
    md_path.write_text(_markdown_report(by_combo, records))
    print(f"Wrote markdown report: {md_path}")

    csv_path = args.output_csv or (args.input_dir / "leaderboard.csv")
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"Wrote CSV: {csv_path}")

    print()
    rows_strict = sorted(rows, key=lambda r: (-r["strict_rate"], r["mean_cost_usd"]))
    for r in rows_strict:
        print(f"  {r['model']:30s} {r['strategy']:12s} "
              f"strict={r['strict_rate']*100:5.1f}%  "
              f"loose={r['pass_rate']*100:5.1f}%  "
              f"cost=${r['total_cost_usd']:6.2f}  "
              f"dur={r['mean_dur_s']:5.1f}s  N={r['n']}")


if __name__ == "__main__":
    main()
