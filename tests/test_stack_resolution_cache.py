"""Block stack: the cube-set resolution of the ``cubes`` form is cached by the
exact cube list, errors are never cached, and the cached lattice id mapping is
read-only so one caller cannot corrupt later compiles."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir import ir, stack
from geometry_diagrams.ir.errors import IRCompileError
from geometry_diagrams.ir.to_sympy import compile_defs

CUBES = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]


def _stmt(cubes, sid="S"):
    return ir.BlockStack(id=sid, origin="O", cubes=cubes)


def test_cube_set_validation_runs_once_per_cube_list(monkeypatch):
    stack._cached_cube_set.cache_clear()
    calls = []
    real = stack._validate_cube_set
    monkeypatch.setattr(stack, "_validate_cube_set", lambda *a: calls.append(a) or real(*a))
    stmt = _stmt([list(c) for c in CUBES])
    for _ in range(5):
        stack._resolve(stmt)
        stack._valid_cubes(stmt)
        stack.bounding_extents(stmt)
    assert len(calls) == 1
    cubes, extents = stack._resolve(stmt)
    assert cubes == {(0, 0, 0), (1, 0, 0), (0, 1, 0)} and extents == (2, 2, 1)


def test_a_different_cube_list_is_not_served_from_the_cache():
    stack._cached_cube_set.cache_clear()
    stack._resolve(_stmt([[0, 0, 0]], "A"))
    # 0.5 is not an integer: must fail after the same id's valid list was cached
    with pytest.raises(IRCompileError, match="integer"):
        stack._resolve(_stmt([[0.5, 0, 0]], "A"))


def test_errors_are_raised_every_time():
    bad = _stmt([[0, 0, 0], [0, 0, 0]])
    for _ in range(2):
        with pytest.raises(IRCompileError, match="duplicate"):
            stack._resolve(bad)


def test_lattice_names_are_read_only():
    stmt = _stmt([list(c) for c in CUBES])
    names = stack.lattice_names(stmt)
    with pytest.raises(TypeError):
        names[(9, 9, 9)] = "x"  # type: ignore[index]
    assert len(stack.lattice_names(stmt)) == len(names)
    sym = compile_defs(ir.DiagramIR(define=[ir.PointFixed(id="O", x=0, y=0), stmt]))
    assert set(sym["S"].lattice_ids.values()) <= set(sym)
    assert stack.lattice_names(_stmt(None)) == {}
