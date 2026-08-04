# geometry_diagrams/pydsl/handles.py
"""Thin typed handles returned by pydsl API functions.

A handle wraps an internal id (auto-generated or model-supplied for
identity-carrying points) and never requires the model to re-derive
geometric parts from raw point references — see Triangle/Polygon for the
accessor pattern that replaces the DSL's string-id threading.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    id: str


@dataclass(frozen=True)
class Line:
    id: str


@dataclass(frozen=True)
class Segment:
    id: str
