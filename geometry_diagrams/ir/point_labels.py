"""Which points a diagram labels with which text."""
from __future__ import annotations

from . import ir


def labeled_point_ids(diagram: "ir.DiagramIR", *, untexted_show_id: bool = False) -> dict[str, set[str]]:
    """Each explicit point-label text of ``diagram`` -> the ids of the points it labels
    (usually one; a text on several points is ambiguous). A label without text shows the
    point's own id: it adds nothing here unless ``untexted_show_id``, which lists the id
    as that label's text."""
    labeled: dict[str, set[str]] = {}
    for op in diagram.render:
        if isinstance(op, ir.LabelPoint) and (op.text or untexted_show_id):
            labeled.setdefault(op.text or op.p, set()).add(op.p)
    return labeled
