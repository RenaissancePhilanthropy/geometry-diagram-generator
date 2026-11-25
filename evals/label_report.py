"""Label-placement regression report: re-render stored figures and measure how well each label
stays attached to what it labels, so a change to the label placement (or a comparison of two
commits) is judged on real figures, not only on hand-made ones. No model calls: every record in
the eval results carries its ``diagram_ir``.

    # measure with the code in this checkout
    python -m evals.label_report run --results evals/results --sample 300 --out after.json
    # measure with another checkout's geometry_diagrams (a `git worktree add` of the old commit)
    python -m evals.label_report run --results evals/results --sample 300 --out before.json \\
        --code-root /path/to/old/worktree
    python -m evals.label_report compare before.json after.json

The measurement reads only the SVG (``measure_svg``): a label's ``data-bbox``/``data-for``/
``data-role`` and, for what it labels, the drawn lines' ``data-endpoints`` and pixel ends, the
circles' ``data-center`` and the drawn points. So it works on the output of any version of the
renderer. A label is *unmeasured* when what it labels has no drawn pixel position (an undrawn
point with no incident drawn line, an arc).

Measures per figure:

- ``point_on_dot``: a point label whose box is closer to its point than the dot plus a hair;
- ``point_far``: a point label whose box is more than ``POINT_MAX_GAP`` px from its point;
- ``segment_far``: a straight segment's label whose centre is more than ``SEGMENT_MAX_DRIFT`` px
  from the segment's line, or whose projection falls well past either end;
- ``label_overlaps``: pairs of label boxes that overlap.

These thresholds are the ones ``to_svg`` uses to re-attach a label (``_POINT_LABEL_MIN_GAP``,
``_POINT_LABEL_MAX_GAP``, ``_SEGMENT_LABEL_MAX_DRIFT``); they are repeated here so the report does
not depend on the code under test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

POINT_MIN_GAP = 4.0       # px, box to point: closer covers the dot (radius 2.5)
POINT_MAX_GAP = 20.0
SEGMENT_MAX_DRIFT = 20.0
SEGMENT_T_RANGE = (-0.15, 1.15)
_MEASURES = ("point_on_dot", "point_far", "segment_far", "label_overlaps")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _gap_to_point(box: tuple[float, float, float, float], px: float, py: float) -> float:
    return math.hypot(max(box[0] - px, 0.0, px - box[2]), max(box[1] - py, 0.0, py - box[3]))


def measure_svg(svg: str) -> dict[str, Any]:
    """The label measurements of one rendered SVG (see the module docstring)."""
    root = ET.fromstring(svg)
    points: dict[str, tuple[float, float]] = {}
    lines: dict[str, tuple[float, float, float, float]] = {}
    labels: list[dict[str, Any]] = []
    for el in root.iter():
        tag, a = _local(el.tag), el.attrib
        role = a.get("data-role", "")
        if role.startswith("label-") and "data-bbox" in a:
            x0, y0, x1, y1 = (float(v) for v in a["data-bbox"].split(","))
            labels.append({"role": role, "for": a.get("data-for", ""), "text": a.get("data-label-text", ""),
                           "bbox": (x0, y0, x1, y1)})
        elif tag == "circle" and a.get("data-type") == "point":
            points[a["data-ir-id"]] = (float(a["cx"]), float(a["cy"]))
        elif tag == "circle" and "data-center" in a:
            points.setdefault(a["data-center"], (float(a["cx"]), float(a["cy"])))
        elif tag == "line" and a.get("data-type") == "segment" and "data-endpoints" in a:
            p, q = a["data-endpoints"].split(",")
            x1, y1, x2, y2 = (float(a[k]) for k in ("x1", "y1", "x2", "y2"))
            points.setdefault(p, (x1, y1))
            points.setdefault(q, (x2, y2))
            lines[a["data-ir-id"]] = (x1, y1, x2, y2)

    out: list[dict[str, Any]] = []
    measured = {m: 0 for m in _MEASURES}
    unmeasured = 0
    for lab in labels:
        entry = {"role": lab["role"], "for": lab["for"], "text": lab["text"]}
        bb = lab["bbox"]
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        if lab["role"] == "label-point" and lab["for"] in points:
            gap = _gap_to_point(bb, *points[lab["for"]])
            entry["gap"] = round(gap, 1)
            measured["point_on_dot"] += gap < POINT_MIN_GAP
            measured["point_far"] += gap > POINT_MAX_GAP
        elif lab["role"] == "label-segment" and lab["for"] in lines:
            ax, ay, bx, by = lines[lab["for"]]
            length = math.hypot(bx - ax, by - ay) or 1.0
            drift = abs((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / length
            t = ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / length ** 2
            entry["drift"] = round(drift, 1)
            entry["t"] = round(t, 2)
            measured["segment_far"] += drift > SEGMENT_MAX_DRIFT or not SEGMENT_T_RANGE[0] <= t <= SEGMENT_T_RANGE[1]
        elif lab["role"] in ("label-point", "label-segment"):
            unmeasured += 1
        out.append(entry)
    for i, a in enumerate(labels):
        for b in labels[:i]:
            if not (a["bbox"][2] <= b["bbox"][0] or b["bbox"][2] <= a["bbox"][0]
                    or a["bbox"][3] <= b["bbox"][1] or b["bbox"][3] <= a["bbox"][1]):
                measured["label_overlaps"] += 1
    return {"labels": out, "unmeasured": unmeasured, **measured}


def _use_code_root(code_root: str | None) -> None:
    """Import geometry_diagrams from ``code_root`` (another checkout), and refuse to go on if it
    does not: a stale PYTHONPATH silently measuring the wrong code is the failure to avoid."""
    if code_root is None:
        return
    root = str(Path(code_root).resolve())
    sys.path.insert(0, root)
    import geometry_diagrams
    where = str(Path(geometry_diagrams.__file__).resolve())
    if not where.startswith(root):
        raise SystemExit(f"--code-root {root}, but geometry_diagrams was imported from {where}")


def load_figures(results: Path, sample: int, seed: int) -> list[dict[str, Any]]:
    """Up to ``sample`` distinct stored figures from the eval result files (JSONL, or a directory
    of them): records that carry a ``diagram_ir``, deduplicated by content, a seeded sample."""
    files = sorted(results.glob("*.jsonl")) if results.is_dir() else [results]
    seen: dict[str, dict[str, Any]] = {}
    for f in files:
        for line in f.read_text().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ir = rec.get("diagram_ir")
            if not ir or not rec.get("svg_rendered", True):
                continue
            key = hashlib.sha1(json.dumps(ir, sort_keys=True).encode()).hexdigest()[:16]
            seen.setdefault(key, {"key": key, "scenario": rec.get("scenario_id"),
                                  "strategy": rec.get("strategy"), "diagram_ir": ir})
    figures = [seen[k] for k in sorted(seen)]
    random.Random(seed).shuffle(figures)
    return figures[:sample]


async def _render(diagram_ir: dict) -> str:
    from geometry_diagrams.ir.ir import DiagramIR
    from geometry_diagrams.ir.renderer import SVGRenderer
    from geometry_diagrams.strategies.ir_pipeline import run_ir_pipeline
    result = await run_ir_pipeline(DiagramIR.model_validate(diagram_ir), SVGRenderer(embed_fonts=False))
    return result.svg


def run_report(figures: list[dict[str, Any]], progress: bool = True) -> dict[str, Any]:
    import asyncio
    import geometry_diagrams
    rows: dict[str, Any] = {}
    failed = 0
    for n, fig in enumerate(figures, 1):
        try:
            svg = asyncio.run(_render(fig["diagram_ir"]))
            rows[fig["key"]] = {"scenario": fig["scenario"], "strategy": fig["strategy"], **measure_svg(svg)}
        except Exception as exc:  # a stored figure the code cannot render is not a label finding
            failed += 1
            rows[fig["key"]] = {"scenario": fig["scenario"], "strategy": fig["strategy"], "error": str(exc)[:120]}
        if progress and n % 50 == 0:
            print(f"  {n}/{len(figures)}", file=sys.stderr)
    return {"code": str(Path(geometry_diagrams.__file__).resolve().parent), "figures": rows, "failed": failed}


def totals(report: dict[str, Any]) -> dict[str, int]:
    rows = [r for r in report["figures"].values() if "error" not in r]
    out = {m: sum(r[m] for r in rows) for m in _MEASURES}
    out["figures"] = len(rows)
    out["labels"] = sum(len(r["labels"]) for r in rows)
    return out


def compare(before: dict[str, Any], after: dict[str, Any], show: int = 8) -> str:
    """A text diff of two reports over the figures both rendered."""
    common = sorted(k for k in before["figures"] if k in after["figures"]
                    and "error" not in before["figures"][k] and "error" not in after["figures"][k])
    lines = [f"figures compared: {len(common)} (before: {before['code']}, after: {after['code']})"]
    movers: dict[str, list[tuple[int, str]]] = {m: [] for m in _MEASURES}
    for m in _MEASURES:
        b = sum(before["figures"][k][m] for k in common)
        a = sum(after["figures"][k][m] for k in common)
        better = sum(1 for k in common if after["figures"][k][m] < before["figures"][k][m])
        worse = sum(1 for k in common if after["figures"][k][m] > before["figures"][k][m])
        lines.append(f"  {m:15} {b:5} -> {a:5}  ({a - b:+d})   figures better {better}, worse {worse}")
        for k in common:
            d = after["figures"][k][m] - before["figures"][k][m]
            if d:
                movers[m].append((d, k))
    for m in _MEASURES:
        worst = sorted(movers[m], reverse=True)[:show]
        if worst and worst[0][0] > 0:
            lines.append(f"  worse on {m}: " + ", ".join(
                f"{after['figures'][k]['scenario']}[{k[:6]}] {d:+d}" for d, k in worst if d > 0))
    only = len(set(before["figures"]) ^ set(after["figures"]))
    if only or before["failed"] or after["failed"]:
        lines.append(f"  not compared: {only} figure(s) in one report only; render failures before {before['failed']}, "
                     f"after {after['failed']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="render stored figures and write a report")
    run.add_argument("--results", type=Path, default=Path("evals/results"))
    run.add_argument("--sample", type=int, default=300)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--code-root", help="a checkout whose geometry_diagrams to measure instead of this one")
    cmp_ = sub.add_parser("compare", help="diff two reports")
    cmp_.add_argument("before", type=Path)
    cmp_.add_argument("after", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        _use_code_root(args.code_root)
        figures = load_figures(args.results, args.sample, args.seed)
        report = run_report(figures)
        args.out.write_text(json.dumps(report))
        print(f"{len(figures)} figures from {args.results}; code {report['code']}; totals {totals(report)}")
    else:
        print(compare(json.loads(args.before.read_text()), json.loads(args.after.read_text())))


if __name__ == "__main__":
    main()
