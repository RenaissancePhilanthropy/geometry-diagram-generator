import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, create_model, model_validator

from .models import StringLiteral


@dataclass
class DomainInfo:
    """Parsed information from a Penrose domain file."""
    types: set[str] = field(default_factory=set)
    type_parents: dict[str, str] = field(default_factory=dict)   # child → parent
    constructors: dict[str, list[str]] = field(default_factory=dict)  # name → [param types]
    predicates: dict[str, list[str]] = field(default_factory=dict)   # name → [param types]


# ─────────────────────────────────────── Parsing ───────────────────────────────────────

_COMMENT_RE = re.compile(r'--[^\n]*')
_TYPE_RE = re.compile(r'^type\s+(\w+)(?:\s*<:\s*(\w+))?', re.MULTILINE)
_CTOR_RE = re.compile(r'^constructor\s+(\w+)\s*\(([^)]*)\)', re.MULTILINE)
_FUNC_RE = re.compile(r'^function\s+(\w+)\s*\(([^)]*)\)', re.MULTILINE)
_PRED_RE = re.compile(r'^(symmetric\s+)?predicate\s+(\w+)\s*\(([^)]*)\)', re.MULTILINE)


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub('', text)


def _parse_param_types(params_str: str) -> list[str]:
    """Parse 'Point p, Point q' or 'Point, Linelike' into ['Point', 'Linelike']."""
    params_str = params_str.strip()
    if not params_str:
        return []
    result = []
    for param in params_str.split(','):
        param = param.strip()
        if not param:
            continue
        result.append(param.split()[0])  # first token is always the type
    return result


def parse_domain(text: str) -> DomainInfo:
    """Parse a Penrose domain file and return structured DomainInfo."""
    clean = _strip_comments(text)
    info = DomainInfo()

    for m in _TYPE_RE.finditer(clean):
        info.types.add(m.group(1))
        if m.group(2):
            info.type_parents[m.group(1)] = m.group(2)

    for m in _CTOR_RE.finditer(clean):
        info.constructors[m.group(1)] = _parse_param_types(m.group(2))

    # Functions are treated identically to constructors in the IR
    for m in _FUNC_RE.finditer(clean):
        info.constructors[m.group(1)] = _parse_param_types(m.group(2))

    for m in _PRED_RE.finditer(clean):
        info.predicates[m.group(2)] = _parse_param_types(m.group(3))

    return info


# ─────────────────────────────────────── Type hierarchy ────────────────────────────────

def is_subtype(actual: str, expected: str, parents: dict[str, str]) -> bool:
    """Return True if actual is the same type as or a subtype of expected."""
    current: str | None = actual
    while current is not None:
        if current == expected:
            return True
        current = parents.get(current)
    return False


# ─────────────────────────────────────── Semantic validation ───────────────────────────

