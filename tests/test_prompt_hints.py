from __future__ import annotations

from strategies.prompt_hints import (
    augment_structured_prompt,
    build_structured_hint_text,
    detect_prompt_features,
    extract_explicit_point_coordinates,
)


def test_extract_explicit_point_coordinates_variants():
    prompt = "Plot A at (0,0), B at (4,0), and C = (0,3). Also show D(1.5,2)."
    coords = extract_explicit_point_coordinates(prompt)
    assert coords == {
        "A": (0.0, 0.0),
        "B": (4.0, 0.0),
        "C": (0.0, 3.0),
        "D": (1.5, 2.0),
    }


def test_detect_prompt_features_for_grid_and_incircle():
    features = detect_prompt_features(
        "On a coordinate grid with axes, draw an inscribed circle and its perpendicular bisector."
    )
    assert features["grid"] is True
    assert features["incircle"] is True
    assert features["perpendicular_bisector"] is True


def test_build_structured_hint_text_for_grid_prompt():
    prompt = "On a visible coordinate grid with axes, plot A at (0,0), B at (4,0), and C at (0,3)."
    hints = build_structured_hint_text(prompt)
    assert "canvas.grid = true" in hints
    assert "canvas.axes = true" in hints
    assert "canvas.show_tick_labels = true" in hints
    assert "Exact point: A = (0, 0)" in hints
    assert "LabelPoint.text" in hints


def test_build_structured_hint_text_for_incircle_and_perp_bisector():
    hints = build_structured_hint_text(
        "Draw a triangle ABC with its inscribed circle and the perpendicular bisector of AB."
    )
    assert "point_triangle_center" in hints
    assert "circle_center_point(center=I, through=Ta)" in hints
    assert "line_perp_through" in hints
    assert "contains(I, T)" in hints


def test_augment_structured_prompt_appends_hints():
    prompt = "Draw A(0,0), B(4,0), C(0,3) on a coordinate grid with axes."
    augmented = augment_structured_prompt(prompt)
    assert augmented.startswith(prompt)
    assert "Structured hints for this prompt:" in augmented


def test_extract_explicit_point_coordinates_no_coords():
    coords = extract_explicit_point_coordinates("Draw a right triangle.")
    assert coords == {}


def test_extract_explicit_point_coordinates_negative_values():
    coords = extract_explicit_point_coordinates("Plot A(-3, -2) and B(0, 4).")
    assert coords == {"A": (-3.0, -2.0), "B": (0.0, 4.0)}


def test_extract_explicit_point_coordinates_duplicate_name():
    # When a point name appears twice, the last occurrence wins.
    coords = extract_explicit_point_coordinates("A(1,0) ... A(2,0)")
    assert "A" in coords


def test_detect_prompt_features_plain_prompt_all_false():
    features = detect_prompt_features("Draw a right triangle.")
    assert features["grid"] is False
    assert features["incircle"] is False
    assert features["perpendicular_bisector"] is False
    assert features["midpoint"] is False
