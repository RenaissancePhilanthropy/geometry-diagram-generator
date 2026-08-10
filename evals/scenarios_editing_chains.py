"""Chain-scenario YAML loading and validation for the pydsl edit-chain
reliability eval (evals/run_edit_chains.py). Deliberately a separate
schema/validator from evals/scenarios.py's single-shot scenarios — a chain
is a list of turns, not one prompt, and reusing the flat schema would
overload a field that means one thing everywhere else in the codebase."""
from __future__ import annotations

from typing import Any


def _validate_chain_scenarios(raw_scenarios: Any) -> list[dict[str, Any]]:
    """Validate chain-scenario YAML shape and return a normalized list.

    Each chain is {"id": str, "turns": [turn, ...]}, where each turn is
    {"request": str, "expected_properties": list[dict]} (empty list if
    omitted). At least one turn across the whole chain must define a
    non-empty expected_properties — the "floor" sanity check that catches
    "the chain technically succeeded at every turn but produced garbage"
    (see design doc, Component A).
    """
    if not isinstance(raw_scenarios, list):
        raise ValueError("Chain scenario file must be a YAML list of chain objects")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, raw in enumerate(raw_scenarios, start=1):
        where = f"chain scenario #{idx}"
        if not isinstance(raw, dict):
            raise ValueError(f"{where}: expected mapping/object, got {type(raw).__name__}")

        chain_id = raw.get("id")
        if not isinstance(chain_id, str) or not chain_id.strip():
            raise ValueError(f"{where}: 'id' must be a non-empty string")
        if chain_id in seen_ids:
            raise ValueError(f"{where}: duplicate id '{chain_id}'")
        seen_ids.add(chain_id)

        raw_turns = raw.get("turns")
        if not isinstance(raw_turns, list) or not raw_turns:
            raise ValueError(f"{where} ({chain_id}): 'turns' must be a non-empty list")

        turns: list[dict[str, Any]] = []
        has_any_properties = False
        for turn_idx, raw_turn in enumerate(raw_turns, start=1):
            turn_where = f"{where} ({chain_id}), turn #{turn_idx}"
            if not isinstance(raw_turn, dict):
                raise ValueError(f"{turn_where}: expected mapping/object, got {type(raw_turn).__name__}")
            request = raw_turn.get("request")
            if not isinstance(request, str) or not request.strip():
                raise ValueError(f"{turn_where}: 'request' must be a non-empty string")
            expected_properties = raw_turn.get("expected_properties", [])
            if not isinstance(expected_properties, list):
                raise ValueError(f"{turn_where}: 'expected_properties' must be a list if present")
            if expected_properties:
                has_any_properties = True
            turns.append({"request": request, "expected_properties": expected_properties})

        if not has_any_properties:
            raise ValueError(
                f"{where} ({chain_id}): at least one turn must define 'expected_properties' "
                "— every chain needs a floor sanity check (see design doc, Component A)"
            )

        normalized.append({"id": chain_id, "turns": turns})

    return normalized
