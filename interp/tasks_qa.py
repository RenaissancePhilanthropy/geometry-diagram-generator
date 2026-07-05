"""
QA task adapters for the 3-turn confidence capture (interp/capture_qa.py).

Each task is a dict of callables sharing one interface, so the SAME 3-turn
confidence capture + residual-stream reads + analysis (confidence_temporal.py)
apply to every benchmark — only load/prompt/grade change:

  load(n, seed) -> [item dict]        pull + subsample the benchmark
  system()      -> str | None         task system prompt
  prompt(item)  -> str                the user message posing the question
  answer_query  -> str                turn-2 instruction ("give your final answer")
  grade(completion, item) -> bool     correct?

The output meta.jsonl / npz format is identical to the geometry capture, so the
calibration / self-correction / internal-probe / pre-post-layer analyses are reused.

Registry: QA_TASKS. Datasets are ungated and pulled via `datasets` on the GPU box.
"""
from __future__ import annotations

import random
import re

_LETTERS = "ABCDEFGHIJ"


def _mc_body(question: str, options: list[str]) -> str:
    return question.strip() + "\n\n" + "\n".join(
        f"{_LETTERS[i]}. {o}" for i, o in enumerate(options))


def _pick_letter(completion: str, n: int):
    """Last answer letter in A..n, preferring an explicit 'Answer: X' pattern."""
    up = (completion or "").upper()
    valid = _LETTERS[:n]
    m = re.findall(rf"ANSWER\s*(?:IS)?\s*[:=]?\s*\(?([{valid}])\b", up)
    if m:
        return m[-1]
    m = re.findall(rf"\b([{valid}])\b", up)
    return m[-1] if m else None


def _num(s: str):
    m = re.findall(r"-?\$?\d[\d,]*\.?\d*", s or "")
    return m[-1].replace(",", "").replace("$", "") if m else None


MC_SYSTEM = ("You answer multiple-choice questions. Reason briefly if needed, then end with "
             "your final answer on its own line as:  Answer: X   (a single letter).")
MC_ANSWER_QUERY = "Now give your final answer as a single letter in the form 'Answer: X'."


def _mmlu_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("cais/mmlu", "all", split="test")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    return [{"id": f"mmlu_{i}", "question": ds[i]["question"],
             "options": list(ds[i]["choices"]), "answer": _LETTERS[int(ds[i]["answer"])]}
            for i in idx[:n]]


def _medqa_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("GBaker/MedQA-USMLE-4-options", split="test")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    out = []
    for i in idx[:n]:
        r = ds[i]
        opts = r["options"]
        if isinstance(opts, dict):
            options = [opts[k] for k in sorted(opts)]
        else:
            options = list(opts)
        ans = str(r.get("answer_idx") or r.get("answer") or "").strip()
        if ans not in _LETTERS:                      # gold given as full text -> map to letter
            ans = _LETTERS[options.index(ans)] if ans in options else (ans[:1].upper() or "?")
        out.append({"id": f"medqa_{i}", "question": r["question"], "options": options, "answer": ans})
    return out


def _gsm8k_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("openai/gsm8k", "main", split="test")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    return [{"id": f"gsm8k_{i}", "question": ds[i]["question"],
             "answer": _num(ds[i]["answer"].split("####")[-1])} for i in idx[:n]]


def _gsm8k_grade(completion, item):
    pred = _num(completion)
    if pred is None or item["answer"] is None:
        return False
    try:
        return abs(float(pred) - float(item["answer"])) < 1e-4
    except ValueError:
        return pred == item["answer"]


def _mc_task(loader):
    return {"load": loader, "system": lambda: MC_SYSTEM,
            "prompt": lambda it: _mc_body(it["question"], it["options"]),
            "answer_query": MC_ANSWER_QUERY,
            "grade": lambda c, it: _pick_letter(c, len(it["options"])) == it["answer"]}


QA_TASKS = {
    "mmlu": _mc_task(_mmlu_load),
    "medqa": _mc_task(_medqa_load),
    "gsm8k": {"load": _gsm8k_load,
              "system": lambda: "Solve the math word problem. End with 'Answer: <number>'.",
              "prompt": lambda it: it["question"],
              "answer_query": "Now give your final numeric answer in the form 'Answer: <number>'.",
              "grade": _gsm8k_grade},
}
