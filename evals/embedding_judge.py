"""Embedding judge — cosine(reasoning, answer) consistency score per run.

An offline, cheap, model-agnostic judge. For each eval-result JSONL record that
has a recoverable chain-of-thought (`cot`), it embeds the CoT and four text
renderings of the diagram the model produced, then reports cosine similarity
between the CoT embedding and each answer representation, kept **separate**.
Runs are bucketed by the `model` field **verbatim** (no normalization — a
botched model name is its own bucket, easy to discard) and aggregated per
`(model × scenario_id)`.

This is an *internal-coherence* signal (does the reasoning match the artifact),
read alongside the existing gate/pass — not a correctness judge. We deliberately
do not pick a "winning" answer representation; all four are stored so they can
be correlated against the pass signal later (see `repr_signal.txt`).

Reuses:
  - evals.compare.load_results          (JSONL reading)
  - evals.rescore_cot._backfill_cot     (recover CoT from attempt_traces)
  - evals.rescore_cot._target_dsl       (successful attempt's DSL, else last)
  - evals.analyze_confidence.auc_roc    (pure-stdlib AUC for repr_signal.txt)
  - util.embeddings.EmbeddingClient / cosine

Usage:
    python -m evals.embedding_judge evals/results/*.jsonl \\
        --out-dir evals/embedding_judge_out \\
        --embedding-model embeddinggemma \\
        --embedding-base-url http://192.168.178.31:11434/v1
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from evals.analyze_confidence import auc_roc
from evals.compare import load_results
from evals.rescore_cot import _backfill_cot, _target_dsl
from util.embeddings import (
    DEFAULT_MAX_CHARS,
    DEFAULT_OVERLAP,
    DEFAULT_PER_CALL_TIMEOUT,
    EmbeddingClient,
    chunk_text,
    cosine,
    pool,
    text_hash,
)

# Answer representations, each rendered and scored separately.
REPRS = ["flat_dsl", "raw_dsl", "nl_ir", "tikz"]
REPR_PROMPT = "prompt"  # optional reasoning-relevance baseline

# Aggregations of a chunked CoT into one cot↔answer score, kept SEPARATE
# (evaluate later, discard the uninformative). The embeddinggemma endpoint caps
# at 2048 tokens, so long CoTs are chunked; each aggregation turns the chunk
# vectors into a single score:
#   max  — best-matching chunk ("does some part of the reasoning match the answer?")
#   mean — average per-chunk agreement
#   pooled — cosine of the token-count-weighted, L2-normalized mean chunk vector
AGGS = ("max", "mean", "pooled")

# Rendering-noise keys excluded from the flattened DSL text (geometry only).
_NOISE_KEYS = {"visible", "style", "opacity", "holes", "bbox"}


# ---------------------------------------------------------------------------
# Answer renderers — each takes a record and returns str | None
# ---------------------------------------------------------------------------

def _compact(v) -> str:
    """Compact, embedding-friendly rendering of a DSL value."""
    if v is None:
        return "none"
    if isinstance(v, list):
        return ",".join(_compact(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"), sort_keys=True)
    if isinstance(v, float):
        # trim trailing zeros for readability
        return repr(round(v, 6)).rstrip("0").rstrip(".") or "0"
    return str(v)


def render_flat_dsl(dsl_json) -> str | None:
    """Flatten `dsl_json.construction` ops to one readable line per op.

    Generic over all op types: ``op id k=v k=v …`` with rendering-noise keys
    dropped. Falls back to the whole JSON if there is no `construction` list.
    """
    if not isinstance(dsl_json, dict):
        return None
    ops = dsl_json.get("construction")
    if not ops:
        return json.dumps(dsl_json, sort_keys=True) if dsl_json else None
    lines: list[str] = []
    for c in ops:
        if not isinstance(c, dict):
            continue
        parts = [str(c.get("op", "?"))]
        cid = c.get("id")
        if cid:
            parts.append(str(cid))
        for k, v in c.items():
            if k in {"op", "id"} or k in _NOISE_KEYS or v is None:
                continue
            parts.append(f"{k}={_compact(v)}")
        lines.append(" ".join(parts))
    return "\n".join(lines) or None


def render_raw_dsl(dsl_json) -> str | None:
    """The full DSL JSON, verbatim — captures everything, syntactic noise included."""
    if not dsl_json:
        return None
    return json.dumps(dsl_json, sort_keys=True)


def _describe_ir_def(d: dict) -> str:
    """One short phrase for a `diagram_ir.define` statement, by `kind`."""
    kind = d.get("kind", "?")
    cid = d.get("id")
    name = cid if cid is not None else ""
    if kind == "point_fixed":
        return f"point {name} at ({d.get('x')},{d.get('y')})"
    if kind == "point_free":
        return f"point {name} free ~{d.get('hint_xy')}"
    if kind == "point_alias":
        return f"point {name} = {d.get('ref')}"
    if kind == "segment":
        return f"segment {d.get('a')}{d.get('b')}"
    if kind == "triangle":
        return f"triangle {d.get('a')}{d.get('b')}{d.get('c')}"
    if kind == "polygon":
        return "polygon " + ",".join(str(p) for p in (d.get("points") or []))
    if kind == "polygon_exterior":
        return f"polygon_exterior {d.get('a')}{d.get('b')} ref {d.get('ref')} sides {d.get('sides')}"
    if kind == "line_through":
        return f"line {d.get('p')}{d.get('q')}"
    if kind == "ray":
        return f"ray {d.get('a')}->{d.get('b')}"
    if kind == "line_perp_through":
        return f"perp through {d.get('through')} to {d.get('to_line')}"
    if kind == "line_parallel_through":
        return f"parallel through {d.get('through')} to {d.get('to_line')}"
    if kind == "line_angle_bisector":
        return f"angle bisector at {d.get('vertex')} of {d.get('a')}{d.get('b')}"
    if kind == "line_tangent":
        return f"tangent at {d.get('point')} to circle {d.get('circle')}"
    if kind == "point_midpoint":
        return f"{name} midpoint of {d.get('p')}{d.get('q')}"
    if kind == "point_between":
        return f"{name} between {d.get('a')}{d.get('b')} ratio {d.get('ratio')}"
    if kind == "point_intersection":
        return f"{name} = {d.get('obj1')} intersect {d.get('obj2')}"
    if kind == "point_on":
        return f"{name} on {d.get('on')}"
    if kind == "point_rotate":
        return f"{name} = rotate {d.get('source')} about {d.get('center')} by {d.get('angle')}"
    if kind == "point_reflect":
        return f"{name} = reflect {d.get('source')} across {d.get('across')}"
    if kind == "point_foot":
        return f"{name} = foot of {d.get('source')} onto {d.get('onto')}"
    if kind == "point_triangle_center":
        return f"{name} = {d.get('which')} of {d.get('tri')}"
    if kind == "circle_center_radius":
        return f"circle {name} center {d.get('center')} r {d.get('radius')}"
    if kind == "circle_center_point":
        return f"circle {name} center {d.get('center')} through {d.get('through')}"
    if kind == "circle_through3":
        return f"circle {name} through {d.get('a')}{d.get('b')}{d.get('c')}"
    if kind == "ellipse_center_axes":
        return f"ellipse {name} center {d.get('center')} r ({d.get('hradius')},{d.get('vradius')})"
    if kind == "arc_center_start_end":
        return f"arc {name} center {d.get('center')} {d.get('start')}->{d.get('end')}"
    if kind == "sector_center_start_end":
        return f"sector {name} center {d.get('center')} {d.get('start')}->{d.get('end')}"
    # generic fallback for any kind we haven't curated
    args = ",".join(f"{k}={_compact(v)}" for k, v in d.items() if k not in {"kind", "id"})
    return f"{kind} {name}({args})"


def render_nl_ir(diagram_ir) -> str | None:
    """Natural-language description built from the compiled `diagram_ir.define`."""
    if not isinstance(diagram_ir, dict):
        return None
    lines: list[str] = []
    for d in diagram_ir.get("define") or []:
        if isinstance(d, dict):
            lines.append(_describe_ir_def(d))
    canvas = diagram_ir.get("canvas")
    if isinstance(canvas, dict):
        lines.append(f"canvas {canvas.get('kind', '?')}")
    return "\n".join(lines) or None


def render_tikz(record: dict) -> str | None:
    t = record.get("tikz_code")
    if isinstance(t, str) and t.strip():
        return t
    return None


def render_prompt(record: dict) -> str | None:
    return record.get("user_prompt") or None


def render_record(record: dict, name: str) -> str | None:
    """Dispatch for an answer representation by name."""
    if name == "flat_dsl":
        return render_flat_dsl(_target_dsl(record))
    if name == "raw_dsl":
        return render_raw_dsl(_target_dsl(record))
    if name == "nl_ir":
        return render_nl_ir(record.get("diagram_ir"))
    if name == "tikz":
        return render_tikz(record)
    if name == REPR_PROMPT:
        return render_prompt(record)
    raise ValueError(f"unknown representation: {name!r}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _expand_paths(paths: Iterable[str]) -> list[Path]:
    """Accept files or directories (glob ``*.jsonl``). Returns sorted unique files."""
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for f in sorted(pp.glob("*.jsonl")):
                if f not in seen:
                    seen.add(f)
                    out.append(f)
        elif pp.is_file():
            if pp not in seen:
                seen.add(pp)
                out.append(pp)
    return out


def _variant_rank(src: Path) -> int:
    """Preference rank for the same run appearing in multiple files.

    Lower wins. `rescored` (current gate) > `original` > `backfill` (backfill is
    a redundant copy whose CoT is identical to the original's — both recover from
    `attempt_traces`).
    """
    n = src.name
    if "rescored" in n:
        return 0
    if "cotbackfill" in n:
        return 2
    return 1


def _run_identity(rec: dict, src: Path) -> tuple:
    """Unique key for a run. Falls back to including the source file when run_id
    is missing (rare) so unrelated records never collide."""
    run_id = rec.get("run_id")
    if run_id is None:
        return (run_id, rec.get("scenario_id"), rec.get("repeat_index"), rec.get("model"), str(src))
    return (run_id, rec.get("scenario_id"), rec.get("repeat_index"), rec.get("model"))


def _build_run(src: Path, rec: dict, cot: str, repr_names: list[str]) -> dict:
    reprs = {name: render_record(rec, name) for name in repr_names}
    return {
        "run_id": rec.get("run_id"),
        "model": rec.get("model") or "<missing>",
        "scenario_id": rec.get("scenario_id"),
        "tier": rec.get("tier"),
        "repeat_index": rec.get("repeat_index"),
        "strategy": rec.get("strategy"),
        "source_file": str(src),
        "gate_status": rec.get("gate_status"),
        "generation_success": rec.get("generation_success"),
        "svg_rendered": rec.get("svg_rendered"),
        "cot": cot,
        "cot_chars": len(cot),
        "reprs": reprs,
        "_record": rec,
    }


def _extract_runs(files: list[Path], with_prompt: bool) -> tuple[list[dict], dict]:
    """Recover CoT + answer texts per run, deduped by run identity.

    Returns (runs, coverage). A run may appear in several files (original,
    `*_rescored`, `*.cotbackfill`); we keep one — preferring `rescored` (current
    gate), then `original`, then `backfill` (a redundant copy). Records with no
    recoverable CoT are dropped and counted. `per_model_cot` counts unique
    (deduped) runs, not raw records.
    """
    repr_names = list(REPRS) + ([REPR_PROMPT] if with_prompt else [])
    kept: dict[tuple, tuple[int, dict]] = {}  # identity -> (rank, run_dict)
    cov: dict = defaultdict(int)
    cov["files"] = len(files)
    per_model_seen: dict[str, int] = defaultdict(int)
    per_model_cot: dict[str, int] = defaultdict(int)
    merged = 0

    for src in files:
        records = load_results(src)
        cov["records"] += len(records)
        rank = _variant_rank(src)
        for rec in records:
            model = rec.get("model") or "<missing>"
            per_model_seen[model] += 1
            cot = _backfill_cot(rec)  # recovers from attempt_traces if top-level empty
            if not cot:
                cov["no_cot"] += 1
                continue
            ident = _run_identity(rec, src)
            existing = kept.get(ident)
            if existing is None:
                kept[ident] = (rank, _build_run(src, rec, cot, repr_names))
                per_model_cot[model] += 1
            elif rank < existing[0]:
                kept[ident] = (rank, _build_run(src, rec, cot, repr_names))  # better variant
                merged += 1
            else:
                merged += 1  # duplicate variant, skip

    runs = [v[1] for v in kept.values()]
    cov["per_model_seen"] = dict(per_model_seen)
    cov["per_model_cot"] = dict(per_model_cot)
    cov["kept"] = len(runs)
    cov["duplicate_variants_merged"] = merged
    return runs, cov


def _agg_scores(
    cot_vecs: list[tuple[list[float], int]],
    ans_vecs: list[tuple[list[float], int]],
) -> dict[str, float | None]:
    """Three cot↔answer aggregations from chunk vectors (each is (vec, char_len)).

    Returns {max, mean, pooled}. max/mean are over all (cot_chunk, ans_chunk)
    pairs; pooled is cosine of the char-length-weighted, L2-normalized mean of
    each side's chunk vectors.
    """
    out: dict[str, float | None] = {a: None for a in AGGS}
    if not cot_vecs or not ans_vecs:
        return out
    cv = [v for v, _ in cot_vecs]
    cw = [w for _, w in cot_vecs]
    av = [v for v, _ in ans_vecs]
    aw = [w for _, w in ans_vecs]
    pc = pool(cv, cw)
    pa = pool(av, aw)
    out["pooled"] = cosine(pc, pa) if pc is not None and pa is not None else None
    pair = [cosine(c, a) for c in cv for a in av]
    out["max"] = max(pair) if pair else None
    out["mean"] = sum(pair) / len(pair) if pair else None
    return out


def _score_runs(runs: list[dict], repr_names: list[str]) -> None:
    """Fill `cos_<repr>_<agg>` and `cos_combined_<agg>` on each run in place.

    Uses `run['cot_vecs']` and `run['<repr>_vecs']` (lists of (vec, char_len))
    set up during the chunk-embedding pass in `run()`.
    """
    for run in runs:
        cot_vecs = run.get("cot_vecs", [])
        per_agg_avail: dict[str, list[float]] = {a: [] for a in AGGS}
        for name in repr_names:
            ans_vecs = run.get(f"{name}_vecs", [])
            scores = _agg_scores(cot_vecs, ans_vecs)
            for a in AGGS:
                run[f"cos_{name}_{a}"] = scores[a]
                if scores[a] is not None:
                    per_agg_avail[a].append(scores[a])
        for a in AGGS:
            run[f"cos_combined_{a}"] = (
                statistics.fmean(per_agg_avail[a]) if per_agg_avail[a] else None
            )


def _stats(values: list[float]) -> tuple[float | None, float | None, int]:
    """(mean, std, n) over non-null cosines. std is population stdev."""
    n = len(values)
    if n == 0:
        return None, None, 0
    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if n > 1 else 0.0
    return mean, std, n


def _aggregate(runs: list[dict], repr_names: list[str]) -> list[dict]:
    """Aggregate per (model, scenario_id). One row dict per cell."""
    cells: dict[tuple, dict] = defaultdict(
        lambda: {
            "model": None,
            "scenario_id": None,
            "tier": None,
            "n_runs": 0,
            "gate_pass": 0,
            "gen_success": 0,
            **{f"cos_{r}_{a}": [] for r in repr_names for a in AGGS},
            **{f"cos_combined_{a}": [] for a in AGGS},
        }
    )
    for run in runs:
        key = (run["model"], run["scenario_id"])
        c = cells[key]
        c["model"] = run["model"]
        c["scenario_id"] = run["scenario_id"]
        c["tier"] = run.get("tier")
        c["n_runs"] += 1
        if run.get("gate_status") == "pass":
            c["gate_pass"] += 1
        if run.get("generation_success"):
            c["gen_success"] += 1
        for r in repr_names:
            for a in AGGS:
                v = run.get(f"cos_{r}_{a}")
                if v is not None:
                    c[f"cos_{r}_{a}"].append(v)
        for a in AGGS:
            v = run.get(f"cos_combined_{a}")
            if v is not None:
                c[f"cos_combined_{a}"].append(v)

    rows: list[dict] = []
    for c in cells.values():
        row = {
            "model": c["model"],
            "scenario_id": c["scenario_id"],
            "tier": c["tier"],
            "n_runs": c["n_runs"],
            "gate_pass_rate": c["gate_pass"] / c["n_runs"] if c["n_runs"] else 0.0,
            "gen_success_rate": c["gen_success"] / c["n_runs"] if c["n_runs"] else 0.0,
        }
        for a in AGGS:
            m, s, n = _stats(c[f"cos_combined_{a}"])
            row[f"cos_combined_{a}_mean"] = m
            row[f"cos_combined_{a}_std"] = s
            row[f"cos_combined_{a}_n"] = n
        for r in repr_names:
            for a in AGGS:
                m, _, _ = _stats(c[f"cos_{r}_{a}"])
                row[f"cos_{r}_{a}_mean"] = m
        rows.append(row)
    rows.sort(key=lambda r: (str(r["model"]), str(r["scenario_id"])))
    return rows


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_runs_jsonl(runs: list[dict], repr_names: list[str], path: Path) -> None:
    with path.open("w") as fh:
        for run in runs:
            out = {
                "run_id": run["run_id"],
                "model": run["model"],
                "scenario_id": run["scenario_id"],
                "tier": run["tier"],
                "repeat_index": run["repeat_index"],
                "strategy": run["strategy"],
                "source_file": run["source_file"],
                "gate_status": run["gate_status"],
                "generation_success": run["generation_success"],
                "svg_rendered": run["svg_rendered"],
                "cot_chars": run["cot_chars"],
                "cot_chunks": len(run.get("cot_chunks", [])),
            }
            for r in repr_names:
                txt = run["reprs"].get(r)
                out[f"chars_{r}"] = len(txt) if txt else 0
                out[f"chunks_{r}"] = len(run.get(f"{r}_chunks", []))
                for a in AGGS:
                    out[f"cos_{r}_{a}"] = run.get(f"cos_{r}_{a}")
            for a in AGGS:
                out[f"cos_combined_{a}"] = run.get(f"cos_combined_{a}")
            fh.write(json.dumps(out) + "\n")


def _write_matrix_csv(rows: list[dict], repr_names: list[str], path: Path) -> None:
    cols = ["model", "scenario_id", "tier", "n_runs", "gate_pass_rate", "gen_success_rate"]
    for a in AGGS:
        cols += [f"cos_combined_{a}_mean", f"cos_combined_{a}_std", f"cos_combined_{a}_n"]
    for r in repr_names:
        for a in AGGS:
            cols.append(f"cos_{r}_{a}_mean")
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) for c in cols])


def _fmt(v, default="") -> str:
    if v is None:
        return default
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _write_summary_txt(rows: list[dict], repr_names: list[str], path: Path) -> None:
    cols = ["model", "scenario_id", "n", "gate%", "comb_max", "comb_mean", "comb_pooled"]
    widths = {"model": 34, "scenario_id": 40, "n": 4, "gate%": 6,
              "comb_max": 9, "comb_mean": 10, "comb_pooled": 11}
    header = "  ".join(c.ljust(widths.get(c, 8)) for c in cols)
    lines = [header, "-" * len(header)]
    for r in rows:
        cells = {
            "model": _fmt(r["model"]),
            "scenario_id": _fmt(r["scenario_id"]),
            "n": _fmt(r["n_runs"]),
            "gate%": f"{r['gate_pass_rate'] * 100:.0f}",
            "comb_max": _fmt(r.get("cos_combined_max_mean")),
            "comb_mean": _fmt(r.get("cos_combined_mean_mean")),
            "comb_pooled": _fmt(r.get("cos_combined_pooled_mean")),
        }
        lines.append("  ".join(cells[c].ljust(widths.get(c, 8)) for c in cols))
    path.write_text("\n".join(lines) + "\n")


def _write_coverage_txt(cov: dict, runs: list[dict], repr_names: list[str], path: Path) -> None:
    lines: list[str] = []
    lines.append("Coverage report")
    lines.append("=" * 40)
    lines.append(f"files:           {cov.get('files', 0)}")
    lines.append(f"records seen:    {cov.get('records', 0)}")
    lines.append(f"unique w/ CoT:    {cov.get('kept', 0)}  (kept, deduped)")
    lines.append(f"records no CoT:  {cov.get('no_cot', 0)}  (dropped)")
    lines.append(f"dup variants:    {cov.get('duplicate_variants_merged', 0)}  (rescored>original>backfill, by run identity)")
    lines.append("")
    lines.append("Per-model breakdown (records seen -> unique CoT runs kept):")
    seen = cov.get("per_model_seen", {})
    kept = cov.get("per_model_cot", {})
    for model in sorted(seen):
        lines.append(f"  {model:40s} seen={seen[model]:5d}  cot={kept.get(model, 0):5d}")
    lines.append("")
    lines.append("Answer-representation availability (over kept runs):")
    n = len(runs)
    for r in repr_names:
        avail = sum(1 for run in runs if run["reprs"].get(r))
        lines.append(f"  {r:10s} {avail:5d} / {n}")
    path.write_text("\n".join(lines) + "\n")


def _write_repr_signal_txt(runs: list[dict], repr_names: list[str], path: Path) -> None:
    """Informational: per (representation × aggregation), how well cos separates
    gate pass/fail. The grid to read when choosing which rep/agg to keep."""
    lines: list[str] = []
    lines.append("Representation × aggregation signal report (informational — not a discard directive)")
    lines.append("AUC for predicting gate_status==pass from each cos_<rep>_<agg>, over runs with a")
    lines.append("definite pass/fail gate. Higher AUC = that (rep, agg) tracks correctness better.")
    lines.append("=" * 78)
    header = f"{'repr':12s} {'agg':7s} {'n':>5s} {'pass_mean':>10s} {'fail_mean':>10s} {'AUC':>7s}"
    lines.append(header)
    lines.append("-" * len(header))
    # rows: each rep × agg, then combined × agg
    entries: list[tuple[str, str, str]] = []
    for r in repr_names:
        for a in AGGS:
            entries.append((r, a, f"cos_{r}_{a}"))
    for a in AGGS:
        entries.append(("combined", a, f"cos_combined_{a}"))
    for label, agg, key in entries:
        scores: list[float] = []
        labels: list[int] = []
        for run in runs:
            v = run.get(key)
            gs = run.get("gate_status")
            if v is None or gs not in ("pass", "fail"):
                continue
            scores.append(v)
            labels.append(1 if gs == "pass" else 0)
        if not scores or len(set(labels)) < 2:
            lines.append(f"{label:12s} {agg:7s} {len(scores):5d} {'-':>10s} {'-':>10s} {'-':>7s}")
            continue
        pass_scores = [s for s, l in zip(scores, labels) if l == 1]
        fail_scores = [s for s, l in zip(scores, labels) if l == 0]
        pm = statistics.fmean(pass_scores) if pass_scores else None
        fm = statistics.fmean(fail_scores) if fail_scores else None
        auc = auc_roc(scores, labels)
        lines.append(
            f"{label:12s} {agg:7s} {len(scores):5d} {_fmt(pm):>10s} {_fmt(fm):>10s} {_fmt(auc):>7s}"
        )
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def run(
    paths: list[str],
    out_dir: str,
    *,
    embedding_model: str,
    embedding_base_url: str,
    embedding_api_key: str = "ollama",
    concurrency: int = 3,
    batch_size: int = 8,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
    per_call_timeout: float = DEFAULT_PER_CALL_TIMEOUT,
    with_prompt: bool = False,
    client: EmbeddingClient | None = None,
) -> dict:
    """Run the embedding judge end-to-end. Returns a small summary dict."""
    files = _expand_paths(paths)
    if not files:
        print("No JSONL files found.", file=sys.stderr)
        return {"files": 0}

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    repr_names = list(REPRS) + ([REPR_PROMPT] if with_prompt else [])

    runs, cov = _extract_runs(files, with_prompt)
    print(f"Loaded {cov['records']} records from {len(files)} files; {len(runs)} have CoT.")

    if not runs:
        print("No runs with recoverable CoT — nothing to score.", file=sys.stderr)
        _write_coverage_txt(cov, runs, repr_names, out / "coverage.txt")
        return {"files": len(files), "runs": 0}

    # Chunk every document (cot + available answer reprs). embeddinggemma caps
    # at 2048 tokens (~6000 chars); chunking keeps each request under the cap so
    # no CoT content is silently dropped.
    all_chunks: dict[str, str] = {}  # hash -> chunk text
    total_chunks = 0
    for run in runs:
        cot_chunks = chunk_text(run["cot"], max_chars, overlap)
        run["cot_chunks"] = cot_chunks
        total_chunks += len(cot_chunks)
        for ch in cot_chunks:
            all_chunks[text_hash(ch)] = ch
        for name in repr_names:
            txt = run["reprs"].get(name)
            if not txt:
                run[f"{name}_chunks"] = []
                continue
            chs = chunk_text(txt, max_chars, overlap)
            run[f"{name}_chunks"] = chs
            total_chunks += len(chs)
            for ch in chs:
                all_chunks[text_hash(ch)] = ch

    client_owned = client is None
    if client_owned:
        client = EmbeddingClient(
            base_url=embedding_base_url,
            model=embedding_model,
            api_key=embedding_api_key,
            concurrency=concurrency,
            batch_size=batch_size,
            max_chars=max_chars,
            overlap=overlap,
            per_call_timeout=per_call_timeout,
            cache_path=str(out / "embeddings_cache.sqlite"),
        )

    chunk_hashes = list(all_chunks.keys())
    chunk_texts = [all_chunks[h] for h in chunk_hashes]
    n_batches = (len(chunk_texts) + batch_size - 1) // batch_size
    print(
        f"Chunked {len(runs)} runs into {total_chunks} chunks "
        f"({len(chunk_hashes)} unique, {n_batches} batches); embedding…",
        flush=True,
    )

    _last = [time.time()]
    _start = [time.time()]

    def _progress(done: int, total: int) -> None:
        if total == 0:
            return
        now = time.time()
        if now - _last[0] >= 15 or done >= total:
            _last[0] = now
            pct = 100.0 * done / total
            elapsed = now - _start[0]
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (total - done) / rate if rate > 0 else 0.0
            print(
                f"  … {done}/{total} chunks ({pct:.0f}%) — "
                f"{rate:.1f} chunks/s, ETA {eta:.0f}s",
                flush=True,
            )

    t0 = time.time()
    vectors = await client.embed_texts(chunk_texts, on_progress=_progress)
    print(f"  embedded {len(chunk_hashes)} unique chunks in {time.time() - t0:.0f}s", flush=True)

    # hash -> list[(vec, char_len)]. Normal chunk: one entry; a chunk that
    # exceeded the cap (None) is halved on-stall into sub-chunk vectors.
    h2vecs: dict[str, list[tuple[list[float], int]]] = {}
    none_hashes: list[str] = []
    for h, t, v in zip(chunk_hashes, chunk_texts, vectors):
        if v is not None:
            h2vecs[h] = [(v, len(t))]
        else:
            none_hashes.append(h)
            h2vecs[h] = []
    for h in none_hashes:
        h2vecs[h] = await client.resolve_chunk(all_chunks[h])
    if none_hashes:
        print(f"  halve-on-stall: resolved {len(none_hashes)} over-cap chunks.")

    # Reassemble each document's chunk vectors.
    def _reassemble(chunks: list[str]) -> list[tuple[list[float], int]]:
        out_v: list[tuple[list[float], int]] = []
        for ch in chunks:
            out_v.extend(h2vecs.get(text_hash(ch), []))
        return out_v

    for run in runs:
        run["cot_vecs"] = _reassemble(run["cot_chunks"])
        for name in repr_names:
            run[f"{name}_vecs"] = _reassemble(run[f"{name}_chunks"])

    _score_runs(runs, repr_names)
    rows = _aggregate(runs, repr_names)

    _write_runs_jsonl(runs, repr_names, out / "runs.jsonl")
    _write_matrix_csv(rows, repr_names, out / "matrix.csv")
    _write_summary_txt(rows, repr_names, out / "summary.txt")
    _write_coverage_txt(cov, runs, repr_names, out / "coverage.txt")
    _write_repr_signal_txt(runs, repr_names, out / "repr_signal.txt")

    print(f"Wrote outputs to {out}/")
    print(f"  runs.jsonl ({len(runs)} runs), matrix.csv ({len(rows)} model×scenario cells),")
    print("  summary.txt, coverage.txt, repr_signal.txt")
    if client_owned:
        await client.aclose()  # close the httpx pool cleanly (no abrupt connection drops)
    return {"files": len(files), "runs": len(runs), "cells": len(rows), "chunks": total_chunks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+", help="JSONL files and/or directories (globbed for *.jsonl)")
    ap.add_argument("--out-dir", default="evals/embedding_judge_out")
    ap.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL", "embeddinggemma"),
    )
    ap.add_argument(
        "--embedding-base-url",
        default=os.environ.get("EMBEDDING_BASE_URL", "http://192.168.178.31:11434/v1"),
    )
    ap.add_argument(
        "--embedding-api-key",
        default=os.environ.get("EMBEDDING_API_KEY", "ollama"),
    )
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"chunk size in chars (default {DEFAULT_MAX_CHARS}, calibrated to the "
        f"2048-token embeddinggemma cap); long texts are chunked, not truncated",
    )
    ap.add_argument(
        "--overlap",
        type=int,
        default=DEFAULT_OVERLAP,
        help=f"overlap between chunks in chars (default {DEFAULT_OVERLAP})",
    )
    ap.add_argument(
        "--per-call-timeout",
        type=float,
        default=DEFAULT_PER_CALL_TIMEOUT,
        help=f"per-request timeout in seconds (default {DEFAULT_PER_CALL_TIMEOUT}); "
        "over-cap chunks are halved on timeout",
    )
    ap.add_argument(
        "--with-prompt-baseline",
        action="store_true",
        help="also embed user_prompt and score cos_prompt (reasoning-relevance baseline)",
    )
    args = ap.parse_args()
    asyncio.run(
        run(
            args.paths,
            args.out_dir,
            embedding_model=args.embedding_model,
            embedding_base_url=args.embedding_base_url,
            embedding_api_key=args.embedding_api_key,
            concurrency=args.concurrency,
            batch_size=args.batch_size,
            max_chars=args.max_chars,
            overlap=args.overlap,
            per_call_timeout=args.per_call_timeout,
            with_prompt=args.with_prompt_baseline,
        )
    )


if __name__ == "__main__":
    main()