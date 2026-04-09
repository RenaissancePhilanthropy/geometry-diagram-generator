"""
Benchmark Annotation Server — serves annotation UI and API on port 8004.

  GET  /api/benchmarks                              — list benchmark definitions
  GET  /api/runs                                    — list runs with annotation progress
  GET  /api/runs/{run_id}/queue                     — annotation queue for a run
  GET  /api/runs/{run_id}/results/{prompt_id}       — full result detail with rubric
  GET  /api/runs/{run_id}/results/{prompt_id}/svg   — serve generated SVG
  GET  /api/references/{benchmark_id}/{prompt_id}   — serve reference SVG
  POST /api/annotate                                — save a single annotation
  GET  /api/irr/{run_id}                            — IRR stub
"""

import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path when the script is run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from benchmark.db import (
    get_db,
    get_annotations_for_result,
    get_run,
    get_result,
    list_runs as db_list_runs,
    list_results_for_run,
    upsert_annotation,
)
from benchmark.models import load_definition

_BENCHMARK_ROOT = Path(__file__).parent
_DEFINITIONS_DIR = _BENCHMARK_ROOT / "definitions"
_REFERENCES_DIR = _BENCHMARK_ROOT / "references"
_DATA_DIR = _BENCHMARK_ROOT / "data"
_DB_PATH = _DATA_DIR / "benchmark.db"


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def list_benchmarks(request: Request) -> JSONResponse:
    if not _DEFINITIONS_DIR.exists():
        return JSONResponse([])
    benchmarks = []
    for path in sorted(_DEFINITIONS_DIR.glob("*.yaml")):
        try:
            defn = load_definition(path)
            benchmarks.append({"id": defn.id, "prompt_count": len(defn.prompts)})
        except Exception:
            pass
    return JSONResponse(benchmarks)


async def list_runs(request: Request) -> JSONResponse:
    conn = get_db(_DB_PATH)
    runs = db_list_runs(conn)
    result = []
    for run in runs:
        run_id = run["run_id"]
        results = list_results_for_run(conn, run_id)
        result_count = len(results)
        annotated_count = 0
        for r in results:
            annotations = get_annotations_for_result(conn, r["result_id"])
            if annotations:
                annotated_count += 1
        result.append({
            "run_id": run_id,
            "benchmark_id": run["benchmark_id"],
            "label": run["label"],
            "created_at": run["created_at"],
            "result_count": result_count,
            "annotated_count": annotated_count,
        })
    return JSONResponse(result)


async def get_queue(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    conn = get_db(_DB_PATH)
    run = get_run(conn, run_id)
    if run is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)
    results = list_results_for_run(conn, run_id)
    queue = []
    for r in results:
        annotations = get_annotations_for_result(conn, r["result_id"])
        queue.append({
            "result_id": r["result_id"],
            "prompt_id": r["prompt_id"],
            "generation_success": bool(r["generation_success"]),
            "annotated": len(annotations) > 0,
        })
    return JSONResponse(queue)


