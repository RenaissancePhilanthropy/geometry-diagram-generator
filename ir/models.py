from pydantic import BaseModel


class Constructor(BaseModel):
    """A constructor or function call that creates a geometric object.

    Examples: Line(A, B), InteriorAngle(A, B, C), CircleR(center, radius)
    """
    name: str
    args: list[str]  # references to other named objects


class GeoObject(BaseModel):
    """A geometric object declaration.

    Bare declaration (no constructor): Point A
    Constructor declaration: Line L1 := Line(A, B)
    """
    type: str                          # e.g. "Point", "Line", "Angle"
    name: str                          # e.g. "A", "L1", "AEF"
    constructor: Constructor | None = None


class Predicate(BaseModel):
    """A predicate (constraint) applied to geometric objects.

    Examples: Parallel(L1, L2), SetX(A, -200), SetAngle(AEF, 0.75)
    """
    name: str
    args: list[str | float]  # object names or numeric values


class Diagram(BaseModel):
    """A complete geometry diagram in JSON IR form."""
    objects: list[GeoObject] = []
    predicates: list[Predicate] = []
    auto_label: list[str] = []
