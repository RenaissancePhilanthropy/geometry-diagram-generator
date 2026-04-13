"""Generate student-style eval scenarios from the extracted curriculum.

Reads curriculum/geometry_curriculum.json (produced by extract_curriculum.py),
calls Claude to produce diagram request prompts per topic (batched), validates
output, and writes YAML files compatible with evals/run.py.

Usage:
    .venv/bin/python curriculum/generate_prompts.py
    .venv/bin/python curriculum/generate_prompts.py --dry-run
    .venv/bin/python curriculum/generate_prompts.py --grade geometry --volume 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from textwrap import dedent

import anthropic
import yaml
from dotenv import load_dotenv

load_dotenv()

CURRICULUM_DIR = Path(__file__).parent
REPO_ROOT = CURRICULUM_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from evals.scenarios import _validate_scenarios, _SUPPORTED_PROPERTY_TYPES

SUPPORTED_TYPES_STR = ", ".join(sorted(_SUPPORTED_PROPERTY_TYPES))

MODEL = "claude-sonnet-4-6"
MAX_WORKERS = 4

SYSTEM_PROMPT = dedent(f"""\
You are a geometry student who needs help visualizing concepts from your
textbook. For each lesson and activity listed below, write diagram requests
that a student might ask a diagram-generation tool to create.

Each request must be a JSON object:
- "id": kebab-case unique id (e.g. "geo-m1-t2-l3-parallel-lines-1")
- "tier": 1-3 (1=basic construction, 2=theorem/proof diagram, 3=multi-step)
- "tags": keyword list including "curriculum" and "grade-geometry"
- "prompt": a student-style diagram request. Be SPECIFIC about what to draw:
  name the points/vertices, state angle measures, side lengths, or
  relationships. Sound like a student asking for help, not textbook language.
  Example: "Draw triangle ABC where angle C is 90 degrees, side AC is 5 units,
  and side BC is 12 units. Label the hypotenuse and mark the right angle."
- "required_labels": list of point/vertex labels that MUST appear
- "expected_properties": list of verifiable geometric properties:
  - "name": descriptive snake_case (e.g. "right_angle_at_C")
  - "type": one of: {SUPPORTED_TYPES_STR}
  - "args": property-specific arguments

Property type reference:
- right_angle: [P1, vertex, P2] — angle at vertex is 90°
- midpoint: [M, A, B] — M is midpoint of AB
- collinear: [P1, P2, P3] — points are collinear
- equal_lengths: [[P1,P2], [P3,P4], ...] — segments are equal length
- parallel: [[P1,P2], [P3,P4]] — lines are parallel
- perpendicular: [[P1,P2], [P3,P4]] — lines are perpendicular
- point_on_line: [P, A, B] — P lies on line AB
- point_on_segment: [P, A, B] — P lies on segment AB
- point_on_circle: [P, center, radius_point] — P on circle
- tangent: [[P1,P2], center, tangent_point] — line tangent to circle
- angle_equal: [[P1,V1,P2], [P3,V2,P4]] — angles are equal
- angle_bisector: [D, vertex, P1, P2] — ray bisects angle
- mark_present: [mark_type, point] — visual mark present
- equidistant_from_sides: [P, V1, V2, V3] — equidistant from triangle sides
- centroid: [G, A, B, C] — G is centroid of ABC
- opposite_side: [P, ref, A, B] — P opposite side of line AB from ref

Rules:
- Generate 1-3 scenarios per activity that involves a visual diagram.
- Skip activities that are purely verbal/conceptual (no diagram needed).
- Prompts must be specific enough to verify: include concrete point labels,
  angle measures, length relationships, or parallelism/perpendicularity.