def _validate_semantics(diagram, info: DomainInfo) -> None:
    """Validate arg counts and type compatibility across the whole diagram."""
    obj_types: dict[str, str] = {obj.name: obj.type for obj in diagram.objects}

    # Duplicate object names
    seen: dict[str, int] = {}
    for i, obj in enumerate(diagram.objects):
        if obj.name in seen:
            raise ValueError(
                f"Duplicate object name '{obj.name}' (objects[{seen[obj.name]}] and objects[{i}])"
            )
        seen[obj.name] = i

    # Undeclared refs in constructors
    for obj in diagram.objects:
        if obj.constructor:
            for arg in obj.constructor.args:
                if arg not in obj_types:
                    raise ValueError(
                        f"Constructor {obj.constructor.name} references undeclared object '{arg}'"
                    )

    # Coerce plain strings to StringLiteral for String-typed predicate params so
    # the emitter renders them quoted and the undeclared-ref check below ignores them.
    for pred in diagram.predicates:
        params = info.predicates.get(pred.name, [])
        for i, arg in enumerate(pred.args):
            if isinstance(arg, str) and i < len(params) and params[i] == 'String':
                pred.args[i] = StringLiteral(value=arg)

    # Undeclared refs in predicates
    for pred in diagram.predicates:
        for arg in pred.args:
            if isinstance(arg, str) and arg not in obj_types:
                raise ValueError(
                    f"Predicate {pred.name} references undeclared object '{arg}'"
                )

    # Undeclared refs in auto_label
    for name in diagram.auto_label:
        if name not in obj_types:
            raise ValueError(f"auto_label references undeclared object '{name}'")

    def check_args(label: str, params: list[str], args: list) -> None:
        if len(args) != len(params):
            raise ValueError(
                f"{label} expects {len(params)} argument(s), got {len(args)}"
            )
        for i, (arg, expected) in enumerate(zip(args, params)):
            if isinstance(arg, StringLiteral):
                if expected != 'String':
                    raise ValueError(
                        f"{label} arg {i + 1}: expected {expected}, got String literal"
                    )
            elif isinstance(arg, float):
                if expected != 'Number':
                    raise ValueError(
                        f"{label} arg {i + 1}: expected {expected}, got Number"
                    )
            else:  # str — object reference, guaranteed declared by checks above
                if expected in ('Number', 'String'):
                    raise ValueError(
                        f"{label} arg {i + 1}: expected {expected}, got object reference '{arg}'"
                    )
                actual = obj_types[arg]
                if not is_subtype(actual, expected, info.type_parents):
                    raise ValueError(
                        f"{label} arg {i + 1}: expected {expected} (or subtype), got {actual}"
                    )

    for obj in diagram.objects:
        if obj.constructor is not None:
            params = info.constructors.get(obj.constructor.name, [])
            check_args(f"Constructor {obj.constructor.name}", params, obj.constructor.args)

    for pred in diagram.predicates:
        params = info.predicates.get(pred.name, [])
        check_args(f"Predicate {pred.name}", params, pred.args)


# ─────────────────────────────────────── Model factory ─────────────────────────────────

def build_diagram_model(domain_info: DomainInfo) -> type:
    """Return a domain-constrained Diagram model built from DomainInfo.

    Fields that accept names (type, constructor name, predicate name) are
    restricted to Literal unions of valid domain values.  A cross-field
    model_validator enforces argument counts and type-hierarchy compatibility.
    """
    valid_types = tuple(sorted(domain_info.types))
    valid_ctors = tuple(sorted(domain_info.constructors))
    valid_preds = tuple(sorted(domain_info.predicates))

    if not valid_types:
        raise ValueError("Domain has no types")
    if not valid_ctors:
        raise ValueError("Domain has no constructors or functions")
    if not valid_preds:
        raise ValueError("Domain has no predicates")

    # Literal[tuple] is equivalent to Literal[t[0], t[1], ...] at runtime
    ValidType = Literal[valid_types]
    ValidCtorName = Literal[valid_ctors]
    ValidPredName = Literal[valid_preds]

    _Constructor = create_model(
        'Constructor',
        name=(ValidCtorName, ...),
        args=(list[str], ...),
    )

    _GeoObject = create_model(
        'GeoObject',
        type=(ValidType, ...),
        name=(str, ...),
        constructor=(_Constructor | None, None),
    )

    _Predicate = create_model(
        'Predicate',
        name=(ValidPredName, ...),
        args=(list[str | float | StringLiteral], ...),
    )

    _di = domain_info  # captured for the validator closure

    class _DiagramBase(BaseModel):
        @model_validator(mode='after')
        def _cross_validate(self):
            _validate_semantics(self, _di)
            return self

    DomainDiagram = create_model(
        'Diagram',
        __base__=_DiagramBase,
        objects=(list[_GeoObject], Field(default_factory=list)),
        predicates=(list[_Predicate], Field(default_factory=list)),
        auto_label=(list[str], Field(default_factory=list)),
    )

    return DomainDiagram
