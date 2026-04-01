"""Output formatting and JSONL I/O for eval results."""
from __future__ import annotations

import json
from pathlib import Path


def _externalize_traces(record: dict, traces_dir: Path) -> None:
    """Write phase_traces to a separate JSON file and replace with a relative path."""
    traces = record.get("phase_traces")
    if not traces:
        return
    scenario_id = record.get("scenario_id", "unknown")
    repeat = record.get("repeat_index", 1)
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace_file = traces_dir / f"{scenario_id}_r{repeat:03d}.json"
    with trace_file.open("w") as f:
        json.dump(traces, f)
    # Store relative path (relative to the traces_dir's parent, i.e. output_dir)
    record["phase_traces"] = str(trace_file.relative_to(traces_dir.parent.parent))


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def _tikz_check_summary(record: dict) -> str:
    """Return a compact tikz check summary string like 'TIK:3/4(1skip)'."""
    tc = record.get("tikz_checks") or {}
    if not tc:
        return ""
    total = len(tc)
    passed = sum(
        1 for v in tc.values()
        if isinstance(v, dict) and v.get("passed") is True
    )
    skipped = sum(
        1 for v in tc.values()
        if isinstance(v, dict) and v.get("skipped") is True
    )
    if skipped:
        return f" TIK:{passed}/{total}({skipped}skip)"
    return f" TIK:{passed}/{total}"


def _gate_summary(record: dict) -> str:
    status = record.get("gate_status")
    if not status:
        return ""
    return f" G:{status}"


def _print_record(record: dict) -> None:
    status = "OK " if record["generation_success"] else "ERR"
    svg = "SVG:ok  " if record["svg_rendered"] else "SVG:fail"
    svg_chk = record.get("svg_checks") or {}
    checks = "CHK:ok  " if svg_chk.get("passed") else "CHK:fail"
    judge_str = ""
    if record.get("llm_judge_score") is not None:
        judge_str = f" J:{record['llm_judge_score']}/5"
    duration = f"{record['duration_s']:.1f}s" if record["duration_s"] is not None else "?"
    repeat = f"r{record.get('repeat_index', 1):03d}"
    error = f" [{record['error'][:60]}]" if record.get("error") else ""
    tik_str = _tikz_check_summary(record)
    gate_str = _gate_summary(record)
    query_str = ""
    qr_list = record.get("query_results", [])
    if qr_list:
        q_total = len(qr_list)
        q_called = sum(1 for q in qr_list if q.get("tool_called"))
        q_type = sum(1 for q in qr_list if q.get("query_type_match"))
        query_str = f" Q:{q_called}/{q_total} QT:{q_type}/{q_total}"
    print(
        f"  [{status}] {record['scenario_id']:<25} {repeat} {svg} {checks} "
        f"{duration:>7}{judge_str}{tik_str}{gate_str}{error}{query_str}"
    )


def _print_summary(records: list[dict]) -> None:
    from collections import defaultdict

    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_strategy[r["strategy"]].append(r)

    print("\n--- Summary ---")
    for strategy, recs in sorted(by_strategy.items()):
        n = len(recs)
        gen_ok = sum(1 for r in recs if r["generation_success"])
        svg_ok = sum(1 for r in recs if r["svg_rendered"])
        svg_chk_ok = sum(1 for r in recs if (r.get("svg_checks") or {}).get("passed"))
        gate_ok = sum(1 for r in recs if r.get("gate_status") == "pass")
        gate_soft = sum(1 for r in recs if r.get("gate_status") == "soft_pass")
        avg_s = sum(r["duration_s"] for r in recs if r["duration_s"]) / max(n, 1)
        retry_rate = sum(r.get("retries", 0) for r in recs) / max(n, 1)

        judge_scores = [r["llm_judge_score"] for r in recs if r.get("llm_judge_score") is not None]
        judge_str = f"  judge:{sum(judge_scores)/len(judge_scores):.1f}/5" if judge_scores else ""
        gate_judge_scores = [
            r["llm_judge_score"]
            for r in recs
            if r.get("gate_status") == "pass" and r.get("llm_judge_score") is not None
        ]
        gate_judge_str = (
            f"  judge(pass):{sum(gate_judge_scores)/len(gate_judge_scores):.1f}/5"
            if gate_judge_scores else ""
        )

        # Tikz check aggregation
        tik_total = sum(len(r.get("tikz_checks") or {}) for r in recs)
        tik_pass = sum(
            sum(1 for v in (r.get("tikz_checks") or {}).values()
                if isinstance(v, dict) and v.get("passed") is True)
            for r in recs
        )
        tik_skip = sum(
            sum(1 for v in (r.get("tikz_checks") or {}).values()
                if isinstance(v, dict) and v.get("skipped") is True)
            for r in recs
        )
        tik_str = ""
        if tik_total:
            tik_str = f"  tik:{tik_pass}/{tik_total}"
            if tik_skip:
                tik_str += f"({tik_skip}skip)"

        # Query eval aggregation
        q_total = sum(len(r.get("query_results", [])) for r in recs)
        q_called = sum(
            sum(1 for q in r.get("query_results", []) if q.get("tool_called"))
            for r in recs
        )
        q_type = sum(
            sum(1 for q in r.get("query_results", []) if q.get("query_type_match"))
            for r in recs
        )
        q_str = ""
        if q_total:
            q_str = f"  query:{q_called}/{q_total} qtype:{q_type}/{q_total}"

        print(
            f"  {strategy:<12}  gen:{gen_ok}/{n}  svg:{svg_ok}/{n}  "
            f"svgchk:{svg_chk_ok}/{n}  gate:{gate_ok}/{n}"
            f" soft:{gate_soft}/{n}  retries:{retry_rate:.1f}"
            f"{judge_str}{gate_judge_str}{tik_str}  avg:{avg_s:.1f}s{q_str}"
        )
