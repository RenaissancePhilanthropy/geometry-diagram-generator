"""solve_triangle verifies dropped/extra constraints; shipped recipes still lower."""
from __future__ import annotations

import pytest

from geometry_diagrams.ir.to_sympy import compile_defs
from geometry_diagrams.recipe.catalog import clear_cache, load_catalog, load_recipe
from geometry_diagrams.recipe.dsl import RecipeDSL
from geometry_diagrams.recipe.lower import lower_to_ir
from geometry_diagrams.recipe.solve import SpecError, solve_triangle

_ALL_CATALOGS = "default,curriculum,genexam"
_ABC = ["A", "B", "C"]


def test_sss_with_contradicting_angle_raises():
    spec = {"side_AB": 3, "side_BC": 4, "side_CA": 5, "angle_A": 10}
    with pytest.raises(SpecError, match="angle_A"):
        solve_triangle(_ABC, spec)


def test_sss_with_consistent_angle_accepted():
    spec = {"side_AB": 3, "side_BC": 4, "side_CA": 5, "angle_B": 90}
    assert solve_triangle(_ABC, spec)


def test_right_angle_with_contradicting_hypotenuse_raises():
    spec = {"right_angle_at": "A", "side_AB": 3, "side_CA": 4, "side_BC": 9}
    with pytest.raises(SpecError, match="side_BC"):
        solve_triangle(_ABC, spec)


def test_aas_with_contradicting_third_angle_raises():
    spec = {"angle_A": 40, "angle_B": 60, "angle_C": 80, "side_AB": 5}
    assert solve_triangle(_ABC, spec)  # consistent: 40+60+80
    with pytest.raises(SpecError):
        solve_triangle(_ABC, {"angle_A": 40, "angle_B": 60, "angle_C": 85, "side_AB": 5})


@pytest.fixture(autouse=True)
def _reset():
    clear_cache()
    yield
    clear_cache()


@pytest.mark.parametrize("recipe_id", [e.id for e in load_catalog(_ALL_CATALOGS)])
def test_every_shipped_recipe_lowers_and_compiles(recipe_id):
    recipe = load_recipe(recipe_id, catalog=_ALL_CATALOGS)
    example = dict(recipe.example)
    example["construction"] = list(recipe.setup) + list(example.get("construction", []))
    ir = lower_to_ir(RecipeDSL.model_validate(example))
    compile_defs(ir)
