# geometry_diagrams/pydsl/handles.py
"""Thin typed handles returned by pydsl API functions.

A handle wraps an internal id (auto-generated or model-supplied for
identity-carrying points) and never requires the model to re-derive
geometric parts from raw point references — see Triangle/Polygon for the
accessor pattern that replaces the DSL's string-id threading.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    id: str


@dataclass(frozen=True)
class Line:
    id: str


@dataclass(frozen=True)
class Segment:
    id: str


@dataclass(frozen=True)
class Triangle:
    id: str
    vertices: tuple[Point, Point, Point]
    _builder: "object" = field(repr=False, compare=False)  # type is Builder; avoid a
                                                             # circular import at module load

    def side(self, p: Point, q: Point) -> "Segment":
        vertex_ids = {v.id for v in self.vertices}
        for name, pt in (("p", p), ("q", q)):
            if pt.id not in vertex_ids:
                raise ValueError(f"{pt.id!r} is not a vertex of triangle {self.id!r} ({name})")
        return self._builder._get_or_create_segment(p.id, q.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        vertex_ids = [vert.id for vert in self.vertices]
        if v.id not in vertex_ids:
            raise ValueError(f"{v.id!r} is not a vertex of triangle {self.id!r}")
        others = [pid for pid in vertex_ids if pid != v.id]
        return AngleRef(a=Point(id=others[0]), o=v, b=Point(id=others[1]))


@dataclass(frozen=True)
class Polygon:
    id: str
    vertices: tuple[Point, ...]
    _builder: "object" = field(repr=False, compare=False)

    def side(self, v1: Point, v2: Point) -> "Segment":
        ids = [v.id for v in self.vertices]
        for name, pt in (("v1", v1), ("v2", v2)):
            if pt.id not in ids:
                raise ValueError(f"{pt.id!r} is not a vertex of polygon {self.id!r} ({name})")
        i1, i2 = ids.index(v1.id), ids.index(v2.id)
        n = len(ids)
        if abs(i1 - i2) % n not in (1, n - 1):
            raise ValueError(
                f"{v1.id!r} and {v2.id!r} are not adjacent vertices of polygon {self.id!r}"
            )
        return self._builder._get_or_create_segment(v1.id, v2.id)

    def angle_at(self, v: Point) -> "AngleRef":
        from geometry_diagrams.pydsl.handles import AngleRef  # Task 7

        ids = [vert.id for vert in self.vertices]
        if v.id not in ids:
            raise ValueError(f"{v.id!r} is not a vertex of polygon {self.id!r}")
        n = len(ids)
        i = ids.index(v.id)
        prev_id, next_id = ids[(i - 1) % n], ids[(i + 1) % n]
        return AngleRef(a=Point(id=prev_id), o=v, b=Point(id=next_id))
