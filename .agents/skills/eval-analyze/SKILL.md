---
name: eval-analyze
description: Use when analyzing geometry eval results to diagnose failures and improve code. Triggered by "analyze evals", "check results", "run and analyze", or "what's failing".
---

# Eval Analyze

Diagnose eval failures and improve the geometry pipeline systematically.

## Entry Points

| User says | Action |
|-----------|--------|
| "analyze evals", "check results", "what's failing" | Find latest JSONL in `evals/results/`, proceed to Analysis |
| "run evals", "run and analyze" | Run evals first (see below), then proceed to Analysis |
| "compare runs" | `python -m evals.compare <old.jsonl> <new.jsonl>` |

### Running Evals (only when requested)

```bash
uv run python -m evals.run --scenarios evals/scenarios_core.yaml --strategies structured --repeats 3 --output evals/results
```

Scenario files: `scenarios_core.yaml` (13, default), `scenarios_smoke.yaml` (4, fast), `scenarios.yaml` (26, full), `scenarios_generalization.yaml` (13).

## Analysis Workflow

### Step 1: Summary

Read the latest JSONL in `evals/results/`. Report:
- Overall gate pass rate (pass / soft_pass / fail counts)
- Per-scenario breakdown
- Flag scenarios failing on all repeats vs intermittently (intermittent = flaky)

### Step 2: Categorize Failures

Read failing records. Classify each failure by pipeline stage:

| Category | JSONL signals | Source files |
|----------|--------------|--------------|
| **Generation** | `generation_success=false`, `error` field | `strategies/structured.py`, `strategies/instructions.py` |
| **SVG Render** | `svg_rendered=false`, LaTeX/dvisvgm error | `ir/to_tikz.py`, `renderer/` |
| **Geometric** | `sympy_property_checks` failures, `tikz_checks` failures | `ir/to_sympy.py`, `ir/checks.py` |
| **Structural/IR** | `structural_checks` failures, IR compile errors | `ir/ir.py`, `ir/to_sympy.py` |
| **Strategy/Prompt** | Correct structure but wrong geometry; same mistake across all retries | `strategies/instructions.py` |

### Step 3: Diagnose Root Causes

For each failure category with hits:
1. Read the specific failing JSONL fields (e.g., `sympy_property_checks` entries where `passed=false`, `gate_failures` list)
2. Read the `diagram_ir` field for structured strategy failures to see what the LLM produced
3. Read relevant source files from the table above
4. Identify the root cause: bad IR lowering, missing check, prompt ambiguity, TikZ generation bug, etc.

### Step 4: Report

Present findings grouped by category:
- Scenario name + repeat consistency (e.g., "fails 3/3 repeats")
- Specific failure (e.g., `sympy check midpoint_M fails`)
- Root cause diagnosis
- Suggested fix with file path

### Step 5: Fix (only when requested)

Implement fixes. When done, ask the user: "Want me to re-run evals to confirm?"

**Do NOT automatically re-run evals or loop.** The user decides when to re-run.
