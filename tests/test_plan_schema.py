"""Tests for ir/plan.py — ConstructionPlan schema."""
from ir.plan import ConstructionPlan, ConstructionStep


def test_construction_plan_roundtrip():
    plan = ConstructionPlan(
        steps=[
            ConstructionStep(
                description="Place triangle ABC",
                entities_produced=["A", "B", "C", "T"],
                depends_on=[],
            ),
            ConstructionStep(
                description="Find circumcenter O",
                entities_produced=["O"],
                depends_on=["T"],
            ),
        ],
        geometric_checks=["O is equidistant from A, B, C"],
    )
    data = plan.model_dump()
    plan2 = ConstructionPlan.model_validate(data)
    assert plan2.steps[0].description == plan.steps[0].description
    assert plan2.geometric_checks == ["O is equidistant from A, B, C"]
