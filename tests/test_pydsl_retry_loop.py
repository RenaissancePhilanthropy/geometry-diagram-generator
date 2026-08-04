# tests/test_pydsl_retry_loop.py
"""Tests for the retry-loop driver: stops on success, stops at the cap."""
from geometry_diagrams.pydsl.retry_loop import run_with_retries


def test_stops_immediately_on_first_success():
    attempts_seen = []

    def make_script(history):
        attempts_seen.append(len(history))
        return "point(0, 0)"  # always valid

    results = run_with_retries(make_script, cap=5)
    assert len(results) == 1
    assert results[-1].error is None
    assert attempts_seen == [0]


def test_retries_until_success_within_cap():
    def make_script(history):
        if len(history) < 2:
            return "undefined_thing(1)"  # fails twice
        return "point(0, 0)"  # succeeds on the 3rd attempt

    results = run_with_retries(make_script, cap=5)
    assert len(results) == 3
    assert results[0].error is not None
    assert results[1].error is not None
    assert results[2].error is None


def test_stops_at_cap_when_every_attempt_fails():
    call_count = {"n": 0}

    def make_script(history):
        call_count["n"] += 1
        return "undefined_thing(1)"  # never valid

    results = run_with_retries(make_script, cap=3)
    assert len(results) == 3  # not before, not after
    assert call_count["n"] == 3
    assert all(r.error is not None for r in results)


def test_make_script_receives_the_prior_result_for_retry_prompting():
    seen_retry_messages = []

    def make_script(history):
        if history:
            seen_retry_messages.append(history[-1].retry_message)
            return "point(0, 0)"
        return "undefined_thing(1)"

    run_with_retries(make_script, cap=3)
    assert len(seen_retry_messages) == 1
    assert seen_retry_messages[0] is not None
