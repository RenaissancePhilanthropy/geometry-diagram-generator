"""Tests for evals/sympy_checks.py — especially prime notation normalization."""
from __future__ import annotations

import math

import pytest

from evals.sympy_checks import _resolve_point_name, _validate_properties_sympy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_sym_float(**kwargs: tuple[float, float]) -> dict:
    """Build a sym_float dict mapping point IDs to (x, y) tuples."""
    return dict(kwargs)


# A realistic symbol table with prime-notation names from the model
SYMMETRIC_TABLE = _make_sym_float(
    A=(1.0, 2.0),
    B=(4.0, 2.0),
    C=(3.0, 4.0),
    D=(2.0, 4.0),
    A_prime=(3.0, 2.0),
    B_prime=(6.0, 2.0),
    C_prime=(5.0, 4.0),
    D_prime=(4.0, 4.0),
    A_double=(5.0, 2.0),
    B_double=(8.0, 2.0),
    P_prime=(3.0, 1.0),
    Q_prime=(5.0, 1.0),
    R_prime=(4.0, 3.0),
)


# ---------------------------------------------------------------------------
# _resolve_point_name tests
# ---------------------------------------------------------------------------

class TestResolvePointName:
    """Test that _resolve_point_name maps prime notation to model IDs."""

    def test_exact_match(self):
        """Exact names in sym_float are returned directly."""
        assert _resolve_point_name("A", SYMMETRIC_TABLE) == (1.0, 2.0)

    def test_single_prime_to_underscore_prime(self):
        """A' resolves to A_prime."""
        assert _resolve_point_name("A'", SYMMETRIC_TABLE) == (3.0, 2.0)

    def test_double_prime_to_underscore_double(self):
        """A'' resolves to A_double."""
        assert _resolve_point_name("A''", SYMMETRIC_TABLE) == (5.0, 2.0)

    def test_single_prime_P(self):
        """P' resolves to P_prime."""
        assert _resolve_point_name("P'", SYMMETRIC_TABLE) == (3.0, 1.0)

    def test_missing_point_returns_none(self):
        """Non-existent point returns None."""
        assert _resolve_point_name("Z", SYMMETRIC_TABLE) is None

    def test_missing_prime_point_returns_none(self):
        """Non-existent prime point returns None."""
        assert _resolve_point_name("Z'", SYMMETRIC_TABLE) is None

    def test_aprime_no_underscore(self):
        """A' resolves to Aprime (no underscore variant)."""
        table = _make_sym_float(Aprime=(7.0, 8.0))
        assert _resolve_point_name("A'", table) == (7.0, 8.0)

    def test_aprime_with_suffix(self):
        """A' resolves to A1 (numeric suffix variant)."""
        table = _make_sym_float(A1=(9.0, 10.0))
        assert _resolve_point_name("A'", table) == (9.0, 10.0)

    def test_double_prime_to_double_prime_suffix(self):
        """A'' resolves to A_double_prime."""
        table = _make_sym_float(A_double_prime=(11.0, 12.0))
        assert _resolve_point_name("A''", table) == (11.0, 12.0)

    def test_double_prime_to_numeric_suffix(self):
        """A'' resolves to A2 (numeric suffix variant)."""
        table = _make_sym_float(A2=(13.0, 14.0))
        assert _resolve_point_name("A''", table) == (13.0, 14.0)

    def test_triple_prime(self):
        """A''' resolves to A_triple_prime."""
        table = _make_sym_float(A_triple_prime=(15.0, 16.0))
        assert _resolve_point_name("A'''", table) == (15.0, 16.0)

    def test_exact_match_takes_priority(self):
        """If both A' and A_prime exist as keys, exact match wins."""
        table = _make_sym_float(**{"A'": (1.0, 1.0), "A_prime": (2.0, 2.0)})
        assert _resolve_point_name("A'", table) == (1.0, 1.0)

    def test_composite_name_prime_with_suffix_C_prime_1(self):
        """C'1 resolves to C_prime_1, C_prime1, or C_p1."""
        # C'1 → base='C', primes=1, suffix='1'
        table = _make_sym_float(C_prime_1=(5.0, 6.0))
        assert _resolve_point_name("C'1", table) == (5.0, 6.0)

    def test_composite_name_prime_with_suffix_C_prime1(self):
        """C'1 resolves to C_prime1 (no underscore before digit)."""
        table = _make_sym_float(C_prime1=(5.0, 6.0))
        assert _resolve_point_name("C'1", table) == (5.0, 6.0)

    def test_composite_name_prime_with_suffix_C_p1(self):
        """C'1 resolves to C_p1 (short form)."""
        table = _make_sym_float(C_p1=(5.0, 6.0))
        assert _resolve_point_name("C'1", table) == (5.0, 6.0)

    def test_composite_name_prime_with_suffix_C1_prime(self):
        """C'1 resolves to C1_prime (suffix before prime word)."""
        table = _make_sym_float(**{"C1_prime": (7.0, 8.0)})
        assert _resolve_point_name("C'1", table) == (7.0, 8.0)

    def test_composite_name_prime_with_suffix_C1p(self):
        """C'1 resolves to C1p (short form, suffix first)."""
        table = _make_sym_float(**{"C1p": (7.0, 8.0)})
        assert _resolve_point_name("C'1", table) == (7.0, 8.0)

    def test_single_prime_to_p_short_form(self):
        """A' resolves to A_p (short form)."""
        table = _make_sym_float(A_p=(7.0, 8.0))
        assert _resolve_point_name("A'", table) == (7.0, 8.0)

    def test_double_prime_to_p2(self):
        """A'' resolves to A_p2 (short form)."""
        table = _make_sym_float(A_p2=(9.0, 10.0))
        assert _resolve_point_name("A''", table) == (9.0, 10.0)

    def test_composite_name_C1_prime(self):
        """P1' resolves to P1_prime."""
        table = _make_sym_float(P1_prime=(10.0, 20.0))
        assert _resolve_point_name("P1'", table) == (10.0, 20.0)

    def test_composite_name_with_number_before_prime(self):
        """C1' where C1 is part of the base name."""
        table = _make_sym_float(C1_prime=(3.0, 5.0))
        # "C1'" → rstrip("'") = "C1", n_primes=1, base="C1"
        # generates: C1_prime, C1_prime_prime, C1prime, C1prime, C1_prime, C11
        assert _resolve_point_name("C1'", table) == (3.0, 5.0)


