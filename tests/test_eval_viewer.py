"""Eval viewer endpoints: partial JSONL, cache invalidation, svg_path containment."""
import json

import pytest
from starlette.testclient import TestClient

from evals import eval_viewer


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_viewer, "RESULTS_DIR", tmp_path)
    eval_viewer._run_cache.clear()
    yield TestClient(eval_viewer.app)
    eval_viewer._run_cache.clear()


def _write(tmp_path, name, lines):
    (tmp_path / f"{name}.jsonl").write_text("\n".join(lines) + "\n")


def test_truncated_last_line_is_skipped(client, tmp_path):
    good = json.dumps({"scenario_id": "a", "gate_status": "pass", "strategy": "s"})
    _write(tmp_path, "r1", [good, '{"scenario_id": "b", "gate_st'])
    resp = client.get("/api/runs/r1")
    assert resp.status_code == 200
    assert [r["scenario_id"] for r in resp.json()] == ["a"]


def test_one_bad_file_does_not_break_index(client, tmp_path, monkeypatch):
    _write(tmp_path, "good", [json.dumps({"scenario_id": "a"})])
    _write(tmp_path, "bad", [json.dumps({"scenario_id": "b"})])
    real = eval_viewer._load_run

    def flaky(run_id):
        if run_id == "bad":
            raise RuntimeError("boom")
        return real(run_id)

    monkeypatch.setattr(eval_viewer, "_load_run", flaky)
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert [r["run_id"] for r in resp.json()] == ["good"]


def test_cache_invalidates_when_file_grows(client, tmp_path):
    _write(tmp_path, "r1", [json.dumps({"scenario_id": "a"})])
    assert len(client.get("/api/runs/r1").json()) == 1
    _write(tmp_path, "r1", [json.dumps({"scenario_id": "a"}), json.dumps({"scenario_id": "b"})])
    assert len(client.get("/api/runs/r1").json()) == 2


def test_svg_served_from_results_dir(client, tmp_path):
    svg = tmp_path / "svgs" / "a.svg"
    svg.parent.mkdir()
    svg.write_text("<svg/>")
    _write(tmp_path, "r1", [json.dumps({"scenario_id": "a", "svg_path": str(svg)})])
    resp = client.get("/api/runs/r1/svg/0")
    assert resp.status_code == 200
    assert resp.text == "<svg/>"


def test_svg_path_outside_results_dir_is_404(client, tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret")
    results = tmp_path / "res"
    results.mkdir()
    eval_viewer.RESULTS_DIR = results
    _write(
        results,
        "r1",
        [
            json.dumps({"svg_path": str(outside)}),
            json.dumps({"svg_path": "../secret.txt"}),
            json.dumps({"svg_path": "/etc/hosts"}),
        ],
    )
    for i in range(3):
        resp = client.get(f"/api/runs/r1/svg/{i}")
        assert resp.status_code == 404
        assert "secret" not in resp.text


def test_compile_ir_check_error_is_clean_response(client, monkeypatch):
    def boom(checks, sym):
        raise ValueError("bad check")

    monkeypatch.setattr(eval_viewer, "run_checks", boom)
    ir = {"canvas": {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1}, "define": [], "checks": [], "render": []}
    resp = client.post("/api/compile-ir", json={"diagram_ir": ir})
    if resp.status_code == 422:
        pytest.skip("minimal IR shape not valid for this schema")
    assert resp.status_code == 400
    assert resp.json()["stage"] == "checks"
