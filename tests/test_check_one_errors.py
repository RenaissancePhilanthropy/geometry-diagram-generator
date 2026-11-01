"""_check_one: unknown ids get a clear message, internal exceptions are logged
and named, an unknown check kind warns (and still passes)."""
from __future__ import annotations

import logging

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.checks import run_checks
from geometry_diagrams.ir.to_sympy import compile_defs

CANVAS = {"xmin": -10, "xmax": 10, "ymin": -10, "ymax": 10}


def _sym():
    return compile_defs(ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [
        {"id": "A", "kind": "point_fixed", "x": 0, "y": 0},
        {"id": "B", "kind": "point_fixed", "x": 1, "y": 0},
        {"id": "s", "kind": "segment", "a": "A", "b": "B"},
    ]}))


def _check(**kw):
    return ir.DiagramIR.model_validate({"canvas": CANVAS, "define": [], "checks": [kw]}).checks[0]


def test_unknown_id_message():
    r = run_checks([_check(kind="distinct_points", a="A", b="ZZ")], _sym())[0]
    assert not r.passed
    assert "unknown id 'ZZ'" in r.message
    assert "KeyError" not in r.message


def test_internal_exception_is_logged_and_named(caplog):
    # A segment where a point is required fails inside SymPy, not in a verdict.
    with caplog.at_level(logging.WARNING, logger="geometry_diagrams.ir.checks"):
        r = run_checks([_check(kind="distinct_points", a="A", b="s")], _sym())[0]
    assert not r.passed
    assert r.message.startswith("Error in 'distinct_points': ")
    type_name = r.message.split(": ")[1]
    assert type_name[0].isupper() and type_name.isidentifier()
    assert any(rec.exc_info for rec in caplog.records)


def test_unknown_kind_warns_but_passes():
    warnings: list[str] = []
    check = ir.CheckBase(kind="mystery_kind")
    r = run_checks([check], _sym(), warnings=warnings)[0]
    assert r.passed
    assert "unrecognized check kind" in r.message
    assert any("mystery_kind" in w for w in warnings)
