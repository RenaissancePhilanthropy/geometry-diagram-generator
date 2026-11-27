"""Resolve the point names a scenario's expected_properties use to the ids of the
compiled figure.

A scenario says "A", "B", "C" (what the prompt asked the model to draw), but the
checks look points up by definition id: recipe and structured authors choose ids
(a point labelled ``P`` may have id ``Pp``) and python_full's are opaque
(``__pydsl_pt_N``). A name resolves, in order, by

1. an id of the figure exactly, unless the reader sees something else: another
   point labelled with that name makes it ``ambiguous`` (the label is what the
   reader sees, the id is the model's private choice), and an id whose own label
   shows another text is not a match at all;
2. the text of the one point label that shows it (``LabelPoint.text``; prime
   spellings the label strictness allows, ``$`` math delimiters ignored);
3. an id spelling a primed name another way: the strict spellings (``A'``,
   ``Aprime``, ``A_prime``) first, then the loose ones the TikZ checks accept
   (``Ap``, ``A1``), which skip a point whose own label says it is something
   else (``P1`` labelled ``P_1`` is not ``P'``; a label with no text shows the id,
   so an auto-labelled ``A1`` is ``A1``); several ids are ``ambiguous``;
4. the script's own variable name (python_full's ``variable_ids``).

A name no step finds is ``unresolved``; one a step finds on several points is
``ambiguous``; so are two different names of one property that resolve to the
same point (a check on "A" and "B" that is really one point passes trivially).
All are reported apart from a geometry failure.
"""
from __future__ import annotations

from typing import Any

from geometry_diagrams.ir.point_labels import labeled_point_ids
from geometry_diagrams.util.tikz_extraction import point_names_match


class NameResolutionError(ValueError):
    """A scenario point name that does not identify exactly one point. ``kind`` is
    ``"unresolved"`` or ``"ambiguous"``."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# What a model writes for a prime, each as the ASCII prime(s) it stands for: the prime, double
# and triple prime signs (``G\u2033`` is ``G''``), the typographic quotes, the modifier letter
# prime and the acute accent that some fonts and models substitute.
PRIME_SPELLINGS = str.maketrans({
    0x2032: "'", 0x2033: "''", 0x2034: "'''", 0x2019: "'", 0x2018: "'", 0x02B9: "'", 0x00B4: "'",
})


def _bare(text: str) -> str:
    """A label text or name without math delimiters, braces and spaces, one prime
    spelling (``A\u2032`` is ``A'``, ``G\u2033`` is ``G''``, ``A_{1}`` is ``A_1``)."""
    text = text.translate(PRIME_SPELLINGS).replace("{", "").replace("}", "")
    return "".join(text.replace("$", " ").split())


class NameResolver:
    """Maps scenario point names to ids of ``points`` (the float symbol table)."""

    def __init__(self, points: dict, diagram_ir: Any = None, variable_ids: dict | None = None):
        self._points = points
        self._variable_ids = variable_ids or {}
        self._labels: dict[str, set[str]] = {}  # bare label text -> point ids
        self._own: dict[str, set[str]] = {}     # point id -> bare texts of its labels
        if diagram_ir is not None:
            for text, ids in labeled_point_ids(diagram_ir, untexted_show_id=True).items():
                for pid in ids:
                    if pid in points:
                        self._labels.setdefault(_bare(text), set()).add(pid)
                        self._own.setdefault(pid, set()).add(_bare(text))
        self.resolved: dict[str, str] = {}  # names that needed resolving -> id, for the record

    def resolve(self, name: str) -> str:
        labelled = self._by_label(name)
        if name in self._points:
            if labelled and labelled != {name}:
                raise NameResolutionError(
                    "ambiguous",
                    f"{name!r} is a point id and also the label of {', '.join(sorted(labelled - {name}))}",
                )
            own = self._own.get(name)
            if not own or any(self._label_shows(t, name) for t in own):
                return name
            labelled = None  # the point carries another label: the reader does not see this name
        found = labelled or self._by_prime_id(name, skip=name)
        if not found:
            vid = self._variable_ids.get(name)
            found = {vid} if isinstance(vid, str) and vid in self._points else None
        if not found:
            raise NameResolutionError("unresolved", f"no point named {name!r} in the figure")
        if len(found) > 1:
            raise NameResolutionError(
                "ambiguous", f"{name!r} names several points ({', '.join(sorted(found))})"
            )
        (point_id,) = found
        self.resolved[name] = point_id
        return point_id

    def _label_shows(self, text: str, name: str) -> bool:
        return text == _bare(name) or point_names_match(_bare(name), text, strict=True) \
            or point_names_match(text, _bare(name), strict=True)

    def _by_label(self, name: str) -> set[str] | None:
        bare = _bare(name)
        if bare in self._labels:
            return set(self._labels[bare])
        loose: set[str] = set()
        for text, ids in self._labels.items():
            if self._label_shows(text, name):
                loose |= ids
        return loose or None

    def _by_prime_id(self, name: str, skip: str | None = None) -> set[str] | None:
        strict = {
            pid for pid in self._points if pid != skip and point_names_match(name, pid, strict=True)
        }
        if strict:
            return strict
        # A loose spelling (Ap, A1) is plausibly another point: not when the point's own
        # label says what it is.
        return {
            pid for pid in self._points
            if pid != skip and point_names_match(name, pid)
            and not (self._own.get(pid) and not any(self._label_shows(t, name) for t in self._own[pid]))
        } or None

    def resolve_args(self, args: Any) -> Any:
        """``args`` with every string (a point name) resolved, recursing into nested
        lists; numbers and other values (an expected length or angle) are kept."""
        seen: dict[str, str] = {}  # resolved id -> the first name that gave it

        def walk(a: Any) -> Any:
            if isinstance(a, str):
                point_id = self.resolve(a)
                other = seen.setdefault(point_id, a)
                if other != a:
                    raise NameResolutionError(
                        "ambiguous", f"{other!r} and {a!r} are the same point ({point_id})"
                    )
                return point_id
            if isinstance(a, list):
                return [walk(x) for x in a]
            return a

        return walk(args)
