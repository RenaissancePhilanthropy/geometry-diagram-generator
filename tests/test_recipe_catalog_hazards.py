"""Catalog loader: duplicate names rejected, load_recipe returns isolated copies."""
from __future__ import annotations

import pytest

from geometry_diagrams.recipe import catalog
from geometry_diagrams.recipe.catalog import clear_cache, load_recipe


@pytest.fixture(autouse=True)
def _reset():
    clear_cache()
    yield
    clear_cache()


def test_load_recipe_returns_copy_not_cache_entry():
    first = load_recipe("altitude")
    first.setup.append({"id": "junk"})
    first.notes.append("corrupted")
    first.example["construction"] = []
    second = load_recipe("altitude")
    assert {"id": "junk"} not in second.setup
    assert "corrupted" not in second.notes
    assert second.example.get("construction")


def test_duplicate_recipe_name_in_catalog_raises(tmp_path, monkeypatch):
    body = (
        "name: dup\ndescription: d\ncontext: c\nexample:\n  construction: []\n"
    )
    (tmp_path / "dupcat").mkdir()
    (tmp_path / "dupcat" / "a.yaml").write_text(body)
    (tmp_path / "dupcat" / "b.yaml").write_text(body)
    monkeypatch.setattr(catalog, "_RECIPES_BASE", tmp_path)
    with pytest.raises(ValueError, match="Duplicate recipe name 'dup'"):
        catalog._load_all_recipes("dupcat")
