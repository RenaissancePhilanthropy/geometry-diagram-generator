"""F3 (strict prime matching on SVG labels) and F4 (errored checks fail the gate)."""
from evals.run import (
    _finalize_gate_status,
    _svg_forbidden_label_checks,
    _svg_label_matches,
    _svg_required_label_checks,
)
from geometry_diagrams.util.tikz_extraction import point_names_match


def _svg_with_labels(*texts: str) -> str:
    els = "".join(f'<text data-label-text="{t}">{t}</text>' for t in texts)
    return f'<svg xmlns="http://www.w3.org/2000/svg">{els}</svg>'


def test_prime_label_accepts_unambiguous_spellings():
    for ok in ("A'", "Aprime", "A_prime"):
        assert _svg_label_matches(ok, "A'"), ok
    assert _svg_label_matches("B''", "B''")
    assert _svg_label_matches("Bprimeprime", "B''")


def test_prime_label_rejects_other_points():
    for other in ("A1", "Ap", "Ad", "A2", "A"):
        assert not _svg_label_matches(other, "A'"), other
    assert not _svg_label_matches("B1", "B''")
    assert not _svg_label_matches("Bdd", "B''")


def test_required_labels_on_svg_use_strict_prime_matching():
    svg = _svg_with_labels("A", "A1")
    res = _svg_required_label_checks(svg, ["A'"])
    assert res == {"passed": False, "missing": ["A'"]}
    assert _svg_required_label_checks(_svg_with_labels("A'"), ["A'"])["passed"] is True


def test_forbidden_label_whole_token_behaviour_kept():
    svg = _svg_with_labels("V = 24")
    assert _svg_forbidden_label_checks(svg, ["24"])["found"] == ["24"]
    assert _svg_forbidden_label_checks(_svg_with_labels("V = 240"), ["24"])["passed"] is True


def test_tikz_path_keeps_lenient_matching():
    assert point_names_match("A'", "Ap")
    assert point_names_match("A'", "A1")
    assert not point_names_match("A'", "Ap", strict=True)


def _record(checks):
    return {
        "generation_success": True,
        "svg_rendered": True,
        "tikz_code": "x",
        "tikz_checks": checks,
    }


def test_errored_check_is_a_gate_failure():
    rec = _record({"p1": {"passed": None, "skipped": True, "error": "boom", "type": "t"}})
    _finalize_gate_status(rec)
    assert rec["gate_status"] == "fail"
    assert "p1:error" in rec["gate_failures"]


def test_deliberate_skip_still_soft_passes():
    rec = _record({"p1": {"passed": None, "skipped": True, "type": "t"}})
    _finalize_gate_status(rec)
    assert rec["gate_status"] == "soft_pass"
    assert rec["gate_failures"] == []


def test_passed_check_with_stale_error_key_is_not_a_failure():
    rec = _record({"p1": {"passed": True, "error": None}})
    _finalize_gate_status(rec)
    assert rec["gate_status"] == "pass"
