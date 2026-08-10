"""Tests for PythonFullStrategy and its LangGraph pipeline.

Only the LLM call is mocked — the real pydsl sandbox and the real
compile/check/render pipeline run for real (SVGRenderer, no Docker needed).
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from geometry_diagrams.strategies.python_full import (
    PythonFullStrategy, PydslScriptOutput, MAX_RETRIES, _run_script_node,
    _extract_script_from_raw_text, _unescape_literal_newlines,
    _unwrap_json_script_envelope, _clean_script, _fix_trailing_stray_indentation,
    _strip_whole_script_triple_quote_wrapper, _strip_leading_junk_line,
    _strip_trailing_envelope_residue,
)
from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
from geometry_diagrams.ir.renderer import SVGRenderer
from geometry_diagrams.pydsl.sandbox import ScriptResult


VALID_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
draw(t)
"""

TYPO_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangel(a, b, c)
draw(t)
"""

NO_DRAW_SCRIPT = """
a = point(0, 0)
b = point(4, 0)
c = point(0, 3)
t = triangle(a, b, c)
"""


def _make_script_response(script: str) -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 20}}
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    return {"raw": raw, "parsed": PydslScriptOutput(script=script), "parsing_error": None}


def _make_script_fail_response() -> dict:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 5, "output_tokens": 2}}
    raw.usage_metadata = {"input_tokens": 5, "output_tokens": 2}
    return {"raw": raw, "parsed": None, "parsing_error": "bad JSON from LLM"}


def _make_mock_llm(side_effects: list):
    """Return a mock LLM where with_structured_output().ainvoke() uses side_effects."""
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(side_effect=side_effects)
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)
    return mock_llm


@pytest.mark.asyncio
async def test_generate_script_node_forces_function_calling_for_qwen37flash_only():
    """Regression test for openrouter:qwen/qwen3.7-flash: letting
    with_structured_output guess its method silently picked json_mode for a
    model LangChain didn't recognize as tool-calling-capable, and the
    provider rejected every single attempt outright. method="function_calling"
    must be passed explicitly for this specific model (see llm.py's
    _FORCED_FUNCTION_CALLING_MODELS) — NOT for every model (see the sibling
    test below)."""
    mock_llm = _make_mock_llm([_make_script_response(VALID_SCRIPT)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        await strategy.run(
            "a right triangle", model="openrouter:qwen/qwen3.7-flash", renderer=SVGRenderer()
        )
    _, kwargs = mock_llm.with_structured_output.call_args
    assert kwargs["method"] == "function_calling"


async def test_generate_script_node_does_not_force_method_for_other_models():
    """Regression test for mantle-oa:google.gemma-4-31b: forcing
    method="function_calling" universally (the original, too-broad fix for
    qwen3.7-flash above) destabilized gemma-4-31b's tool-calling, regressing
    its pass rate from 84% to 57% (2026-08-07) — 10 real trials showed
    unforced auto-detection was reliable (9/10 clean) while forcing produced
    a degenerate output 4/10 times. Any model other than the confirmed
    qwen3.7-flash exception must get an unforced with_structured_output call
    (no "method" kwarg at all), matching pre-regression behavior."""
    mock_llm = _make_mock_llm([_make_script_response(VALID_SCRIPT)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        await strategy.run(
            "a right triangle", model="mantle-oa:google.gemma-4-31b", renderer=SVGRenderer()
        )
    _, kwargs = mock_llm.with_structured_output.call_args
    assert "method" not in kwargs


@pytest.mark.asyncio
async def test_first_attempt_success():
    mock_llm = _make_mock_llm([_make_script_response(VALID_SCRIPT)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert len(result.diagram_ir.define) > 0
    assert len(result.diagram_ir.render) > 0


@pytest.mark.asyncio
async def test_script_gen_failure_costs_one_attempt():
    """Mirrors test_structured_strategy.py's test_ir_gen_failure_costs_one_attempt:
    after script generation fails once, the sandbox must still run on the next
    attempt — _run_script_node must not double-count a generation failure."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_sandbox_failure_retries_with_did_you_mean_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(TYPO_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_nothing_drawn_guard_retries_and_succeeds():
    mock_llm = _make_mock_llm([
        _make_script_response(NO_DRAW_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1


@pytest.mark.asyncio
async def test_exhausts_retries_and_raises():
    mock_llm = _make_mock_llm([_make_script_response(TYPO_SCRIPT)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="PythonFullStrategy failed"):
            await strategy.run(
                "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
            )


@pytest.mark.asyncio
async def test_run_script_node_falls_back_to_error_when_retry_message_is_none():
    """sandbox.py's ExecutionTimeoutError branch always sets retry_message=None —
    _run_script_node must fall back to result.error so last_error is never empty.
    Tested directly against a canned ScriptResult (not a real timing-dependent
    sandbox race) since this is a deterministic fallback-logic check, not an
    integration behavior."""
    fake_result = ScriptResult(
        diagram_ir=None, error="boom, timed out", error_type="timeout", retry_message=None,
    )
    with patch("geometry_diagrams.strategies.python_full.run_script", return_value=fake_result):
        state = {"script": "point(0, 0)", "attempt": 0, "renderer": SVGRenderer()}
        update = await _run_script_node(state)
    assert update["last_error"] == "boom, timed out"
    assert update["attempt"] == 1


from geometry_diagrams.strategies.python_full import PythonFullMetadata


@pytest.mark.asyncio
async def test_metadata_records_one_trace_per_attempt_and_final_stage_success():
    """Retry-then-succeed: python_full_metadata (the dedicated field, never
    recipe_metadata) must have one trace per attempt, with the sandbox
    failure's message on the first and stage='success' on the second."""
    mock_llm = _make_mock_llm([
        _make_script_response(TYPO_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.recipe_metadata is None  # never touched
    meta = result.python_full_metadata
    assert isinstance(meta, PythonFullMetadata)
    assert len(meta.attempt_traces) == 2
    assert meta.attempt_traces[0].script == TYPO_SCRIPT
    assert meta.attempt_traces[0].stage == "sandbox"
    assert meta.attempt_traces[0].error is not None
    assert meta.attempt_traces[1].script == VALID_SCRIPT
    assert meta.attempt_traces[1].stage == "success"
    assert meta.attempt_traces[1].error is None


@pytest.mark.asyncio
async def test_metadata_records_nothing_drawn_stage():
    mock_llm = _make_mock_llm([
        _make_script_response(NO_DRAW_SCRIPT),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.python_full_metadata.attempt_traces[0].stage == "nothing_drawn"


@pytest.mark.asyncio
async def test_metadata_records_generation_failure_stage_without_double_counting():
    """Covers the script-is-None early-return path: _run_script_node must NOT
    touch the trace _generate_script_node already recorded for this attempt."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    meta = result.python_full_metadata
    assert len(meta.attempt_traces) == 2
    assert meta.attempt_traces[0].stage == "generation"
    assert meta.attempt_traces[0].script is None
    assert meta.attempt_traces[0].error == "bad JSON from LLM"


@pytest.mark.asyncio
async def test_run_reports_total_tokens_across_all_attempts():
    """Pre-existing bug caught while wiring metadata through run(): the current
    PythonFullStrategy.run() returns final_state["result"] directly without ever
    copying final_state's accumulated input_tokens/output_tokens onto it — so
    result.input_tokens/output_tokens are always 0 regardless of actual LLM
    usage (nothing previously asserted on these fields, so it went uncaught).
    A 2-attempt run must report tokens summed across BOTH generation calls."""
    mock_llm = _make_mock_llm([
        _make_script_fail_response(),  # 5 in / 2 out
        _make_script_response(VALID_SCRIPT),  # 10 in / 20 out
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert result.input_tokens == 15
    assert result.output_tokens == 22


@pytest.mark.asyncio
async def test_partial_metadata_captured_on_total_failure():
    """The exhausts-all-retries case — the single most important scenario for
    diagnostics, and the one the original design draft missed entirely."""
    mock_llm = _make_mock_llm([_make_script_response(TYPO_SCRIPT)] * MAX_RETRIES)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="PythonFullStrategy failed"):
            await strategy.run(
                "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
            )
    assert isinstance(strategy._partial_python_full_metadata, PythonFullMetadata)
    assert len(strategy._partial_python_full_metadata.attempt_traces) == MAX_RETRIES
    assert all(t.stage == "sandbox" for t in strategy._partial_python_full_metadata.attempt_traces)
    assert strategy._partial_input_tokens > 0
    assert strategy._partial_output_tokens > 0


# ---------------------------------------------------------------------------
# Fallback: some models don't honor the structured-output contract and just
# write plain/fenced code instead of JSON. _extract_script_from_raw_text lets
# _generate_script_node salvage a usable script from that raw text rather than
# treating it as an unrecoverable parse failure.
# ---------------------------------------------------------------------------

def test_extract_script_from_python_fenced_code_block():
    text = "Here's the script:\n```python\na = point(0, 0)\ndraw(a)\n```"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_from_bare_fenced_code_block():
    text = "```\na = point(0, 0)\ndraw(a)\n```"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_falls_back_to_raw_text_when_no_fence_present():
    text = "a = point(0, 0)\ndraw(a)"
    assert _extract_script_from_raw_text(text) == "a = point(0, 0)\ndraw(a)"


def test_extract_script_returns_none_for_empty_text():
    assert _extract_script_from_raw_text("") is None
    assert _extract_script_from_raw_text("   \n  ") is None


# ---------------------------------------------------------------------------
# Some models (observed: nvidia.nemotron-super-3-120b via Bedrock Mantle)
# intermittently emit every line break in the script field as a literal
# two-character "\n" sequence instead of an actual newline, collapsing the
# whole script onto one unparseable line. _unescape_literal_newlines recovers
# from this without touching any already-well-formed script.
# ---------------------------------------------------------------------------

def test_unescape_literal_newlines_fixes_a_fully_double_escaped_script():
    corrupted = "a = point(0, 0)\\nb = point(4, 0)\\ndraw(a)"
    assert _unescape_literal_newlines(corrupted) == "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"


def test_unescape_literal_newlines_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _unescape_literal_newlines(fine) == fine


def test_unescape_literal_newlines_is_a_noop_when_there_is_no_literal_backslash_n():
    fine = "a = point(0, 0)"
    assert _unescape_literal_newlines(fine) == fine


def test_unescape_literal_newlines_passes_through_none():
    assert _unescape_literal_newlines(None) is None


# ---------------------------------------------------------------------------
# Some models (observed: mantle:openai.gpt-oss-20b, ~80% of its curriculum-
# eval failures) emit their tool-call argument as a literal {"script": "..."}
# JSON envelope instead of raw Python, sometimes prefixed with junk text
# and/or wrapped in a ```python fence. _unwrap_json_script_envelope recovers
# the inner script; _clean_script chains it with _unescape_literal_newlines.
# ---------------------------------------------------------------------------

def test_unwrap_json_script_envelope_extracts_inner_script():
    text = '{"script": "a = point(0, 0)\\ndraw(a)"}'
    assert _unwrap_json_script_envelope(text) == "a = point(0, 0)\ndraw(a)"


def test_unwrap_json_script_envelope_handles_fence_and_junk_prefix():
    """Real example from a curriculum-eval failure corpus (2026-08-07)."""
    text = '```python\n#{ "script": "canvas(x_range=(-1,6))\\nA = point(0,0)\\ndraw(A)"}\n```'
    assert _unwrap_json_script_envelope(text) == "canvas(x_range=(-1,6))\nA = point(0,0)\ndraw(A)"


def test_unwrap_json_script_envelope_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _unwrap_json_script_envelope(fine) == fine


def test_unwrap_json_script_envelope_falls_back_to_manual_unescape_for_malformed_json():
    """Strict json.loads bails on this (the string never closes), but the
    manual-unescape fallback still recovers whatever's after the marker —
    this is no longer a pure no-op now that fallback exists (see
    test_unwrap_json_script_envelope_manually_recovers_an_unterminated_wrapper
    for the realistic multi-line version of this case)."""
    text = '{"script": "unterminated'
    assert _unwrap_json_script_envelope(text) == "unterminated"


def test_unwrap_json_script_envelope_passes_through_none():
    assert _unwrap_json_script_envelope(None) is None


def test_unwrap_json_script_envelope_manually_recovers_an_unterminated_wrapper():
    """Real example from a curriculum-eval failure corpus (2026-08-09,
    gpt-oss-20b): generation stopped mid-envelope, so the wrapper's own
    closing quote/brace never arrives and json.loads can't parse it — but
    the "script" value itself is complete, well-escaped JSON-string
    content. The manual-unescape fallback recovers it without requiring
    the wrapper to be valid JSON."""
    text = '#{ \n    "script": "a = point(0, 0)\\ndraw(a)\\n'
    assert _unwrap_json_script_envelope(text) == "a = point(0, 0)\ndraw(a)\n"


def test_unwrap_json_script_envelope_manual_fallback_strips_trailing_residue():
    """Same shape, but with trailing junk (a stray '}') left after the
    unterminated string — the manual fallback trims it rather than folding
    it into the recovered script."""
    text = 'import{"script":"a = point(0, 0)\\ndraw(a)"}'
    assert _unwrap_json_script_envelope(text) == "a = point(0, 0)\ndraw(a)"


# ---------------------------------------------------------------------------
# Whole-script triple-quote wrapper (observed: gpt-oss-20b) — the model
# wraps its entire script in a docstring-style triple-quoted string instead
# of emitting executable statements.
# ---------------------------------------------------------------------------

def test_strip_whole_script_triple_quote_wrapper_recovers_a_real_example():
    """Real example from a curriculum-eval failure corpus (2026-08-09):
    the whole script is wrapped in \"\"\"...\"\"\" with a stray trailing '}'
    left after the closing quotes."""
    script = '"""\na = point(0, 0)\nb = point(4, 0)\ndraw(a)\n"""\n}'
    assert _strip_whole_script_triple_quote_wrapper(script) == (
        "\na = point(0, 0)\nb = point(4, 0)\ndraw(a)\n"
    )


def test_strip_whole_script_triple_quote_wrapper_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _strip_whole_script_triple_quote_wrapper(fine) == fine


def test_strip_whole_script_triple_quote_wrapper_passes_through_none():
    assert _strip_whole_script_triple_quote_wrapper(None) is None


# ---------------------------------------------------------------------------
# A single junk line before the real script starts (observed: gpt-oss-20b) —
# a bare fence-language tag with no backticks, a filename, or a stray title.
# ---------------------------------------------------------------------------

def test_strip_leading_junk_line_recovers_a_bare_fence_tag():
    script = 'python\na = point(0, 0)\nb = point(4, 0)\ndraw(a)'
    assert _strip_leading_junk_line(script) == "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"


def test_strip_leading_junk_line_recovers_a_stray_title_line():
    script = '*** Begin Script ***\na = point(0, 0)\ndraw(a)'
    assert _strip_leading_junk_line(script) == "a = point(0, 0)\ndraw(a)"


def test_strip_leading_junk_line_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _strip_leading_junk_line(fine) == fine


def test_strip_leading_junk_line_leaves_a_single_broken_line_alone():
    """Nothing to recover if the whole script is just one broken line —
    stripping it would silently reduce the script to empty."""
    script = "python"
    assert _strip_leading_junk_line(script) == script


def test_strip_leading_junk_line_passes_through_none():
    assert _strip_leading_junk_line(None) is None


# ---------------------------------------------------------------------------
# A stray junk-only line left at the very end of an otherwise-correct script
# (observed: gpt-oss-20b) — either JSON-envelope residue or a bare closing
# markdown fence with no opening fence left in the script.
# ---------------------------------------------------------------------------

def test_strip_trailing_envelope_residue_recovers_a_stray_closing_brace():
    """Real example from a curriculum-eval failure corpus (2026-08-09)."""
    script = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)\n}"
    assert _strip_trailing_envelope_residue(script) == "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"


def test_strip_trailing_envelope_residue_recovers_a_bare_closing_fence():
    """Real example from a curriculum-eval failure corpus (2026-08-09): the
    opening ```python fence was already stripped elsewhere, leaving a bare
    closing ``` with no matching open."""
    script = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)\n```"
    assert _strip_trailing_envelope_residue(script) == "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"


def test_strip_trailing_envelope_residue_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _strip_trailing_envelope_residue(fine) == fine


def test_strip_trailing_envelope_residue_leaves_a_genuine_multiline_call_alone():
    """A trailing line that's syntactically pure closing-bracket punctuation
    from a REAL multi-line call must not be mistaken for envelope residue —
    stripping it would break, not fix, a script that was already correct."""
    script = "draw_points(\n    a, b\n)"
    assert _strip_trailing_envelope_residue(script) == script


def test_strip_trailing_envelope_residue_gives_up_when_stripping_cant_fix_it():
    """A script broken for an unrelated reason, whose last line happens to
    look like junk-only residue: stripping it doesn't fix the real error,
    so the function must give up and return the input unchanged rather
    than silently truncating real (if broken) code."""
    script = "a = point(0, 0\nb = point(4, 0)\ndraw(a)\n}"
    assert _strip_trailing_envelope_residue(script) == script


def test_strip_trailing_envelope_residue_passes_through_none():
    assert _strip_trailing_envelope_residue(None) is None


# ---------------------------------------------------------------------------
# The identical bug in two unrelated models (observed: openai:gpt-5.6-luna,
# openrouter:kwaipilot/kat-coder-air-v2.5) — every line from some point
# onward, always the trailing draw()/draw_points() block, carries one stray
# leading space, with everything before it at column 0.
# _fix_trailing_stray_indentation targets exactly this shape.
# ---------------------------------------------------------------------------

def test_fix_trailing_stray_indentation_recovers_a_real_example():
    """Real example from a curriculum-eval failure corpus (2026-08-08),
    trimmed to the essential shape: comment lines interspersed in the
    stray-indented block stay at column 0 while the real statements don't —
    the fix must not treat that as non-uniform."""
    script = (
        'a = point(0, 0)\n'
        'b = point(4, 0)\n'
        's = segment(a, b)\n'
        '\n'
        '# Draw everything\n'
        ' draw(s, color="blue")\n'
        '\n'
        '# Mark points\n'
        ' draw_points(a, b)'
    )
    fixed = _fix_trailing_stray_indentation(script)
    assert fixed == (
        'a = point(0, 0)\n'
        'b = point(4, 0)\n'
        's = segment(a, b)\n'
        '\n'
        '# Draw everything\n'
        'draw(s, color="blue")\n'
        '\n'
        '# Mark points\n'
        'draw_points(a, b)'
    )
    import ast
    ast.parse(fixed)  # must actually parse now


def test_fix_trailing_stray_indentation_is_a_noop_for_a_well_formed_script():
    fine = "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"
    assert _fix_trailing_stray_indentation(fine) == fine


def test_fix_trailing_stray_indentation_leaves_a_real_indented_block_alone():
    """A genuine for-loop's indentation must never be touched."""
    script = (
        "pts = []\n"
        "for i in range(3):\n"
        "    pts.append(point(i, i))\n"
        "draw_points(*pts)"
    )
    assert _fix_trailing_stray_indentation(script) == script


def test_fix_trailing_stray_indentation_bails_out_when_indent_is_not_uniform_to_eof():
    """Real example: indentation starts, stops, and resumes — not a single
    uniform trailing block. Must not guess; returns the input unchanged."""
    script = (
        "a = point(0, 0)\n"
        " draw(a)\n"
        "draw_points(a)"
    )
    assert _fix_trailing_stray_indentation(script) == script


def test_fix_trailing_stray_indentation_passes_through_none():
    assert _fix_trailing_stray_indentation(None) is None


def test_clean_script_unwraps_envelope_then_unescapes_newlines():
    """The envelope's own JSON decoding already turns \\n into real newlines,
    but _clean_script must still handle the case where a script that was
    NOT enveloped separately needs the literal-newline fix."""
    enveloped = '{"script": "a = point(0, 0)\\ndraw(a)"}'
    assert _clean_script(enveloped) == "a = point(0, 0)\ndraw(a)"

    double_escaped = "a = point(0, 0)\\nb = point(4, 0)\\ndraw(a)"
    assert _clean_script(double_escaped) == "a = point(0, 0)\nb = point(4, 0)\ndraw(a)"


def _make_unparsed_response(raw_content: str) -> dict:
    """A with_structured_output(include_raw=True) response where JSON parsing
    failed but the underlying model message still carries usable text."""
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 8, "output_tokens": 12}}
    raw.usage_metadata = {"input_tokens": 8, "output_tokens": 12}
    raw.content = raw_content
    return {"raw": raw, "parsed": None, "parsing_error": "Invalid JSON: expected value at line 1 column 1"}


@pytest.mark.asyncio
async def test_generate_script_node_salvages_a_script_from_fenced_raw_text_on_parse_failure():
    """The exact failure mode seen from a real weaker model: with_structured_output
    can't parse the model's markdown-fenced code as JSON, but the code itself is
    fine — this must succeed via the fallback, not be treated as a bare failure."""
    mock_llm = _make_mock_llm([
        _make_unparsed_response(f"```python\n{VALID_SCRIPT.strip()}\n```"),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert result.python_full_metadata.attempt_traces[0].stage == "success"


@pytest.mark.asyncio
async def test_generate_script_node_recovers_a_double_escaped_script_via_structured_output():
    """The nvidia.nemotron-super-3-120b failure mode: with_structured_output
    parses cleanly (parsed is not None, unlike the fenced-text fallback above),
    but the script field itself has every line break as a literal "\n" instead
    of a real newline. This must succeed via _unescape_literal_newlines rather
    than fail in the sandbox with a syntax error."""
    double_escaped = VALID_SCRIPT.strip().replace("\n", "\\n")
    mock_llm = _make_mock_llm([_make_script_response(double_escaped)])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert result.python_full_metadata.attempt_traces[0].stage == "success"
    assert "\\n" not in result.python_full_metadata.attempt_traces[0].script


# ---------------------------------------------------------------------------
# vercel:meta/muse-spark-1.2-contributor rejects BOTH with_structured_output
# methods this pipeline supports (forced tool_choice AND json_mode) with a
# deterministic API-level error — requires_raw_text_generation() routes these
# models around with_structured_output entirely, calling llm.ainvoke()
# directly and salvaging from plain content as the ONLY generation path.
# ---------------------------------------------------------------------------

def _make_raw_ainvoke_mock_llm(content: "str | None") -> MagicMock:
    raw = MagicMock()
    raw.response_metadata = {"usage": {"input_tokens": 10, "output_tokens": 20}}
    raw.usage_metadata = {"input_tokens": 10, "output_tokens": 20}
    raw.content = content
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=raw)
    return mock_llm


@pytest.mark.asyncio
async def test_generate_script_node_uses_raw_text_path_for_models_requiring_it():
    """Must call llm.ainvoke() directly and never with_structured_output for
    a model in llm.py's _RAW_TEXT_ONLY_MODELS."""
    mock_llm = _make_raw_ainvoke_mock_llm(f"```python\n{VALID_SCRIPT.strip()}\n```")
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="vercel:meta/muse-spark-1.2-contributor", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert result.python_full_metadata.attempt_traces[0].stage == "success"
    mock_llm.with_structured_output.assert_not_called()


@pytest.mark.asyncio
async def test_generate_script_node_raw_text_path_fails_cleanly_on_empty_content():
    """No usable text at all must be a real generation failure, not a silent
    success with an empty/None script."""
    mock_llm = _make_raw_ainvoke_mock_llm(None)
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        with pytest.raises(RuntimeError, match="failed after"):
            await strategy.run(
                "a right triangle", model="vercel:meta/muse-spark-1.2-contributor", renderer=SVGRenderer()
            )
    assert mock_llm.ainvoke.call_count == MAX_RETRIES


@pytest.mark.asyncio
async def test_generate_script_node_still_fails_when_raw_text_is_empty():
    """If there's truly nothing to salvage (empty raw content), this must still
    be a real generation failure, not silently succeed with an empty script."""
    mock_llm = _make_mock_llm([
        _make_unparsed_response(""),
        _make_script_response(VALID_SCRIPT),
    ])
    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 1
    assert result.python_full_metadata.attempt_traces[0].stage == "generation"
    assert result.python_full_metadata.attempt_traces[0].script is None


def _make_real_validation_error(raw_text: str):
    """A genuine pydantic ValidationError, triggered the same way
    with_structured_output's internals trigger it — not a hand-constructed
    stand-in — so the test exercises the actual .errors()[0]['input'] shape."""
    from pydantic import ValidationError
    try:
        PydslScriptOutput.model_validate_json(raw_text)
    except ValidationError as e:
        return e
    raise AssertionError(f"expected {raw_text!r} to fail JSON validation")


@pytest.mark.asyncio
async def test_generate_script_node_salvages_a_script_when_with_structured_output_raises():
    """The exact failure mode seen from poolside/laguna-s-2.1 via openrouter:
    with_structured_output doesn't gracefully return parsed=None — it raises a
    ValidationError directly out of structured.ainvoke(), bypassing the
    parsed-is-None branch entirely. The full raw text must still be salvageable
    from the exception itself (str(exc) truncates it; .errors()[0]['input'] does not)."""
    raw_text = f"Here's the script:\n```python\n{VALID_SCRIPT.strip()}\n```"
    structured_mock = MagicMock()
    structured_mock.ainvoke = AsyncMock(side_effect=[_make_real_validation_error(raw_text)])
    mock_llm = MagicMock()
    mock_llm.with_structured_output = MagicMock(return_value=structured_mock)

    with patch("geometry_diagrams.strategies.python_full.get_chat_model", return_value=mock_llm):
        strategy = PythonFullStrategy()
        result = await strategy.run(
            "a right triangle", model="anthropic:claude-sonnet-4-6", renderer=SVGRenderer()
        )
    assert isinstance(result, StructuredRunResult)
    assert result.retries == 0
    assert result.python_full_metadata.attempt_traces[0].stage == "success"
    assert result.python_full_metadata.attempt_traces[0].script == VALID_SCRIPT.strip()


def test_run_script_node_attaches_variable_ids_and_entity_manifest():
    import asyncio
    from geometry_diagrams.strategies.python_full import (
        _run_script_node, PythonFullMetadata, PythonFullAttemptTrace,
    )
    from geometry_diagrams.ir.renderer import SVGRenderer

    script = """
a = point(0, 0)
b = point(3, 0)
c = point(0, 4)
t = triangle(a, b, c)
draw(t)
"""
    metadata = PythonFullMetadata(attempt_traces=[
        PythonFullAttemptTrace(attempt=0, script=script, error=None, stage="generation"),
    ])
    state = {
        "prompt": "a right triangle",
        "model_id": "test",
        "enable_cache": False,
        "attempt": 0,
        "last_error": "",
        "script": script,
        "result": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "renderer": SVGRenderer(),
        "metadata": metadata,
    }
    update = asyncio.run(_run_script_node(state))
    result = update["result"]
    assert result is not None
    assert set(result.variable_ids) == {"a", "b", "c", "t"}
    # The stored script has its leading/trailing blank lines stripped (this
    # fixture's own leading "\n" is exactly the pattern that motivated that
    # normalization) — see test_run_script_node_normalizes_leading_and_trailing_blank_lines_in_stored_script.
    assert result.script == script.strip("\n") + "\n"
    named_names = {e["name"] for e in result.entity_manifest["named"]}
    assert "t" in named_names


def test_build_edit_prompt_includes_script_manifest_and_naming_contract():
    from geometry_diagrams.strategies.python_full import build_edit_prompt

    manifest = {
        "named": [{"name": "tri", "id": "t1", "type": "triangle", "approx_position": [1.0, 2.0]}],
        "anonymous": [],
    }
    prompt = build_edit_prompt("make it bigger", "tri = triangle(a, b, c)\ndraw(tri)", manifest)

    assert "make it bigger" in prompt
    assert "tri = triangle(a, b, c)" in prompt
    assert '"name": "tri"' in prompt
    assert "same variable name" in prompt.lower()


def test_build_agent_returns_a_graph_instead_of_raising():
    from geometry_diagrams.strategies.python_full import PythonFullStrategy

    strategy = PythonFullStrategy()
    graph = strategy.build_agent(model="anthropic:claude-haiku-4-5-20251001")
    assert graph is not None


@pytest.mark.asyncio
async def test_render_diagram_tool_edits_using_previous_script_context(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    prompts_seen: list[str] = []

    async def fake_run(self, prompt, model="test", renderer=None):
        prompts_seen.append(prompt)
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg=f"<svg>{len(prompts_seen)}</svg>",
            sym_table={}, sym_full={},
            script="a = point(0,0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={
                "named": [{"name": "a", "id": "p1", "type": "point_fixed", "approx_position": [0.0, 0.0]}],
                "anonymous": [],
            },
        )

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    strategy = PythonFullStrategy()
    graph = strategy.build_agent(model="test")
    tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
    render_tool = tools_by_name["render_diagram"]

    await render_tool.ainvoke({"request": "draw a point"})
    await render_tool.ainvoke({"request": "move it up"})

    assert len(prompts_seen) == 2
    assert prompts_seen[0] == "draw a point"
    assert "a = point(0,0)" in prompts_seen[1]
    assert "same variable name" in prompts_seen[1].lower()


def _closure_stack(render_tool):
    """Pull the `_stack` list out of render_diagram's closure for assertions.
    There is no public accessor for the edit stack, so tests reach into the
    coroutine's closure cells by free-variable name."""
    fn = render_tool.coroutine
    idx = fn.__code__.co_freevars.index("_stack")
    return fn.__closure__[idx].cell_contents


@pytest.mark.asyncio
async def test_render_diagram_survives_a_locality_diagnostic_crash(monkeypatch):
    """check_edit_locality is a diagnostic only — per the Global Constraints
    it must never be able to fail an edit turn, even if it raises internally."""
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    call_count = 0

    async def fake_run(self, prompt, model="test", renderer=None):
        nonlocal call_count
        call_count += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg=f"<svg>{call_count}</svg>",
            sym_table={}, sym_full={},
            script="a = point(0,0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={
                "named": [{"name": "a", "id": "p1", "type": "point_fixed", "approx_position": [0.0, 0.0]}],
                "anonymous": [],
            },
        )

    def raising_check_edit_locality(*args, **kwargs):
        raise RuntimeError("boom: bug inside the diagnostic")

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    monkeypatch.setattr(
        "geometry_diagrams.strategies.python_full.check_edit_locality",
        raising_check_edit_locality,
    )
    strategy = PythonFullStrategy()
    graph = strategy.build_agent(model="test")
    tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
    render_tool = tools_by_name["render_diagram"]

    first = json.loads(await render_tool.ainvoke({"request": "draw a point"}))
    second = json.loads(await render_tool.ainvoke({"request": "move it up"}))

    assert "svg" in first and "error" not in first
    assert "svg" in second and "error" not in second

    stack = _closure_stack(render_tool)
    assert len(stack) == 2
    assert stack[-1]["locality_diagnostic"] is None


@pytest.mark.asyncio
async def test_render_diagram_attaches_locality_diagnostic_to_stack_frame():
    """A successful diagnostic's result must be retrievable (not thrown away)
    from the stack frame it was computed for."""
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR
    from geometry_diagrams.ir.edit_diagnostics import LocalityDiagnostic

    call_count = 0

    async def fake_run(self, prompt, model="test", renderer=None):
        nonlocal call_count
        call_count += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg=f"<svg>{call_count}</svg>",
            sym_table={}, sym_full={},
            script="a = point(0,0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={
                "named": [{"name": "a", "id": "p1", "type": "point_fixed", "approx_position": [0.0, 0.0]}],
                "anonymous": [],
            },
        )

    with patch.object(PythonFullStrategy, "run", fake_run):
        strategy = PythonFullStrategy()
        graph = strategy.build_agent(model="test")
        tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
        render_tool = tools_by_name["render_diagram"]

        await render_tool.ainvoke({"request": "draw a point"})
        await render_tool.ainvoke({"request": "move it up"})

    stack = _closure_stack(render_tool)
    assert len(stack) == 2
    diagnostic = stack[-1]["locality_diagnostic"]
    assert isinstance(diagnostic, LocalityDiagnostic)
    assert diagnostic.matched_names == {"a"}


@pytest.mark.asyncio
async def test_generate_patch_includes_pydsl_api_instructions_as_system_message():
    """_generate_patch must give the model the same pydsl API reference
    _generate_script_node gives full-script generation — without it, the
    model has no information about the actual API surface and hallucinates
    plausible-but-nonexistent calls (e.g. draw(fill_color=...) instead of a
    separate fill() call, or angle(...).mark_right_angle() instead of the
    standalone mark_right_angle() function) — confirmed via live testing."""
    from geometry_diagrams.strategies import python_full as pf_module
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    captured_messages = []

    class FakeStructured:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return pf_module.PydslScriptPatchOutput(patch="@@ -1,1 +1,1 @@\n-a\n+b\n")

    class FakeLLM:
        def with_structured_output(self, schema, include_raw=False):
            return FakeStructured()

    with patch.object(pf_module, "get_chat_model", return_value=FakeLLM()):
        result = await pf_module._generate_patch("edit this script", model="test")

    assert result == "@@ -1,1 +1,1 @@\n-a\n+b\n"
    assert len(captured_messages) == 2
    system_message, human_message = captured_messages
    assert system_message.content or (
        isinstance(system_message.content, list) and system_message.content
    )
    system_text = (
        system_message.content
        if isinstance(system_message.content, str)
        else system_message.content[0].get("text", "")
    )
    assert build_python_full_instructions()[:200] in system_text
    assert human_message.content == "edit this script"


def test_run_script_node_normalizes_leading_and_trailing_blank_lines_in_stored_script():
    """A script with a leading blank line (routine LLM output — confirmed via
    live testing) is ambiguous once embedded in a markdown-fenced prompt for
    a later edit turn: the model consistently loses count of "line 1" being
    blank, producing hunk headers off by one against the real script and
    failing apply_script_patch's context check on every single attempt.
    The EXECUTED script is untouched (leading blank lines are harmless to
    run) — only the STORED copy used for future prompts/patches is
    normalized, so there's exactly one unambiguous "line 1" going forward."""
    import asyncio
    from geometry_diagrams.strategies.python_full import (
        _run_script_node, PythonFullMetadata, PythonFullAttemptTrace,
    )
    from geometry_diagrams.ir.renderer import SVGRenderer

    script = "\n\ncanvas(x_range=(0, 10), y_range=(0, 10))\na = point(0, 0)\ndraw_points(a)\n\n\n"
    metadata = PythonFullMetadata(attempt_traces=[
        PythonFullAttemptTrace(attempt=0, script=script, error=None, stage="generation"),
    ])
    state = {
        "prompt": "a point", "model_id": "test", "enable_cache": False,
        "attempt": 0, "last_error": "", "script": script, "result": None,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
        "renderer": SVGRenderer(), "metadata": metadata,
    }
    update = asyncio.run(_run_script_node(state))
    result = update["result"]
    assert result is not None
    assert result.script == "canvas(x_range=(0, 10), y_range=(0, 10))\na = point(0, 0)\ndraw_points(a)\n"


def test_build_search_replace_request_prompt_includes_script_manifest_and_naming_contract():
    from geometry_diagrams.strategies.python_full import build_search_replace_request_prompt

    manifest = {"named": [{"name": "tri", "id": "t1", "type": "triangle", "approx_position": [1.0, 2.0]}], "anonymous": []}
    prompt = build_search_replace_request_prompt("make it bigger", "tri = triangle(a, b, c)\ndraw(tri)", manifest)

    assert "make it bigger" in prompt
    assert "tri = triangle(a, b, c)" in prompt
    assert '"name": "tri"' in prompt
    assert "same variable name" in prompt.lower()
    assert "unique" in prompt.lower()


@pytest.mark.asyncio
async def test_generate_search_replace_includes_pydsl_api_instructions_as_system_message():
    from geometry_diagrams.strategies import python_full as pf_module
    from geometry_diagrams.strategies.instructions_python_full import build_python_full_instructions

    captured_messages = []

    class FakeStructured:
        async def ainvoke(self, messages):
            captured_messages.extend(messages)
            return pf_module.PydslSearchReplaceOutput(
                blocks=[pf_module.SearchReplaceBlock(old_string="a", new_string="b")]
            )

    class FakeLLM:
        def with_structured_output(self, schema, include_raw=False):
            return FakeStructured()

    with patch.object(pf_module, "get_chat_model", return_value=FakeLLM()):
        result = await pf_module._generate_search_replace("edit this script", model="test")

    assert result == [{"old_string": "a", "new_string": "b"}]
    assert len(captured_messages) == 2
    system_message = captured_messages[0]
    system_text = (
        system_message.content
        if isinstance(system_message.content, str)
        else system_message.content[0].get("text", "")
    )
    assert build_python_full_instructions()[:200] in system_text


@pytest.mark.asyncio
async def test_render_diagram_edits_via_search_replace_mode(monkeypatch):
    from geometry_diagrams.strategies.python_full import PythonFullStrategy
    from geometry_diagrams.strategies.ir_pipeline import StructuredRunResult
    from geometry_diagrams.ir.ir import DiagramIR

    call_count = 0

    async def fake_run(self, prompt, model="test", renderer=None):
        nonlocal call_count
        call_count += 1
        return StructuredRunResult(
            diagram_ir=DiagramIR(define=[], render=[]),
            tikz="", svg=f"<svg>{call_count}</svg>",
            sym_table={}, sym_full={},
            script="a = point(0, 0)\ndraw_points(a)\n",
            variable_ids={"a": "p1"},
            entity_manifest={"named": [{"name": "a", "id": "p1", "type": "point_fixed", "approx_position": [0.0, 0.0]}], "anonymous": []},
            retries=0,
        )

    async def fake_generate_search_replace(prompt, model, enable_cache=False):
        return [{"old_string": "a = point(0, 0)", "new_string": "a = point(9, 9)"}]

    monkeypatch.setattr(PythonFullStrategy, "run", fake_run)
    monkeypatch.setattr(
        "geometry_diagrams.strategies.python_full._generate_search_replace",
        fake_generate_search_replace,
    )

    strategy = PythonFullStrategy()
    graph = strategy.build_agent(model="test", edit_generation_mode="search_replace")
    tools_by_name = {t.name: t for t in graph.nodes["tools"].bound.tools_by_name.values()}
    render_tool = tools_by_name["render_diagram"]

    first = json.loads(await render_tool.ainvoke({"request": "draw a point"}))
    second = json.loads(await render_tool.ainvoke({"request": "move it"}))

    assert "svg" in first and "error" not in first
    assert "svg" in second and "error" not in second
