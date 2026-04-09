"""Inter-rater reliability (IRR) computation for benchmark annotations.

Computes Cohen's kappa between two annotators for a benchmark run.
"""
from __future__ import annotations
from pathlib import Path

from benchmark.db import get_db, list_results_for_run, get_annotations_for_result, get_run
from benchmark.models import load_definition

_BENCHMARK_ROOT = Path(__file__).parent
_DB_PATH = _BENCHMARK_ROOT / "data" / "benchmark.db"
_DEFINITIONS_DIR = _BENCHMARK_ROOT / "definitions"


def cohens_kappa(rater1: list[int], rater2: list[int]) -> float:
    n = len(rater1)
    if n == 0:
        return 0.0
    agree = sum(a == b for a, b in zip(rater1, rater2))
    p_o = agree / n
    p1_yes, p2_yes = sum(rater1) / n, sum(rater2) / n
    p_e = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def percent_agreement(rater1: list[int], rater2: list[int]) -> float:
    if not rater1:
        return 0.0
    return sum(a == b for a, b in zip(rater1, rater2)) / len(rater1)


def compute_irr(
    run_id: str,
    annotator1: str | None = None,
    annotator2: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """Compute IRR between two annotators for a benchmark run.

    Returns a dict with kappa, percent_agreement, by_category, and by_item
    breakdowns. If annotator1/annotator2 are not provided, defaults to the
    first human: and ai: annotators found in the data.
    """
    conn = get_db(db_path or _DB_PATH)

    run = get_run(conn, run_id)
    if run is None:
        return {"run_id": run_id, "error": "run_not_found", "kappa": None}

    benchmark_id = run["benchmark_id"]
    def_path = _DEFINITIONS_DIR / f"{benchmark_id}.yaml"
    definition = load_definition(def_path)

    # Build a map from rubric_item_id -> category from the full definition
    item_category: dict[str, str] = {}
    for prompt in definition.prompts:
        for item in definition.effective_rubric(prompt.id):
            item_category[item.id] = item.category

    results = list_results_for_run(conn, run_id)

    # Collect all annotations: {(result_id, rubric_item_id): {annotator_id: value}}
    all_annotations: dict[tuple[str, str], dict[str, int]] = {}
    all_annotator_ids: set[str] = set()

    for result in results:
        result_id = result["result_id"]
        annotations = get_annotations_for_result(conn, result_id)
        for ann in annotations:
            key = (result_id, ann["rubric_item_id"])
            if key not in all_annotations:
                all_annotations[key] = {}
            all_annotations[key][ann["annotator_id"]] = ann["value"]
            all_annotator_ids.add(ann["annotator_id"])

    # Determine annotator pair
    if annotator1 is None or annotator2 is None:
        human_annotators = sorted(a for a in all_annotator_ids if a.startswith("human:"))
        ai_annotators = sorted(a for a in all_annotator_ids if a.startswith("ai:"))
        if not human_annotators or not ai_annotators:
            return {"run_id": run_id, "error": "not_enough_annotators", "kappa": None}
        annotator1 = human_annotators[0]
        annotator2 = ai_annotators[0]

    # Build paired vectors
    r1_all: list[int] = []
    r2_all: list[int] = []
    by_item_data: dict[str, dict] = {}

    for (result_id, rubric_item_id), rater_map in all_annotations.items():
        if annotator1 not in rater_map or annotator2 not in rater_map:
            continue
        v1 = rater_map[annotator1]
        v2 = rater_map[annotator2]
        r1_all.append(v1)
        r2_all.append(v2)

        if rubric_item_id not in by_item_data:
            by_item_data[rubric_item_id] = {"r1": [], "r2": []}
        by_item_data[rubric_item_id]["r1"].append(v1)
        by_item_data[rubric_item_id]["r2"].append(v2)

    if len(r1_all) < 2:
        return {"run_id": run_id, "error": "not_enough_data", "kappa": None}

    # by_category
    category_data: dict[str, dict] = {}
    for rubric_item_id, vectors in by_item_data.items():
        cat = item_category.get(rubric_item_id, "custom")
        if cat not in category_data:
            category_data[cat] = {"r1": [], "r2": []}
        category_data[cat]["r1"].extend(vectors["r1"])
        category_data[cat]["r2"].extend(vectors["r2"])

    by_category = {}
    for cat, vectors in category_data.items():
        r1, r2 = vectors["r1"], vectors["r2"]
        by_category[cat] = {
            "n_pairs": len(r1),
            "kappa": cohens_kappa(r1, r2),
            "percent_agreement": percent_agreement(r1, r2),
        }

    # by_item
    by_item = []
    for rubric_item_id, vectors in by_item_data.items():
        r1, r2 = vectors["r1"], vectors["r2"]
        n = len(r1)
        agree = sum(a == b for a, b in zip(r1, r2))
        by_item.append({
            "rubric_item_id": rubric_item_id,
            "category": item_category.get(rubric_item_id, "custom"),
            "n_pairs": n,
            "agreement": agree / n if n > 0 else 0.0,
            "annotator1_yes_rate": sum(r1) / n if n > 0 else 0.0,
            "annotator2_yes_rate": sum(r2) / n if n > 0 else 0.0,
        })

    return {
        "run_id": run_id,
        "annotator1": annotator1,
        "annotator2": annotator2,
        "n_pairs": len(r1_all),
        "kappa": cohens_kappa(r1_all, r2_all),
        "percent_agreement": percent_agreement(r1_all, r2_all),
        "by_category": by_category,
        "by_item": by_item,
    }
