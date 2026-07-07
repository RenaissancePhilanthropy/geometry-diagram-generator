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

# Confidence-elicitation queries for the 3-turn temporal capture — QA-worded.
# (The geometry PRETASK_QUERY/CONFIDENCE_QUERY in interp/confidence.py ask about a
# "construction" being "geometrically correct/valid", which is nonsensical on QA and
# was leaking into the QA confidence turns.) capture_qa.py uses these; a task may
# override either via a "pretask_query"/"posttask_query" field.
QA_PRETASK_QUERY = (
    "Before answering, estimate how likely you are to answer this question "
    "correctly. Reply with EXACTLY one line and nothing else:\n"
    "Confidence: N\n"
    "where N is an integer from 0 (certain to be wrong) to 100 (certain to be "
    "correct). Do NOT answer yet."
)
QA_POSTTASK_QUERY = (
    "Now assess the answer you just gave. On a scale of 0 to 100, how confident "
    "are you that it is correct? Reply with exactly one line and nothing else:\n"
    "Confidence: N"
)


def _mmlu_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("cais/mmlu", "all", split="test")
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    return [{"id": f"mmlu_{i}", "question": ds[i]["question"],
             "options": list(ds[i]["choices"]), "answer": _LETTERS[int(ds[i]["answer"])]}
            for i in idx[:n]]


def _mmlupro_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("TIGER-Lab/MMLU-Pro", split="test")   # 10-option, harder -> real failure spread
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    return [{"id": f"mmlupro_{ds[i]['question_id']}", "question": ds[i]["question"],
             "options": list(ds[i]["options"]), "answer": ds[i]["answer"]}
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


def _last_boxed(s):
    r"""Content of the last \boxed{...} in s (brace-matched), or None."""
    s = s or ""
    i = s.rfind("\\boxed")
    if i < 0:
        return None
    j = s.find("{", i)
    if j < 0:
        return None
    depth = 0
    for k in range(j, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                return s[j + 1:k]
    return None


def _math_norm(x):
    if x is None:
        return None
    x = x.strip().strip("$").replace(" ", "")
    for a, b in (("\\left", ""), ("\\right", ""), ("\\!", ""), ("\\,", ""),
                 ("\\dfrac", "\\frac"), ("\\tfrac", "\\frac"), ("^{\\circ}", ""), ("^\\circ", "")):
        x = x.replace(a, b)
    return x.rstrip(".").strip("{}")


def _math_load(n, seed):
    from datasets import load_dataset
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")   # hendrycks/competition_math was removed
    idx = list(range(len(ds)))
    random.Random(seed).shuffle(idx)
    return [{"id": "math_" + str(ds[i].get("unique_id", i)).replace("/", "_"),
             "question": ds[i]["problem"], "answer": ds[i]["answer"]}
            for i in idx[:n]]


def _math_extract(completion, item):
    return _last_boxed(completion) or _num(completion)


def _clean_latex(s):
    r"""Strip formatting the parser trips on: money \$, \!, brace-less \frac 34."""
    s = (s or "").replace(r"\$", "").replace("$", "").replace(r"\!", "")
    return re.sub(r"\\d?frac\s+(\d)\s*(\d)\b", r"\\frac{\1}{\2}", s)  # \frac 34 -> \frac{3}{4}


def _math_eq(pred, gold):
    r"""Symbolic/numeric equivalence via math_verify, with a whitespace-insensitive
    string fallback (matrices etc.). math_verify is imported lazily so the grader
    degrades to string-only on boxes without it — the offline re-grade
    (interp/analysis/regrade_math.py, run in a venv that HAS math_verify) is the
    source of truth for the reported labels."""
    if pred is None or gold is None:
        return False
    try:
        from math_verify import parse, verify
        if bool(verify(parse(_clean_latex(gold)), parse(_clean_latex(pred)))):
            return True
    except Exception:
        pass
    return _math_norm(_clean_latex(pred)) == _math_norm(_clean_latex(gold))


def _math_grade(completion, item):
    return _math_eq(_math_extract(completion, item), item["answer"])


def _mc_task(loader):
    ex = lambda c, it: _pick_letter(c, len(it["options"]))
    return {"load": loader, "system": lambda: MC_SYSTEM, "is_mc": True,
            "prompt": lambda it: _mc_body(it["question"], it["options"]),
            "answer_query": MC_ANSWER_QUERY,
            "extract": ex, "grade": lambda c, it: ex(c, it) == it["answer"]}


QA_TASKS = {
    "mmlu": _mc_task(_mmlu_load),
    "mmlu_pro": _mc_task(_mmlupro_load),
    "medqa": _mc_task(_medqa_load),
    "gsm8k": {"load": _gsm8k_load, "is_mc": False,
              "system": lambda: "Solve the math word problem. End with 'Answer: <number>'.",
              "prompt": lambda it: it["question"],
              "answer_query": "Now give your final numeric answer in the form 'Answer: <number>'.",
              "extract": lambda c, it: _num(c), "grade": _gsm8k_grade},
    "math": {"load": _math_load, "is_mc": False,
             "system": lambda: "Solve the problem step by step. Put your final answer in \\boxed{}.",
             "prompt": lambda it: it["question"],
             "answer_query": "Now give your final answer inside \\boxed{}.",
             "extract": _math_extract, "grade": _math_grade},
}