# ---------------------------------------------------------------------------
# Integration tests with _validate_properties_sympy
# ---------------------------------------------------------------------------

class TestValidatePropertiesSympy:
    """Test that _validate_properties_sympy works with prime notation normalization."""

    def test_equal_lengths_with_prime_notation(self):
        """Property check using A' notation resolves to A_prime in sym_float."""
        sym_float = _make_sym_float(
            A=(1.0, 2.0), B=(4.0, 2.0),
            A_prime=(5.0, 2.0), B_prime=(8.0, 2.0),
        )
        props = [
            {
                "name": "equal_lengths_AB_AprimeBprime",
                "type": "equal_lengths",
                "args": [["A", "B"], ["A'", "B'"]],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert len(results) == 1
        assert results[0]["passed"] is True

    def test_midpoint_with_prime_notation(self):
        """Midpoint check using A' notation resolves correctly."""
        sym_float = _make_sym_float(
            A=(0.0, 0.0),
            A_prime=(4.0, 0.0),
            M=(2.0, 0.0),
        )
        props = [
            {
                "name": "midpoint_M",
                "type": "midpoint",
                "args": ["M", "A", "A'"],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True

    def test_right_angle_with_prime_notation(self):
        """Right angle check using A'' (double prime) resolves to A_double."""
        sym_float = _make_sym_float(
            A=(0.0, 0.0),
            O=(1.0, 1.0),
            A_double=(2.0, 0.0),  # model uses A_double for A''
        )
        # A'' is at (2,0), O is at (1,1), A is at (0,0)
        # Vector OA = (-1, -1), Vector OA'' = (1, -1), dot product = -1 + 1 = 0 → right angle
        props = [
            {
                "name": "right_angle",
                "type": "right_angle",
                "args": ["A", "O", "A''"],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True

    def test_prime_notation_not_found_gives_error(self):
        """If no variant matches, the check reports an error."""
        sym_float = _make_sym_float(A=(1.0, 2.0))
        props = [
            {
                "name": "equal_lengths",
                "type": "equal_lengths",
                "args": [["A", "Z'"], ["A", "B"]],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is False
        assert "not in symbol table" in results[0]["message"]

    def test_parallel_with_prime_notation(self):
        """Parallel check using A' resolves correctly."""
        # AB: (0,0) → (3,0), A'B': (1,2) → (4,2) — parallel horizontal lines
        sym_float = _make_sym_float(
            A=(0.0, 0.0), B=(3.0, 0.0),
            A_prime=(1.0, 2.0), B_prime=(4.0, 2.0),
        )
        props = [
            {
                "name": "parallel_AB_AprimeBprime",
                "type": "parallel",
                "args": [["A", "B"], ["A'", "B'"]],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True

    def test_point_on_circle_with_prime(self):
        """Point on circle check with P' notation."""
        import math
        # Circle centered at O=(0,0), radius 2. P=(2,0) is on it. P'=(-2,0) is also on it.
        sym_float = _make_sym_float(
            P=(2.0, 0.0), P_prime=(-2.0, 0.0), O=(0.0, 0.0), R=(0.0, 2.0),
        )
        props = [
            {
                "name": "Pprime_on_circle",
                "type": "point_on_circle",
                "args": ["P'", "O", "R"],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True

    def test_collinear_with_prime(self):
        """Collinear check using A' and A'' notation."""
        # A=(0,0), A'=(1,1), A''=(2,2) — collinear
        sym_float = _make_sym_float(
            A=(0.0, 0.0), A_prime=(1.0, 1.0), A_double=(2.0, 2.0),
        )
        props = [
            {
                "name": "collinear_primes",
                "type": "collinear",
                "args": ["A", "A'", "A''"],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True

    def test_mixed_prime_and_regular(self):
        """Properties mixing regular and prime points."""
        # A=(0,0), B=(4,0), A'=(2,0) midpoint
        sym_float = _make_sym_float(
            A=(0.0, 0.0), B=(4.0, 0.0), A_prime=(2.0, 0.0),
        )
        props = [
            {
                "name": "midpoint_A_prime",
                "type": "midpoint",
                "args": ["A'", "A", "B"],
            },
            {
                "name": "equal_lengths",
                "type": "equal_lengths",
                "args": [["A", "A'"], ["A'", "B"]],
            },
        ]
        results = _validate_properties_sympy(props, sym_float)
        assert results[0]["passed"] is True
        assert results[1]["passed"] is True