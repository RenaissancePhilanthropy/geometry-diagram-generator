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


class StringLiteral(BaseModel):
    """A quoted string literal argument in a predicate.

    Distinct from a plain str, which is an object name reference.
    Example: Orientation(L1, "horizontal") → StringLiteral(value="horizontal")
    """
    value: str


class Predicate(BaseModel):
    """A predicate (constraint) applied to geometric objects.

    arg types:
      str           — object name reference, rendered unquoted: L1
      float         — numeric value, rendered as integer when whole: -200
      StringLiteral — quoted string literal: "horizontal"

    Examples:
      Parallel(L1, L2)               → args=["L1", "L2"]
      SetX(A, -200)                  → args=["A", -200.0]
      Orientation(L1, "horizontal")  → args=["L1", StringLiteral("horizontal")]
    """
    name: str
    args: list[str | float | StringLiteral]


class Diagram(BaseModel):
    """A complete geometry diagram in JSON IR form."""
    objects: list[GeoObject] = []
    predicates: list[Predicate] = []
