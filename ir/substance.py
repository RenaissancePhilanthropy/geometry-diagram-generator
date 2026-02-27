from collections import defaultdict

from .emitter import DiagramLike, SubstanceEmitter
from .models import StringLiteral


def _fmt_arg(arg: str | float | StringLiteral) -> str:
    """Format a predicate argument.

    str           → unquoted object reference: L1
    float         → integer when whole (-200), decimal otherwise (0.75)
    StringLiteral → double-quoted string: "horizontal"
    """
    if isinstance(arg, StringLiteral):
        return f'"{arg.value}"'
    if isinstance(arg, float) and arg == int(arg):
        return str(int(arg))
    return str(arg)


class PenroseEmitter(SubstanceEmitter):
    """Emits standard Penrose substance code from any DiagramLike.

    Performs four passes in order:
    1. Bare declarations grouped by type:   Point A, B, C
    2. Constructor declarations:            Line L1 := Line(A, B)
    3. Predicates:                          Parallel(L1, L2)
    4. AutoLabel all points:               AutoLabel A, B, C
    """

    def emit(self, diagram: DiagramLike) -> str:
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

        # Pass 3: predicates.
        for pred in diagram.predicates:
            args_str = ", ".join(_fmt_arg(a) for a in pred.args)
            lines.append(f"{pred.name}({args_str})")

        # Pass 4: AutoLabel all points.
        point_names = [obj.name for obj in diagram.objects if obj.type == "Point"]
        if point_names:
            lines.append(f"AutoLabel {', '.join(point_names)}")

        return "\n".join(lines)


def to_substance(diagram: DiagramLike) -> str:
    """Convert a Diagram (or any DiagramLike) to a Penrose substance string."""
    return PenroseEmitter().emit(diagram)
