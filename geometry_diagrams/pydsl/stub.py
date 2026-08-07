"""Generates LLM-readable signature+docstring text from the pydsl public API.

Single source of truth: change a function's signature or docstring and the
prompt text regenerates automatically. Not a strictly importable .pyi file —
just readable stub text for prompt assembly.
"""
from __future__ import annotations

import inspect

import geometry_diagrams.pydsl as pydsl_module

_HANDLE_CLASS_NAMES = {"Point", "Line", "Ray", "Arc", "Sector", "Segment", "Triangle", "Polygon",
                        "Circle", "Ellipse", "Altitude", "Median", "AngleRef", "PerpendicularBisectorLine"}


def _format_callable(name: str, obj) -> str:
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        sig = "(...)"
    doc = inspect.getdoc(obj) or ""
    first_line = doc.splitlines()[0] if doc else ""
    line = f"def {name}{sig}"
    return f"{line}  # {first_line}" if first_line else line


def generate_stub() -> str:
    import dataclasses

    lines: list[str] = []
    for name in pydsl_module.__all__:
        obj = getattr(pydsl_module, name)
        if inspect.isfunction(obj):
            lines.append(_format_callable(name, obj))
        elif inspect.isclass(obj) and name in _HANDLE_CLASS_NAMES:
            lines.append(f"class {name}:")
            # Dataclass fields first — these are the accessors the design
            # doc's handle pattern depends on (circ.center, alt.foot, ...).
            # A stub that only lists methods would silently omit the reason
            # this handle design exists at all: the model must be able to
            # see these fields without ever assigning them an id itself.
            if dataclasses.is_dataclass(obj):
                for field in dataclasses.fields(obj):
                    if field.name.startswith("_"):
                        continue  # e.g. Triangle/Polygon's internal _builder reference
                    type_name = getattr(field.type, "__name__", str(field.type))
                    lines.append(f"    {field.name}: {type_name}")
            # Computed accessors exposed as properties (e.g. Circle.radius,
            # Point.x/.y) are just as much a part of the handle surface as
            # dataclass fields — the model must see these too, with their
            # return type and docstring, not a bare "name: property" (which
            # would silently drop e.g. Point.x's "raises for a constructed
            # point" contract — exactly the behavior a model needs to know
            # about to use it correctly).
            for prop_name, prop in inspect.getmembers(obj, predicate=lambda m: isinstance(m, property)):
                if prop_name.startswith("_"):
                    continue
                getter = prop.fget
                try:
                    return_type = inspect.signature(getter).return_annotation
                    type_name = "" if return_type is inspect.Signature.empty else \
                        getattr(return_type, "__name__", str(return_type))
                except (TypeError, ValueError):
                    type_name = ""
                doc = inspect.getdoc(getter) or ""
                first_line = doc.splitlines()[0] if doc else ""
                line = f"    {prop_name}: {type_name}" if type_name else f"    {prop_name}: property"
                lines.append(f"{line}  # {first_line}" if first_line else line)
            for method_name, method in inspect.getmembers(obj, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                lines.append("    " + _format_callable(method_name, method))
    return "\n".join(lines)