async def get_result_detail(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    prompt_id = request.path_params["prompt_id"]
    conn = get_db(_DB_PATH)

    run = get_run(conn, run_id)
    if run is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    result_id = f"{run_id}__{prompt_id}"
    result = get_result(conn, result_id)
    if result is None:
        return JSONResponse({"error": "Result not found"}, status_code=404)

    benchmark_id = run["benchmark_id"]
    def_path = _DEFINITIONS_DIR / f"{benchmark_id}.yaml"
    if not def_path.exists():
        return JSONResponse({"error": f"Benchmark definition not found: {benchmark_id}"}, status_code=404)

    defn = load_definition(def_path)

    prompt_obj = next((p for p in defn.prompts if p.id == prompt_id), None)
    if prompt_obj is None:
        return JSONResponse({"error": f"Prompt not found: {prompt_id}"}, status_code=404)

    rubric = defn.effective_rubric(prompt_id)
    annotations = get_annotations_for_result(conn, result_id)

    return JSONResponse({
        "result_id": result_id,
        "prompt_id": prompt_id,
        "prompt_text": prompt_obj.prompt,
        "generation_success": bool(result["generation_success"]),
        "svg_path": result.get("svg_path"),
        "metadata": result.get("metadata"),
        "rubric": [{"id": item.id, "text": item.text, "category": item.category} for item in rubric],
        "annotations": [
            {
                "rubric_item_id": a["rubric_item_id"],
                "annotator_id": a["annotator_id"],
                "annotator_type": a["annotator_type"],
                "value": a["value"],
            }
            for a in annotations
        ],
    })


async def get_result_svg(request: Request) -> Response:
    run_id = request.path_params["run_id"]
    prompt_id = request.path_params["prompt_id"]
    conn = get_db(_DB_PATH)

    result_id = f"{run_id}__{prompt_id}"
    result = get_result(conn, result_id)
    if result is None:
        return JSONResponse({"error": "Result not found"}, status_code=404)

    svg_path = result.get("svg_path")
    if not svg_path:
        return JSONResponse({"error": "No SVG for this result"}, status_code=404)

    full_path = Path(svg_path)
    if not full_path.exists():
        return JSONResponse({"error": "SVG file not found on disk"}, status_code=404)

    svg_content = full_path.read_text()
    return Response(svg_content, media_type="image/svg+xml")


async def get_reference_svg(request: Request) -> Response:
    benchmark_id = request.path_params["benchmark_id"]
    prompt_id = request.path_params["prompt_id"]

    def_path = _DEFINITIONS_DIR / f"{benchmark_id}.yaml"
    if not def_path.exists():
        return JSONResponse({"error": f"Benchmark definition not found: {benchmark_id}"}, status_code=404)

    defn = load_definition(def_path)

    prompt_obj = next((p for p in defn.prompts if p.id == prompt_id), None)
    if prompt_obj is None:
        return JSONResponse({"error": f"Prompt not found: {prompt_id}"}, status_code=404)

    if not prompt_obj.reference_svg:
        return JSONResponse({"error": "No reference SVG for this prompt"}, status_code=404)

    ref_path = _REFERENCES_DIR / prompt_obj.reference_svg
    if not ref_path.exists():
        return JSONResponse({"error": "Reference SVG file not found on disk"}, status_code=404)

    svg_content = ref_path.read_text()
    return Response(svg_content, media_type="image/svg+xml")


async def annotate(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    result_id = body.get("result_id")
    rubric_item_id = body.get("rubric_item_id")
    annotator_id = body.get("annotator_id")
    value = body.get("value")

    if result_id is None or rubric_item_id is None or annotator_id is None or value is None:
        return JSONResponse({"error": "Missing required fields"}, status_code=400)

    if value not in (0, 1):
        return JSONResponse({"error": "value must be 0 or 1"}, status_code=400)

    conn = get_db(_DB_PATH)

    result = get_result(conn, result_id)
    if result is None:
        return JSONResponse({"error": "Result not found"}, status_code=404)

    run_id = result["run_id"]
    prompt_id = result["prompt_id"]

    run = get_run(conn, run_id)
    if run is None:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    benchmark_id = run["benchmark_id"]
    def_path = _DEFINITIONS_DIR / f"{benchmark_id}.yaml"
    if not def_path.exists():
        return JSONResponse({"error": "Benchmark definition not found"}, status_code=500)

    defn = load_definition(def_path)
    rubric = defn.effective_rubric(prompt_id)
    valid_ids = {item.id for item in rubric}

    if rubric_item_id not in valid_ids:
        return JSONResponse({"error": f"rubric_item_id not in effective rubric: {rubric_item_id!r}"}, status_code=400)

    annotator_type = "human" if str(annotator_id).startswith("human:") else "ai"

    upsert_annotation(conn, result_id, rubric_item_id, annotator_id, annotator_type, value)

    return JSONResponse({"status": "ok"})


async def get_irr(request: Request) -> JSONResponse:
    run_id = request.path_params["run_id"]
    annotator1 = request.query_params.get("annotator1")
    annotator2 = request.query_params.get("annotator2")
    from benchmark.irr import compute_irr
    report = compute_irr(run_id, annotator1, annotator2, _DB_PATH)
    return JSONResponse(report)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

routes = [
    Route("/api/benchmarks", list_benchmarks),
    Route("/api/runs", list_runs),
    Route("/api/runs/{run_id}/queue", get_queue),
    Route("/api/runs/{run_id}/results/{prompt_id}/svg", get_result_svg),
    Route("/api/runs/{run_id}/results/{prompt_id}", get_result_detail),
    Route("/api/references/{benchmark_id}/{prompt_id}", get_reference_svg),
    Route("/api/annotate", annotate, methods=["POST"]),
    Route("/api/irr/{run_id}", get_irr),
]

_UI_DIST = _BENCHMARK_ROOT.parent / "benchmark-ui" / "dist"
if _UI_DIST.is_dir():
    routes.append(Mount("/", app=StaticFiles(directory=str(_UI_DIST), html=True)))

app = Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run("benchmark.server:app", host="0.0.0.0", port=8004, reload=True)
