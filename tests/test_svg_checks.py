"""
Unit tests for util/svg_checks.py.
No Docker or renderer required — uses static SVG strings.
"""

from geometry_diagrams.util.svg_checks import (
    check_svg_has_content,
    check_svg_reasonable_size,
    check_svg_wellformed,
    run_svg_checks,
)

# ---------------------------------------------------------------------------
# Minimal SVG fixtures
# ---------------------------------------------------------------------------

VALID_SVG_WITH_PATH = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="M 0 0 L 50 0 L 25 43 Z" stroke="black" fill="none"/>
</svg>"""

VALID_SVG_WITH_CIRCLE = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="30" stroke="black" fill="none"/>
</svg>"""

VALID_SVG_WITH_LINE = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <line x1="0" y1="0" x2="100" y2="100" stroke="black"/>
</svg>"""

EMPTY_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
</svg>"""

SVG_WITH_EMPTY_PATH = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <path d="" stroke="black"/>
</svg>"""

MALFORMED_XML = "<svg viewBox='0 0 100 100'><path d='M 0 0"

SVG_NO_VIEWBOX = """\
<svg xmlns="http://www.w3.org/2000/svg">
  <path d="M 0 0 L 50 50" stroke="black"/>
</svg>"""

SVG_ZERO_VIEWBOX = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 0">
  <path d="M 0 0 L 1 1" stroke="black"/>
</svg>"""

SVG_HUGE_VIEWBOX = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 999999 999999">
  <path d="M 0 0 L 1 1" stroke="black"/>
</svg>"""

SVG_WRONG_ROOT = """\
<html><body>hello</body></html>"""


# ---------------------------------------------------------------------------
# check_svg_wellformed
# ---------------------------------------------------------------------------

def test_wellformed_valid_svg_passes():
    assert check_svg_wellformed(VALID_SVG_WITH_PATH) is None


def test_wellformed_malformed_xml_fails():
    result = check_svg_wellformed(MALFORMED_XML)
    assert result is not None
    assert "XML" in result or "valid" in result.lower()


def test_wellformed_missing_viewbox_fails():
    result = check_svg_wellformed(SVG_NO_VIEWBOX)
    assert result is not None
    assert "viewBox" in result


def test_wellformed_wrong_root_fails():
    result = check_svg_wellformed(SVG_WRONG_ROOT)
    assert result is not None


# ---------------------------------------------------------------------------
# check_svg_has_content
# ---------------------------------------------------------------------------

def test_has_content_path_passes():
    assert check_svg_has_content(VALID_SVG_WITH_PATH) is None


def test_has_content_circle_passes():
    assert check_svg_has_content(VALID_SVG_WITH_CIRCLE) is None


def test_has_content_line_passes():
    assert check_svg_has_content(VALID_SVG_WITH_LINE) is None


def test_has_content_empty_svg_fails():
    result = check_svg_has_content(EMPTY_SVG)
    assert result is not None


def test_has_content_empty_path_fails():
    result = check_svg_has_content(SVG_WITH_EMPTY_PATH)
    assert result is not None


def test_has_content_malformed_xml_fails():
    result = check_svg_has_content(MALFORMED_XML)
    assert result is not None


# ---------------------------------------------------------------------------
# check_svg_reasonable_size
# ---------------------------------------------------------------------------

def test_reasonable_size_valid_passes():
    assert check_svg_reasonable_size(VALID_SVG_WITH_PATH) is None


def test_reasonable_size_zero_viewbox_fails():
    result = check_svg_reasonable_size(SVG_ZERO_VIEWBOX)
    assert result is not None
    assert "zero" in result.lower() or "negative" in result.lower()


def test_reasonable_size_huge_viewbox_fails():
    result = check_svg_reasonable_size(SVG_HUGE_VIEWBOX)
    assert result is not None
    assert "large" in result.lower() or "unreasonably" in result.lower()


def test_reasonable_size_no_viewbox():
    # No viewBox — should report format issue or return None (depends on implementation)
    # Here it should fail because no viewBox = unexpected format
    result = check_svg_reasonable_size(SVG_NO_VIEWBOX)
    assert result is not None


def test_reasonable_size_malformed_xml_fails():
    result = check_svg_reasonable_size(MALFORMED_XML)
    assert result is not None


# ---------------------------------------------------------------------------
# run_svg_checks
# ---------------------------------------------------------------------------

def test_run_all_checks_valid_svg_passes():
    failures = run_svg_checks(VALID_SVG_WITH_PATH)
    assert failures == []


def test_run_all_checks_empty_svg_has_failures():
    failures = run_svg_checks(EMPTY_SVG)
    assert len(failures) > 0


def test_run_all_checks_malformed_has_failures():
    failures = run_svg_checks(MALFORMED_XML)
    assert len(failures) > 0


def test_run_checks_custom_subset():
    failures = run_svg_checks(EMPTY_SVG, checks=[check_svg_wellformed])
    assert failures == []  # Well-formed, just empty


def test_run_all_checks_returns_list():
    result = run_svg_checks(VALID_SVG_WITH_PATH)
    assert isinstance(result, list)
