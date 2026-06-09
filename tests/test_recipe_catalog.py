# tests/test_recipe_catalog.py
"""Tests for recipe catalog loader and prompt builders."""
import pytest
from pathlib import Path
from geometry_diagrams.recipe.catalog import (
    RecipeSummary, Recipe, RecipeSelection,
    load_catalog, load_recipe, build_selection_prompt, build_generation_prompt,
    clear_cache, DSL_DOCS,
)


@pytest.fixture(autouse=True)
def _reset_catalog_cache():
    clear_cache()
    yield
    clear_cache()


def test_load_catalog_returns_list():
    catalog = load_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) >= 1  # at least one recipe exists

def test_catalog_entries_have_required_fields():
    catalog = load_catalog()
    for entry in catalog:
        assert isinstance(entry, RecipeSummary)
        assert entry.id and isinstance(entry.id, str)
        assert entry.name and isinstance(entry.name, str)
        assert entry.description and isinstance(entry.description, str)
        assert isinstance(entry.tags, list)

def test_load_altitude_recipe():
    recipe = load_recipe("altitude")
    assert isinstance(recipe, Recipe)
    assert recipe.name == "altitude"
    assert recipe.context  # non-empty prose string
    assert recipe.example is not None
    assert isinstance(recipe.setup, list)
    # setup contains DSL ops with 'op' discriminator fields
    for op in recipe.setup:
        assert "op" in op  # setup entries are raw dicts

def test_recipe_example_has_construction():
    recipe = load_recipe("altitude")
    # example is a dict with construction list
    assert "construction" in recipe.example
    assert len(recipe.example["construction"]) >= 1

def test_recipe_setup_not_in_example():
    """setup ops should be separate from example — not duplicated."""
    recipe = load_recipe("altitude")
    setup_ids = {op.get("id") for op in recipe.setup}
    example_ids = {op.get("id") for op in recipe.example.get("construction", [])}
    # setup creates prerequisites; example creates the pattern being taught
    # There should be no overlap in ids
    assert setup_ids.isdisjoint(example_ids), (
        f"setup and example share IDs: {setup_ids & example_ids}"
    )


@pytest.mark.parametrize("recipe_id", [e.id for e in load_catalog()])
def test_setup_and_example_ids_disjoint_all_recipes(recipe_id):
    """setup and example IDs must be disjoint for every recipe."""
    recipe = load_recipe(recipe_id)
    setup_ids = {op.get("id") for op in recipe.setup}
    example_ids = {op.get("id") for op in recipe.example.get("construction", [])}
    assert setup_ids.isdisjoint(example_ids), (
        f"{recipe_id}: setup and example share IDs: {setup_ids & example_ids}"
    )

def test_load_nonexistent_recipe_raises():
    with pytest.raises(KeyError):
        load_recipe("does_not_exist")

def test_build_selection_prompt():
    catalog = load_catalog()
    prompt = build_selection_prompt("Draw a triangle with its altitude", catalog)
    assert isinstance(prompt, str)
    assert len(prompt) > 50
    # Should mention "altitude" since it's in the catalog
    assert "altitude" in prompt.lower()

def test_build_generation_prompt():
    recipe = load_recipe("altitude")
    prompt = build_generation_prompt(
        user_request="Draw triangle ABC with altitude from A",
        recipes=[recipe],
        dsl_docs=DSL_DOCS,
    )
    assert isinstance(prompt, str)
    assert "altitude" in prompt.lower()
    # The setup ops should NOT appear in the generation prompt
    # (setup is for tests only, not for the LLM)
    assert "setup" not in prompt.lower() or "example" in prompt.lower()

def test_generation_prompt_no_recipes():
    prompt = build_generation_prompt(
        user_request="Draw a square",
        recipes=[],
        dsl_docs=DSL_DOCS,
    )
    assert isinstance(prompt, str)
    assert "square" in prompt.lower()

def test_dsl_docs_is_nonempty_string():
    assert isinstance(DSL_DOCS, str)
    assert len(DSL_DOCS) > 100

def test_all_recipes_loadable():
    """All recipe files in the catalog must be loadable without error."""
    catalog = load_catalog()
    for entry in catalog:
        recipe = load_recipe(entry.id)
        assert recipe.name == entry.id


# ---------------------------------------------------------------------------
# Multi-catalog tests
# ---------------------------------------------------------------------------

def test_load_catalog_explicit_default():
    """Explicit catalog='default' returns same result as no argument."""
    assert load_catalog() == load_catalog(catalog="default")


def test_load_recipe_explicit_default():
    """Explicit catalog='default' returns same recipe as no argument."""
    assert load_recipe("altitude") == load_recipe("altitude", catalog="default")


def test_load_catalog_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        load_catalog("nonexistent_catalog_xyz")


def test_load_recipe_nonexistent_catalog_raises():
    with pytest.raises(FileNotFoundError):
        load_recipe("altitude", catalog="nonexistent_catalog_xyz")


def test_catalog_path_traversal_rejected():
    """Catalog names with path traversal components must be rejected."""
    with pytest.raises((ValueError, FileNotFoundError)):
        load_catalog("../recipes")


def test_catalog_cache_is_independent(tmp_path, monkeypatch):
    """Two catalogs load independently; each has only its own recipes."""
    import geometry_diagrams.recipe.catalog as cat_module

    # Build two minimal catalogs in a tmp directory
    cat_a = tmp_path / "alpha"
    cat_b = tmp_path / "beta"
    cat_a.mkdir()
    cat_b.mkdir()

    recipe_yaml = """\
name: dummy_{name}
description: A dummy recipe for {name}
tags: [test]
context: Context for {name}
setup: []
example:
  construction:
    - op: point
      id: P_{name}
      coords: [0, 0]
notes: []
"""
    (cat_a / "dummy_alpha.yaml").write_text(recipe_yaml.format(name="alpha"))
    (cat_b / "dummy_beta.yaml").write_text(recipe_yaml.format(name="beta"))

    monkeypatch.setattr(cat_module, "_RECIPES_BASE", tmp_path)
    clear_cache()

    alpha_catalog = load_catalog("alpha")
    beta_catalog = load_catalog("beta")

    assert len(alpha_catalog) == 1
    assert alpha_catalog[0].id == "dummy_alpha"
    assert len(beta_catalog) == 1
    assert beta_catalog[0].id == "dummy_beta"
