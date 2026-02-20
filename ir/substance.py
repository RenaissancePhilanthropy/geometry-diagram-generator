from collections import defaultdict

from .models import Diagram


def _fmt_arg(arg: str | float) -> str:
    """Format a predicate argument. Whole-number floats render without decimal."""
    if isinstance(arg, float) and arg == int(arg):
        return str(int(arg))
    return str(arg)


def to_substance(diagram: Diagram) -> str:
    """Convert a Diagram to a Penrose substance string."""
    lines: list[str] = []

    # Pass 1: bare declarations grouped by type, preserving insertion order.
    bare_by_type: dict[str, list[str]] = defaultdict(list)
    for obj in diagram.objects:
        if obj.constructor is None:
            bare_by_type[obj.type].append(obj.name)

    for type_name, names in bare_by_type.items():
        lines.append(f"{type_name} {', '.join(names)}")

    # Pass 2: constructor / function declarations.
    for obj in diagram.objects:
        if obj.constructor is not None:
            args_str = ", ".join(obj.constructor.args)
            lines.append(f"{obj.type} {obj.name} := {obj.constructor.name}({args_str})")

    # Predicates.
    for pred in diagram.predicates:
        args_str = ", ".join(_fmt_arg(a) for a in pred.args)
        lines.append(f"{pred.name}({args_str})")

    # AutoLabel.
    if diagram.auto_label:
        lines.append(f"AutoLabel {', '.join(diagram.auto_label)}")

    return "\n".join(lines)
