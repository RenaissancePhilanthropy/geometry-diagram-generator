"""Registry position hook: a registered, non-SymPy object supplies its own
position to the centroid computation and the entity manifest."""
from types import SimpleNamespace

from geometry_diagrams.ir import ir
from geometry_diagrams.ir.derived import REGISTRY, DerivedConstruction
from geometry_diagrams.ir.render_util import build_entity_manifest, centroid_of_obj


class _FakeSolid:
    """Not a SymPy object and has no .vertices."""

    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


def _register_fake(monkeypatch) -> None:
    entry = DerivedConstruction(
        kind="test_fake_solid",
        id_forms=(),
        owned_ids=lambda stmt: [],
        register=lambda stmt, obj, sym: None,
        position=lambda obj: (obj.x, obj.y) if isinstance(obj, _FakeSolid) else None,
    )
    monkeypatch.setitem(REGISTRY._by_kind, "test_fake_solid", entry)


def test_centroid_of_registered_non_sympy_object_uses_its_position(monkeypatch):
    _register_fake(monkeypatch)
    assert centroid_of_obj(_FakeSolid(3.0, 4.5)) == (3.0, 4.5)


def test_entity_manifest_uses_registered_position(monkeypatch):
    _register_fake(monkeypatch)
    stmt = ir.PointFixed(id="S", x=0, y=0)
    diagram = SimpleNamespace(define=[stmt], render=[])
    manifest = build_entity_manifest(diagram, {"S": _FakeSolid(3.0, 4.5)}, {"solid": "S"})
    assert manifest["named"] == [
        {"name": "solid", "id": "S", "type": "point_fixed", "approx_position": [3.0, 4.5]}
    ]
