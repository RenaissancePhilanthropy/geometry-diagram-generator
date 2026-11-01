"""Eval runner failure stubs and JSONL writing never lose a record."""
import json
from datetime import datetime
from pathlib import Path

from evals.reporting import _append_jsonl
from evals.run import _runner_exception_stub


def test_runner_exception_stub_keeps_identity():
    stub = _runner_exception_stub(
        {"id": "s1", "prompt": "draw"}, "recipe", "m", 3, ValueError("boom")
    )
    assert stub["scenario_id"] == "s1"
    assert stub["repeat_index"] == 3
    assert stub["user_prompt"] == "draw"
    assert stub["gate_failures"] == ["runner_exception"]
    assert stub["gate_status"] == "fail"
    assert "ValueError: boom" in stub["error"]


def test_append_jsonl_serializes_unknown_types(tmp_path: Path):
    path = tmp_path / "out.jsonl"
    _append_jsonl(path, {"scenario_id": "a", "when": datetime(2026, 1, 1)})
    rec = json.loads(path.read_text())
    assert rec["scenario_id"] == "a"
    assert "2026" in rec["when"]


def test_append_jsonl_falls_back_to_stub(tmp_path: Path):
    path = tmp_path / "out.jsonl"
    circular: dict = {}
    circular["self"] = circular
    _append_jsonl(path, {"scenario_id": "a", "repeat_index": 2, "x": circular})
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["scenario_id"] == "a"
    assert rec["repeat_index"] == 2
    assert rec["gate_failures"] == ["unserializable_record"]
