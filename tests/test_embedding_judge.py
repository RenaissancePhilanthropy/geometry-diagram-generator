"""Tests for the embedding judge (util/embeddings.py + evals/embedding_judge.py).

Pure-logic tests for cosine, renderers, verbatim model bucketing, and
aggregation; mocked-endpoint tests for the EmbeddingClient cache/batching; and
an end-to-end test on a tiny tmp JSONL with a fake embeddings client. No live
endpoint is hit (the LAN endpoint is unreachable from the sandbox).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path

import pytest

from evals import embedding_judge as ej
from util.embeddings import (
    DEFAULT_MAX_CHARS,
    EmbeddingClient,
    chunk_text,
    cosine,
    pool,
    text_hash,
)


# ---------------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------------

def test_cosine_basic():
    assert cosine([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)
    assert cosine([1, 2, 2], [1, 2, 2]) == pytest.approx(1.0)
    # anti-parallel -> -1
    assert cosine([1, 1], [-1, -1]) == pytest.approx(-1.0)


def test_cosine_edge_cases():
    assert cosine([0, 0], [1, 1]) == 0.0          # zero norm
    assert cosine([], [1]) == 0.0                 # empty
    assert cosine([1, 2], [1, 2, 3]) == 0.0      # mismatched length
    assert cosine([1, 0], [1, 0, 0]) == 0.0       # mismatched length


# ---------------------------------------------------------------------------
# renderers
# ---------------------------------------------------------------------------

def test_render_flat_dsl_drops_noise_and_compacts():
    dsl = {
        "mode": "abstract",
        "construction": [
            {"op": "point", "id": "A", "visible": True, "coords": [0.0, 0.0]},
            {"op": "triangle", "id": "T", "visible": True, "vertices": ["A", "B", "C"], "spec": {"side_AB": 4.0}},
        ],
    }
    out = ej.render_flat_dsl(dsl)
    assert out is not None
    assert "point A coords=0,0" in out
    assert "triangle T vertices=A,B,C" in out
    assert "visible" not in out          # noise key dropped
    assert "spec=" in out                 # semantic key kept


def test_render_flat_dsl_none_and_fallback():
    assert ej.render_flat_dsl(None) is None
    assert ej.render_flat_dsl({}) is None
    # dict without construction -> whole-json fallback
    assert ej.render_flat_dsl({"mode": "grid"}) == json.dumps({"mode": "grid"}, sort_keys=True)


def test_render_raw_dsl():
    assert ej.render_raw_dsl(None) is None
    out = ej.render_raw_dsl({"mode": "grid", "construction": []})
    assert json.loads(out) == {"mode": "grid", "construction": []}


def test_render_nl_ir_curated_and_fallback():
    ir = {
        "canvas": {"kind": "cartesian"},
        "define": [
            {"kind": "point_fixed", "id": "A", "x": 0.0, "y": 0.0},
            {"kind": "triangle", "id": "T", "a": "A", "b": "B", "c": "C"},
            {"kind": "segment", "id": "s", "a": "A", "b": "B"},
            {"kind": "weird_kind", "id": "W", "foo": "bar"},
        ],
    }
    out = ej.render_nl_ir(ir)
    assert out is not None
    assert "point A at (0.0,0.0)" in out
    assert "triangle ABC" in out
    assert "segment AB" in out
    assert "canvas cartesian" in out
    assert "weird_kind W(foo=bar)" in out   # generic fallback


def test_render_nl_ir_none():
    assert ej.render_nl_ir(None) is None
    assert ej.render_nl_ir({"define": []}) is None  # nothing to describe


def test_render_tikz_and_prompt():
    rec = {"tikz_code": "", "user_prompt": "Draw ABC."}
    assert ej.render_tikz(rec) is None
    assert ej.render_prompt(rec) == "Draw ABC."
    rec2 = {"tikz_code": "\\draw (0,0) -- (1,1);", "user_prompt": None}
    assert ej.render_tikz(rec2) == "\\draw (0,0) -- (1,1);"
    assert ej.render_prompt(rec2) is None


# ---------------------------------------------------------------------------
# verbatim model bucketing (no normalization)
# ---------------------------------------------------------------------------

def _run(model, scenario, cos_flat, gate="pass", gen=True, null_reps=("tikz",)):
    d = {
        "model": model,
        "scenario_id": scenario,
        "repeat_index": 1,
        "gate_status": gate,
        "generation_success": gen,
        "reprs": {},
    }
    for r in ej.REPRS:
        val = None if r in null_reps else cos_flat
        for a in ej.AGGS:
            d[f"cos_{r}_{a}"] = val
    for a in ej.AGGS:
        d[f"cos_combined_{a}"] = cos_flat
    return d


def test_aggregate_keeps_botched_model_names_distinct():
    runs = [
        _run("ollama:nemotron-3-ultra:cloud", "s1", 0.9, gate="pass"),
        _run("ollam:nemotron-3-ultra:cloud", "s1", 0.1, gate="fail"),   # botched typo
        _run("ollam:nemotron-3-ultra:cloud", "s1", 0.2, gate="fail"),   # botched, 2nd repeat
    ]
    rows = ej._aggregate(runs, ej.REPRS)
    models = {r["model"] for r in rows}
    # The botched name is NOT folded into the real one — two distinct buckets.
    assert "ollama:nemotron-3-ultra:cloud" in models
    assert "ollam:nemotron-3-ultra:cloud" in models
    assert len(rows) == 2
    botched = next(r for r in rows if r["model"].startswith("ollam:"))
    assert botched["n_runs"] == 2
    assert botched["gate_pass_rate"] == 0.0
    real = next(r for r in rows if r["model"] == "ollama:nemotron-3-ultra:cloud")
    assert real["n_runs"] == 1
    assert real["gate_pass_rate"] == 1.0


def test_aggregate_stats_mean_std_n():
    runs = [_run("m", "s", v) for v in (0.9, 0.7, 0.8)]
    rows = ej._aggregate(runs, ej.REPRS)
    assert len(rows) == 1
    r = rows[0]
    # combined_<agg> carries mean/std/n (per-rep only carries mean)
    assert r["cos_combined_max_n"] == 3
    assert r["cos_combined_max_mean"] == pytest.approx(0.8)
    assert r["cos_combined_max_std"] == pytest.approx(0.0816496, rel=1e-4)  # pstdev
    assert r["cos_flat_dsl_max_mean"] == pytest.approx(0.8)


def test_aggregate_ignores_nulls():
    runs = [
        _run("m", "s", 0.8, null_reps=("tikz", "nl_ir")),
        _run("m", "s", 0.6, null_reps=("tikz", "nl_ir")),
    ]
    rows = ej._aggregate(runs, ej.REPRS)
    r = rows[0]
    assert r["cos_tikz_max_mean"] is None              # tikz null
    assert r["cos_nl_ir_max_mean"] is None             # nl_ir null
    assert r["cos_flat_dsl_max_mean"] == pytest.approx(0.7)  # mean(0.8, 0.6)


# ---------------------------------------------------------------------------
# EmbeddingClient: batching + cache (mocked endpoint)
# ---------------------------------------------------------------------------

def _det_vec(text: str, dim: int = 4) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    return [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(dim)]


def _patch_embed_batch(client, capture):
    async def fake_batch(batch):
        capture.append(list(batch))
        return [_det_vec(t) for t in batch]

    client._embed_batch = fake_batch  # type: ignore[method-assign]


def test_embedding_client_cache_hit_skips_endpoint(tmp_path):
    client = EmbeddingClient(
        base_url="http://x", model="m", cache_path=str(tmp_path / "c.sqlite")
    )
    captured: list[list[str]] = []
    _patch_embed_batch(client, captured)

    v1 = asyncio.run(client.embed_texts(["a", "b"]))
    assert captured == [["a", "b"]]
    assert len(v1) == 2

    # second call: "a" is cached, only "c" hits the endpoint
    v2 = asyncio.run(client.embed_texts(["a", "c"]))
    assert captured == [["a", "b"], ["c"]]
    assert v2[0] == _det_vec("a")  # served from cache
    assert v2[1] == _det_vec("c")


def test_embedding_client_dedupes_and_preserves_order(tmp_path):
    client = EmbeddingClient(
        base_url="http://x", model="m", cache_path=str(tmp_path / "c.sqlite")
    )
    captured: list[list[str]] = []
    _patch_embed_batch(client, captured)

    out = asyncio.run(client.embed_texts(["x", "y", "x", "z"]))
    assert captured == [["x", "y", "z"]]      # deduped before batching
    assert len(out) == 4
    assert out[0] == out[2]                    # both "x" -> identical vector


def test_embedding_client_batches_by_batch_size(tmp_path):
    client = EmbeddingClient(
        base_url="http://x", model="m", batch_size=2, cache_path=str(tmp_path / "c.sqlite")
    )
    captured: list[list[str]] = []
    _patch_embed_batch(client, captured)

    out = asyncio.run(client.embed_texts(["a", "b", "c", "d", "e"]))
    assert sorted(captured, key=lambda b: b[0]) == [["a", "b"], ["c", "d"], ["e"]]
    assert len(out) == 5


# ---------------------------------------------------------------------------
# end-to-end on a tiny tmp JSONL with a fake client
# ---------------------------------------------------------------------------

class _FakeClient:
    def __init__(self):
        self.calls = 0

    async def embed_texts(self, texts, on_progress=None):
        self.calls += 1
        out = [_det_vec(t, dim=8) for t in texts]
        if on_progress:
            on_progress(len(texts), len(texts))
        return out


def _make_record(model="ollama:gemma4:31b-cloud", scenario="s1", with_cot=True, gate="pass"):
    dsl = {"mode": "abstract", "construction": [{"op": "triangle", "id": "T", "visible": True, "vertices": ["A", "B", "C"]}]}
    diagram_ir = {
        "canvas": {"kind": "cartesian"},
        "define": [
            {"kind": "point_fixed", "id": "A", "x": 0.0, "y": 0.0},
            {"kind": "triangle", "id": "T", "a": "A", "b": "B", "c": "C"},
        ],
    }
    attempt = {"attempt": 1, "stage": "success", "dsl_json": dsl, "error": None}
    rm = {"attempt_traces": [attempt]}
    cot = "I will construct triangle ABC with vertices A, B, C."
    if with_cot:
        attempt["cot"] = cot
        rm["cot"] = cot
    return {
        "run_id": "r1",
        "model": model,
        "scenario_id": scenario,
        "tier": 1,
        "repeat_index": 1,
        "strategy": "recipe",
        "gate_status": gate,
        "generation_success": True,
        "svg_rendered": True,
        "user_prompt": "Draw triangle ABC.",
        "tikz_code": "",
        "recipe_metadata": rm,
        "diagram_ir": diagram_ir,
    }


def test_end_to_end_drops_no_cot_and_scores_rest(tmp_path):
    jsonl = tmp_path / "in.jsonl"
    rec_keep = _make_record()                                  # has CoT
    rec_drop = _make_record(model="ollama:other:cloud", with_cot=False)  # no CoT
    jsonl.write_text(json.dumps(rec_keep) + "\n" + json.dumps(rec_drop) + "\n")

    out_dir = tmp_path / "out"
    fake = _FakeClient()
    summary = asyncio.run(
        ej.run(
            [str(jsonl)],
            str(out_dir),
            embedding_model="embeddinggemma",
            embedding_base_url="http://x",
            client=fake,
        )
    )
    assert summary["runs"] == 1                 # only the CoT-bearing run kept

    runs = [json.loads(l) for l in (out_dir / "runs.jsonl").read_text().splitlines()]
    assert len(runs) == 1
    r = runs[0]
    assert r["model"] == "ollama:gemma4:31b-cloud"
    assert r["cot_chunks"] >= 1
    for a in ej.AGGS:
        assert r[f"cos_flat_dsl_{a}"] is not None
        assert r[f"cos_raw_dsl_{a}"] is not None
        assert r[f"cos_nl_ir_{a}"] is not None
        assert r[f"cos_tikz_{a}"] is None          # tikz_code empty -> 0 chunks -> None
        assert r[f"cos_combined_{a}"] is not None
        for rep in ("flat_dsl", "raw_dsl", "nl_ir"):
            assert -1.0 <= r[f"cos_{rep}_{a}"] <= 1.0

    matrix = (out_dir / "matrix.csv").read_text().splitlines()
    assert len(matrix) == 2                     # header + 1 cell
    assert "ollama:gemma4:31b-cloud" in matrix[1]
    assert "cos_combined_max_mean" in matrix[0]

    cov = (out_dir / "coverage.txt").read_text()
    assert "kept" in cov


def test_expand_paths_directory_glob(tmp_path):
    (tmp_path / "a.jsonl").write_text("{}\n")
    (tmp_path / "b.jsonl").write_text("{}\n")
    (tmp_path / "ignore.txt").write_text("x")
    files = ej._expand_paths([str(tmp_path)])
    names = {f.name for f in files}
    assert names == {"a.jsonl", "b.jsonl"}


def test_extract_runs_dedups_rescored_over_original(tmp_path):
    # same run in an original (old gate=fail) and a rescored file (current gate=pass)
    base = _make_record(model="ollama:m", scenario="s1", with_cot=True, gate="fail")
    rescored = _make_record(model="ollama:m", scenario="s1", with_cot=True, gate="pass")
    (tmp_path / "20260620-120025.jsonl").write_text(json.dumps(base) + "\n")
    (tmp_path / "20260620-120025_rescored.jsonl").write_text(json.dumps(rescored) + "\n")
    runs, cov = ej._extract_runs(
        [tmp_path / "20260620-120025.jsonl", tmp_path / "20260620-120025_rescored.jsonl"], False
    )
    assert len(runs) == 1                       # deduped to one run
    assert runs[0]["gate_status"] == "pass"     # rescored (rank 0) won
    assert runs[0]["source_file"].endswith("_rescored.jsonl")
    assert cov["duplicate_variants_merged"] == 1
    assert cov["kept"] == 1


def test_extract_runs_dedups_backfill_redundant_with_original(tmp_path):
    # original + its cotbackfill are the same run (identical CoT) -> keep original
    base = _make_record(model="ollama:m", scenario="s1", with_cot=True, gate="pass")
    backfill = _make_record(model="ollama:m", scenario="s1", with_cot=True, gate="pass")
    (tmp_path / "20260620-120025.jsonl").write_text(json.dumps(base) + "\n")
    (tmp_path / "20260620-120025.jsonl.cotbackfill.jsonl").write_text(json.dumps(backfill) + "\n")
    runs, cov = ej._extract_runs(
        [tmp_path / "20260620-120025.jsonl", tmp_path / "20260620-120025.jsonl.cotbackfill.jsonl"], False
    )
    assert len(runs) == 1
    # original (rank 1) beats backfill (rank 2); both carry identical CoT anyway
    assert runs[0]["source_file"].endswith("20260620-120025.jsonl")
    assert cov["duplicate_variants_merged"] == 1


# ---------------------------------------------------------------------------
# chunking + pooling + 3 aggregations + halve-on-stall
# ---------------------------------------------------------------------------

from util.embeddings import _halve  # noqa: E402


def test_chunk_text_short_is_single():
    assert chunk_text("") == []
    assert chunk_text("short text") == ["short text"]
    assert chunk_text("x" * DEFAULT_MAX_CHARS) == ["x" * DEFAULT_MAX_CHARS]  # exactly max -> single


def test_chunk_text_long_splits_within_size_on_boundaries():
    text = " ".join(f"word{i}" for i in range(2000))    # ~12k chars
    chunks = chunk_text(text, max_chars=4000, overlap=400)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 4000
    # no chunk (except the last) ends mid-word — it ends on a space
    for c in chunks[:-1]:
        assert c.endswith(" ")
    # whole text is covered from the start
    assert text.startswith(chunks[0])
    # the last chunk reaches the end of the text
    assert text.endswith(chunks[-1].rstrip())


def test_chunk_text_overlap_and_no_tiny_chunks():
    text = " ".join(f"w{i}" for i in range(3000))
    chunks = chunk_text(text, max_chars=4000, overlap=400)
    # all but the last chunk are >= 60% of max_chars (no tiny interior chunks)
    for c in chunks[:-1]:
        assert len(c) >= int(4000 * 0.6)
    # consecutive chunks overlap (the start of chunk i is present in chunk i-1)
    for i in range(1, len(chunks)):
        assert chunks[i][:40] in chunks[i - 1]


def test_chunk_text_no_backwards_progress_with_paragraph_breaks():
    # Regression: a paragraph break near a window start used to make `start` walk
    # backwards (infinite loop) once start exceeded min_keep. Must terminate with
    # bounded, well-sized chunks.
    text = "".join(f"\n\n{('w ' * 1900)}" for _ in range(12))  # ~45k chars
    chunks = chunk_text(text, max_chars=4000, overlap=400)
    assert 8 <= len(chunks) <= 40                    # bounded -> no runaway / hang
    for c in chunks:
        assert len(c) <= 4000
    for c in chunks[:-1]:
        assert len(c) >= int(4000 * 0.6)            # progress always > overlap
    assert text.startswith(chunks[0])


def test_pool_normalizes_and_weights():
    p = pool([[3.0, 4.0]])
    assert p is not None
    assert math.sqrt(sum(x * x for x in p)) == pytest.approx(1.0)   # normalized
    # two orthogonal equal vectors -> 45 degrees
    p = pool([[1.0, 0.0], [0.0, 1.0]])
    assert p[0] == pytest.approx(p[1])
    assert p[0] == pytest.approx(1 / math.sqrt(2))
    # weight biases toward the heavier vector
    p = pool([[1.0, 0.0], [0.0, 1.0]], weights=[100.0, 1.0])
    assert p[0] > p[1]
    assert pool([]) is None


def test_agg_scores_max_mean_pooled():
    from evals.embedding_judge import _agg_scores

    cot = [([1.0, 0.0], 5), ([0.0, 1.0], 5)]
    ans = [([1.0, 0.0], 3)]
    s = _agg_scores(cot, ans)
    # pairs: cos([1,0],[1,0])=1 ; cos([0,1],[1,0])=0
    assert s["max"] == pytest.approx(1.0)
    assert s["mean"] == pytest.approx(0.5)
    # pooled cot = normalized mean([1,0],[0,1]) = [.707,.707]; ans=[1,0]; cos=.707
    assert s["pooled"] == pytest.approx(1 / math.sqrt(2), rel=1e-3)
    # empty side -> all None
    s2 = _agg_scores([], [([1.0, 0.0], 1)])
    assert all(v is None for v in s2.values())


def test_halve_splits_on_whitespace():
    a, b = _halve("alpha beta gamma delta epsilon zeta")
    assert a and b
    # the cut landed on a whitespace boundary -> concatenation (minus one sep) matches
    assert (a + " " + b) == "alpha beta gamma delta epsilon zeta"


def test_resolve_chunk_halves_on_failure(tmp_path):
    # embed_texts returns None for chunks > 200 chars (the MIN_HALVE_CHARS floor),
    # a vector for smaller ones — so resolve_chunk must halve to get embeddable pieces.
    client = EmbeddingClient(
        base_url="http://x", model="m", cache_path=str(tmp_path / "c.sqlite"), retry_backoff=0.0
    )

    async def fake_embed(texts):
        return [None if len(t) > 200 else _det_vec(t) for t in texts]

    client.embed_texts = fake_embed  # type: ignore[method-assign]
    # a ~700-char text "fails" (> 200) -> halved until each piece <= 200
    res = asyncio.run(client.resolve_chunk(" ".join(f"w{i}" for i in range(160))))
    assert len(res) >= 2
    assert all(v is not None for v, _ in res)


def test_overcap_error_short_circuits_no_retry(tmp_path):
    # An over-cap chunk raises "exceeds context length"; embed_texts must return
    # None for it WITHOUT retrying (an over-cap chunk will always fail), so the
    # server log gets one error, not batch_retries+1.
    client = EmbeddingClient(
        base_url="http://x", model="m", batch_retries=3, retry_backoff=0.0,
        cache_path=str(tmp_path / "c.sqlite"),
    )
    calls = [0]

    async def fake_batch(texts):
        calls[0] += 1
        if any(len(t) > 200 for t in texts):
            raise RuntimeError("the input length exceeds the context length of this model")
        return [_det_vec(t) for t in texts]

    client._embed_batch = fake_batch  # type: ignore[method-assign]
    out = asyncio.run(client.embed_texts(["big text " * 100]))  # ~900 chars -> over-cap
    assert out == [None]
    assert calls[0] == 1                     # NOT retried (would be 4 if it retried)


def test_is_overcap_error_detects_context_length_messages():
    from util.embeddings import is_overcap_error

    assert is_overcap_error(RuntimeError("the input length exceeds the context length"))
    assert is_overcap_error(RuntimeError("maximum context length is 2048 tokens"))
    assert not is_overcap_error(RuntimeError("connection reset"))
    assert not is_overcap_error(TimeoutError("timed out"))


def test_embed_document_chunks_long_text(tmp_path):
    client = EmbeddingClient(base_url="http://x", model="m", cache_path=str(tmp_path / "c.sqlite"))

    async def fake_embed(texts):
        return [_det_vec(t) for t in texts]

    client.embed_texts = fake_embed  # type: ignore[method-assign]
    assert len(asyncio.run(client.embed_document("short text"))) == 1
    long = " ".join(f"w{i}" for i in range(2000))      # ~12k chars -> several chunks
    res = asyncio.run(client.embed_document(long))
    assert len(res) >= 3
    assert all(v is not None for v, _ in res)


def test_end_to_end_long_cot_is_chunked(tmp_path):
    # a long CoT (well over the 2048-token cap) is chunked; all 3 aggregations populate
    jsonl = tmp_path / "in.jsonl"
    rec = _make_record()
    long_cot = "I will draw a triangle with vertices A B C. " * 1500  # ~64k chars
    rec["recipe_metadata"]["cot"] = long_cot
    rec["recipe_metadata"]["attempt_traces"][0]["cot"] = long_cot
    jsonl.write_text(json.dumps(rec) + "\n")

    out_dir = tmp_path / "out"
    fake = _FakeClient()
    summary = asyncio.run(
        ej.run([str(jsonl)], str(out_dir), embedding_model="x", embedding_base_url="http://x", client=fake)
    )
    assert summary["runs"] == 1
    assert summary["chunks"] >= 3                  # long cot -> multiple chunks
    r = json.loads((out_dir / "runs.jsonl").read_text().splitlines()[0])
    assert r["cot_chunks"] >= 3
    for a in ej.AGGS:
        assert r[f"cos_flat_dsl_{a}"] is not None
        assert r[f"cos_combined_{a}"] is not None