- Only use property types from the supported list above.
- Return a JSON array. If no diagram-worthy activities exist, return [].
""")


def _build_topic_message(topic_data: dict, module: dict, grade: str, volume: int) -> str:
    """Build the user message for a full topic."""
    parts = [
        f"Grade: {grade}, Volume: {volume}",
        f"Module {module['number']}: {module.get('title', '')}",
        f"Topic {topic_data['number']}: {topic_data.get('title', '')}",
        f"Geometric focus: {topic_data.get('geometric_focus', '')}",
        "",
        "Lessons and activities:",
        "",
    ]
    for lesson in topic_data.get("lessons", []):
        parts.append(f"### Lesson {lesson['number']}: {lesson.get('title', '')}")
        if lesson.get("essential_question"):
            parts.append(f"Essential question: {lesson['essential_question']}")
        if lesson.get("key_terms"):
            parts.append(f"Key terms: {', '.join(lesson['key_terms'])}")
        if lesson.get("objectives"):
            parts.append(f"Objectives: {'; '.join(lesson['objectives'])}")
        parts.append("")
        for act in lesson.get("activities", []):
            parts.append(f"- Activity {act.get('number', '?')}: {act.get('title', '')}")
            if act.get("description"):
                parts.append(f"  Description: {act['description']}")
            if act.get("diagram_type"):
                parts.append(f"  Diagram type: {act['diagram_type']}")
            if act.get("concepts"):
                parts.append(f"  Concepts: {', '.join(act['concepts'])}")
        parts.append("")

    parts.append(
        "Generate student-style diagram request scenarios as a JSON array. "
        "Focus on activities that involve visual/spatial geometric content."
    )
    return "\n".join(parts)


def _repair_json(text: str) -> str:
    """Attempt to fix common LLM JSON mistakes."""
    # Fix ]] that should be ]} (common bracket confusion)
    text = re.sub(r'\]\](\s*[,\n\r}\]])', r']}\1', text)
    # Fix }} that should be }] at array boundaries
    text = re.sub(r'\}\}(\s*\])', r'}\1', text)
    # Fix trailing commas before closing brackets
    text = re.sub(r',(\s*[\]\}])', r'\1', text)
    return text


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM response text."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0].strip()

    # Try parsing the whole thing as JSON first (fastest path)
    for attempt_text in [text, _repair_json(text)]:
        try:
            result = json.loads(attempt_text)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            pass

    # Fall back: find the outermost [ ... ] by bracket counting
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return []

    chunk = text[start:end]
    for attempt in [chunk, _repair_json(chunk)]:
        try:
            result = json.loads(attempt)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            pass
    return []


def _generate_for_topic(
    client: anthropic.Anthropic,
    topic_data: dict,
    module: dict,
    grade: str,
    volume: int,
) -> list[dict]:
    """Generate eval scenarios for a single topic."""
    label = f"M{module['number']}T{topic_data['number']}"
    user_msg = _build_topic_message(topic_data, module, grade, volume)
    n_acts = sum(len(l.get("activities", [])) for l in topic_data.get("lessons", []))

    print(f"  [{label}] {topic_data.get('title', '?')} ({n_acts} activities)...")
    t0 = time.time()

    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        for _ in stream.text_stream:
            pass
        response = stream.get_final_message()
    elapsed = time.time() - t0

    usage = response.usage
    text = response.content[0].text
    scenarios = _extract_json_array(text)

    if not scenarios and len(text) > 100:
        # Save failed response for debugging
        debug_path = CURRICULUM_DIR / f"debug_{label}.txt"
        debug_path.write_text(text[:5000])
        print(f"    [{label}] JSON extraction failed, saved debug to {debug_path.name}")

    # Tag and deduplicate IDs
    seen_ids: set[str] = set()
    for s in scenarios:
        if "id" not in s or not s["id"]:
            s["id"] = f"geo-m{module['number']}-t{topic_data['number']}-{len(seen_ids)+1}"
        tags = s.get("tags", [])
        if "curriculum" not in tags:
            tags.append("curriculum")
        if f"grade-{grade}" not in tags:
            tags.append(f"grade-{grade}")
        s["tags"] = tags

        base_id = s["id"]
        counter = 1
        while s["id"] in seen_ids:
            s["id"] = f"{base_id}-{counter}"
            counter += 1
        seen_ids.add(s["id"])

    # Validate
    valid = []
    for s in scenarios:
        try:
            result = _validate_scenarios([s])
            valid.extend(result)
        except (ValueError, KeyError, TypeError) as e:
            print(f"    [{label}] INVALID '{s.get('id', '?')}': {e}")

    print(f"  [{label}] {elapsed:.0f}s — {len(valid)}/{len(scenarios)} valid scenarios "
          f"(in={usage.input_tokens:,} out={usage.output_tokens:,})")
    return valid


def _write_markdown(scenarios: list[dict], path: Path) -> None:
    """Write a human-readable markdown overview of the generated scenarios."""
    lines = [
        "# Student Diagram Queries — Generated from Curriculum",
        "",
        f"**{len(scenarios)} scenarios** generated from the geometry curriculum.",
        "",
    ]

    by_tier = {1: [], 2: [], 3: []}
    for s in scenarios:
        by_tier.setdefault(s.get("tier", 1), []).append(s)

    tier_names = {1: "Basic Construction", 2: "Theorem / Proof Diagram", 3: "Multi-step / Advanced"}
    for tier in sorted(by_tier):
        tier_scenarios = by_tier[tier]
        if not tier_scenarios:
            continue
        lines.append(f"## Tier {tier}: {tier_names.get(tier, '')} ({len(tier_scenarios)} scenarios)")
        lines.append("")
        for s in tier_scenarios:
            tags = [t for t in s.get("tags", []) if t not in ("curriculum", "grade-geometry")]
            tag_str = f" `{', '.join(tags)}`" if tags else ""
            lines.append(f"**{s['id']}**{tag_str}")
            lines.append("")
            lines.append(f"> {s['prompt']}")
            lines.append("")
            labels = s.get("required_labels", [])
            props = s.get("expected_properties", [])
            if labels:
                lines.append(f"Labels: {', '.join(labels)}")
            if props:
                prop_strs = [f"`{p['type']}({', '.join(str(a) for a in p.get('args', []))})`" for p in props]
                lines.append(f"Properties: {', '.join(prop_strs)}")
            lines.append("")

    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Generate eval scenarios from curriculum")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--grade", type=str, default=None)
    parser.add_argument("--volume", type=int, default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument(
        "--curriculum",
        type=str,
        default=str(CURRICULUM_DIR / "geometry_curriculum.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(REPO_ROOT / "evals"),
    )
    args = parser.parse_args()

    curriculum_path = Path(args.curriculum)
    if not curriculum_path.exists():
        print(f"ERROR: {curriculum_path} not found. Run extract_curriculum.py first.")
        sys.exit(1)

    data = json.loads(curriculum_path.read_text())
    textbooks = data.get("textbooks", [data])

    # Collect all (topic, module, grade, volume) tuples
    topics: list[tuple[dict, dict, str, int]] = []
    for tb in textbooks:
        grade = tb.get("grade", "")
        volume = tb.get("volume", 0)
        if args.grade and grade != args.grade:
            continue
        if args.volume and volume != args.volume:
            continue
        for mod in tb.get("modules", []):
            for topic in mod.get("topics", []):
                topics.append((topic, mod, grade, volume))

    n_lessons = sum(len(t[0].get("lessons", [])) for t in topics)
    n_acts = sum(
        len(l.get("activities", []))
        for t, _, _, _ in topics
        for l in t.get("lessons", [])
    )
    print(f"Loaded {len(topics)} topics ({n_lessons} lessons, {n_acts} activities)")

    if args.dry_run:
        for topic, mod, grade, vol in topics:
            t_acts = sum(len(l.get("activities", [])) for l in topic.get("lessons", []))
            print(f"  M{mod['number']} T{topic['number']}: {topic.get('title', '?')} "
                  f"({len(topic.get('lessons', []))}L, {t_acts}A)")
        print(f"\nWould generate scenarios for {len(topics)} topics")
        return

    client = anthropic.Anthropic()
    all_scenarios: list[dict] = []
    global_ids: set[str] = set()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = output_dir / "scenarios_geometry_curriculum.yaml"
    md_path = CURRICULUM_DIR / "student_queries.md"

    def _flush():
        """Write current results to disk after each topic completes."""
        sorted_scenarios = sorted(all_scenarios, key=lambda s: s["id"])
        with open(yaml_path, "w") as f:
            yaml.dump(
                sorted_scenarios, f,
                default_flow_style=False, allow_unicode=True,
                sort_keys=False, width=120,
            )
        _write_markdown(sorted_scenarios, md_path)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                _generate_for_topic, client, topic, mod, grade, vol
            ): (topic, mod)
            for topic, mod, grade, vol in topics
        }
        for future in as_completed(futures):
            scenarios = future.result()
            for s in scenarios:
                base_id = s["id"]
                counter = 1
                while s["id"] in global_ids:
                    s["id"] = f"{base_id}-{counter}"
                    counter += 1
                global_ids.add(s["id"])
            all_scenarios.extend(scenarios)
            _flush()
            print(f"    -> wrote {len(all_scenarios)} total scenarios to disk")

    elapsed = time.time() - t0

    print(f"\n{'=' * 50}")
    print(f"Generated {len(all_scenarios)} scenarios in {elapsed:.0f}s")
    print(f"  YAML: {yaml_path}")
    print(f"  Markdown: {md_path}")

    by_tier = {}
    for s in all_scenarios:
        by_tier[s.get("tier", 1)] = by_tier.get(s.get("tier", 1), 0) + 1
    for tier in sorted(by_tier):
        print(f"  Tier {tier}: {by_tier[tier]} scenarios")


if __name__ == "__main__":
    main()
