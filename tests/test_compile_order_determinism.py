"""Compile order (and so the shared RNG's consumption) must not depend on PYTHONHASHSEED."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_SCRIPT = """
from geometry_diagrams.ir.ir import DiagramIR, PointFree, PointFixed, PointMidpoint, Segment
from geometry_diagrams.ir.to_sympy import compile_defs
import json
# Dependents come first (forward references) so predecessor iteration order
# decides which free point is compiled, and so seeded, first.
defs = [Segment(id="s", a="N", b="P1"),
        PointMidpoint(id="N", p="M", q="P3"),
        PointMidpoint(id="M", p="P5", q="P0"),
        PointMidpoint(id="K", p="P2", q="P4")]
defs += [PointFree(id=f"P{i}") for i in range(6)]
defs += [PointFixed(id="O", x=0, y=0)]
sym = compile_defs(DiagramIR(define=defs))
print(json.dumps({k: [float(sym[k].x), float(sym[k].y)] for k in ("P0","P1","P2","P3","P4","P5","N")}))
"""


def _run(seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-c", _SCRIPT], env=env, capture_output=True, text=True, check=True, timeout=120
    ).stdout


def test_free_points_identical_across_hash_seeds():
    outs = {_run(s) for s in ("0", "1", "2", "12345")}
    assert len(outs) == 1
