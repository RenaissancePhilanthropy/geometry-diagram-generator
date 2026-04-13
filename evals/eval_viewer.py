"""
Eval Viewer — standalone server for browsing and re-rendering eval results.

Runs on port 8002. Serves:
  GET  /api/runs                           — list all eval runs
  GET  /api/runs/{run_id}                  — all records for a run (metadata)
  GET  /api/runs/{run_id}/records/{index}  — full record detail
  GET  /api/runs/{run_id}/svg/{index}      — serve the saved SVG file
  POST /api/compile-ir                     — compile IR → TikZ → SVG
  POST /api/render-tikz                    — render TikZ → SVG

Requires the TikZ renderer container running at localhost:8001 for compile/render.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as `python evals/eval_viewer.py`
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import json

import uvicorn
from dotenv import load_dotenv
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from ir.errors import IRCompileError
from ir.ir import DiagramIR
from ir.to_sympy import compile_defs
from ir.checks import run_checks
from ir.renderer import TikZRenderer
from util.tikz_renderer import render_tikz

load_dotenv()

RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# JSONL loading — lazy, cached in memory
# ---------------------------------------------------------------------------

_run_cache: dict[str, list[dict]] = {}


def _load_run(run_id: str) -> list[dict] | None:
    if run_id in _run_cache:
        return _run_cache[run_id]
    path = RESULTS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        return None
    records = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    _run_cache[run_id] = records
    return records


def _run_summary(run_id: str, records: list[dict]) -> dict:
    strategies = sorted({r.get("strategy", "") for r in records})
    gate_counts: dict[str, int] = {}
    for r in records:
        g = r.get("gate_status", "fail")
        gate_counts[g] = gate_counts.get(g, 0) + 1
    return {
        "run_id": run_id,
        "record_count": len(records),
        "strategies": strategies,
        "gate_counts": gate_counts,
    }


def _record_metadata(record: dict) -> dict:
    """Strip large fields for list views."""
    return {k: v for k, v in record.items() if k not in ("tikz_code", "diagram_ir")}


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def list_runs(request: Request) -> JSONResponse:
    if not RESULTS_DIR.exists():
        return JSONResponse([])
    runs = []
    for path in sorted(RESULTS_DIR.glob("*.jsonl"), reverse=True):
        run_id = path.stem
        records = _load_run(run_id) or []
        runs.append(_run_summary(run_id, records))
    return JSONResponse(runs)


async def get_run(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    records = _load_run(run_id)
    if records is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return JSONResponse([_record_metadata(r) for r in records])


async def get_record(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    index = int(request.path_params["index"])
    records = _load_run(run_id)
    if records is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if index < 0 or index >= len(records):
        return JSONResponse({"error": "Record index out of range"}, status_code=404)
    return JSONResponse(records[index])


async def get_svg(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    index = int(request.path_params["index"])
    records = _load_run(run_id)
    if records is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    if index < 0 or index >= len(records):
        return JSONResponse({"error": "Record index out of range"}, status_code=404)
    svg_path = records[index].get("svg_path")
    if not svg_path:
        return JSONResponse({"error": "No SVG for this record"}, status_code=404)
    full_path = Path(svg_path)
    if not full_path.exists():
        return JSONResponse({"error": "SVG file not found on disk"}, status_code=404)
    svg_content = full_path.read_text()
    return Response(svg_content, media_type="image/svg+xml")


async def compile_ir(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    ir_data = body.get("diagram_ir")
    if ir_data is None:
        return JSONResponse({"error": "Missing diagram_ir field"}, status_code=400)

    # Validate IR
    try:
        diagram = DiagramIR.model_validate(ir_data)
    except ValidationError as e:
        return JSONResponse(
            {"error": str(e), "stage": "validate"},
            status_code=422,
        )

    # Compile to SymPy
    try:
        sym = compile_defs(diagram)
    except IRCompileError as e:
        return JSONResponse(
            {"error": str(e), "stage": "compile", "def_id": e.def_id},
            status_code=400,
        )

    # Run checks
    check_results = run_checks(diagram.checks, sym)

    # Generate TikZ and render to SVG
    try:
        render_result = TikZRenderer().render(diagram, sym)
    except Exception as e:
        return JSONResponse(
            {"error": str(e), "stage": "render"},
            status_code=400,
        )

    return JSONResponse({
        "tikz_code": render_result.intermediate,
        "svg": render_result.output,
        "checks": [r.model_dump(mode="json") for r in check_results],
    })


async def render_tikz_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    tikz_code = body.get("tikz_code")
    if not tikz_code:
        return JSONResponse({"error": "Missing tikz_code field"}, status_code=400)

    try:
        svg = render_tikz(tikz_code)
    except RuntimeError as e:
        return JSONResponse(
            {"error": str(e), "stage": "render"},
            status_code=400,
        )

    return JSONResponse({"svg": svg})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

routes = [
    Route("/api/runs", list_runs),
    Route("/api/runs/{run_id}", get_run),
    Route("/api/runs/{run_id}/records/{index:int}", get_record),
    Route("/api/runs/{run_id}/svg/{index:int}", get_svg),
    Route("/api/compile-ir", compile_ir, methods=["POST"]),
    Route("/api/render-tikz", render_tikz_endpoint, methods=["POST"]),
]

if os.path.isdir("eval-viewer-ui/dist"):
    routes.append(Mount("/", app=StaticFiles(directory="eval-viewer-ui/dist", html=True)))

app = Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run("evals.eval_viewer:app", host="0.0.0.0", port=8002, reload=True)
