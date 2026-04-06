"""Phase 2+3: Generate student-style eval scenarios from extracted topics.

Reads curriculum/topic_index.json, calls Claude to produce diagram request
prompts with scenario metadata, validates output, and writes YAML files
compatible with evals/run.py.

Usage:
    .venv/bin/python curriculum/generate_prompts.py [--dry-run] [--grade geometry]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
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

SYSTEM_PROMPT = dedent(f"""\
You are a geometry curriculum specialist creating eval scenarios for a diagram
generation system. Given a textbook lesson title and sample content, produce
student-style diagram request prompts.

Each scenario must be a JSON object with these fields:
- "id": kebab-case unique identifier (e.g. "geo-m1-t2-l3-parallel-lines-1")
- "tier": integer 1-3 (1=basic construction, 2=theorem/proof diagram, 3=multi-step/advanced)
- "tags": list of keyword strings (e.g. ["triangle", "congruence", "curriculum"])
- "prompt": a student-style diagram request. Write it as a clear, specific
  instruction like "Draw a right triangle ABC with the right angle at C.
  Label all three vertices." NOT like a textbook problem.
- "required_labels": list of point/vertex labels that must appear (e.g. ["A", "B", "C"])
- "expected_properties": list of geometric property checks. Each is an object with:
  - "name": descriptive snake_case name (e.g. "right_angle_at_C")
  - "type": one of: {SUPPORTED_TYPES_STR}
  - "args": list of arguments (point labels or nested lists for segments/lines)

Property type reference:
- right_angle: args=[P1, vertex, P2] — angle at vertex is 90°
- midpoint: args=[M, A, B] — M is midpoint of AB
- collinear: args=[P1, P2, P3] — points are collinear
- equal_lengths: args=[[P1,P2], [P3,P4], ...] — segments have equal length
- parallel: args=[[P1,P2], [P3,P4]] — lines are parallel
- perpendicular: args=[[P1,P2], [P3,P4]] — lines are perpendicular
- point_on_line: args=[P, A, B] — P lies on line through A,B
- point_on_segment: args=[P, A, B] — P lies on segment AB
- point_on_circle: args=[P, center, radius_point] — P is on circle
- tangent: args=[[P1,P2], center, tangent_point] — line is tangent to circle
- angle_equal: args=[[P1,V1,P2], [P3,V2,P4]] — two angles are equal
- angle_bisector: args=[D, vertex, P1, P2] — ray vertex->D bisects angle P1-vertex-P2
- mark_present: args=[mark_type, point] — visual mark present (e.g. right_angle mark)
- equidistant_from_sides: args=[P, V1, V2, V3] — P equidistant from sides of triangle
- centroid: args=[G, A, B, C] — G is centroid of triangle ABC
- opposite_side: args=[P, ref, A, B] — P is on opposite side of line AB from ref

Rules:
- Always include "curriculum" in tags, plus the grade level (e.g. "grade-8")
- Prompts should sound like a student asking for help, not textbook language
- Each prompt must request a specific geometric diagram with labeled points
- Only use property types from the supported list above
- Generate 2-5 scenarios per lesson, focusing on diagram-worthy content
- Skip lessons that don't involve geometric diagrams (e.g. pure algebra, statistics)
- Return a JSON array of scenario objects, nothing else
""")


def _build_user_message(topic: dict) -> str:
    """Build the user message for Claude from a topic entry."""
    parts = [
        f"Grade: {topic['grade']}",
        f"Module: {topic['module']}",
        f"Topic: {topic['topic']}",
        f"Lesson {topic['lesson_number']}: {topic['lesson_title']}",
    ]
    if topic.get("sample_text"):
        parts.append(f"\nSample content from lesson:\n{topic['sample_text'][:2000]}")

    parts.append(
        "\nGenerate 2-5 eval scenarios as a JSON array. "
        "Only include scenarios that involve geometric diagrams. "
        "If this lesson has no diagram-worthy geometry content, return an empty array []."
    )
    return "\n".join(parts)


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to kebab-case slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-")


def _generate_scenarios_for_topic(
    client: anthropic.Anthropic,
    topic: dict,
    model: str = "claude-sonnet-4-20250514",
) -> list[dict]:
    """Call Claude to generate scenarios for one topic."""
    user_msg = _build_user_message(topic)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()

    # Extract JSON array from response (may be wrapped in ```json ... ```)
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not json_match:
        return []

    try:
        scenarios = json.loads(json_match.group())
    except json.JSONDecodeError:
        print(f"    WARNING: Failed to parse JSON for {topic['lesson_title']}")
        return []

    if not isinstance(scenarios, list):
        return []

    # Prefix IDs to ensure uniqueness
    grade_prefix = topic["grade"][:3]
    for i, s in enumerate(scenarios):
        if "id" not in s or not s["id"]:
            slug = _slugify(topic["lesson_title"])
            s["id"] = f"{grade_prefix}-{slug}-{i+1}"

        # Ensure curriculum tag
        tags = s.get("tags", [])
        if "curriculum" not in tags:
            tags.append("curriculum")
        grade_tag = f"grade-{topic['grade']}"
        if grade_tag not in tags:
            tags.append(grade_tag)
        s["tags"] = tags

    return scenarios


def _validate_and_filter(scenarios: list[dict]) -> list[dict]:
    """Validate scenarios against the eval runner schema, keeping only valid ones."""
    valid = []
    for s in scenarios:
        try:
            result = _validate_scenarios([s])
            valid.extend(result)
        except (ValueError, KeyError, TypeError) as e:
            print(f"    INVALID scenario '{s.get('id', '?')}': {e}")
    return valid


def generate_all(
    topics: list[dict],
    grade_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, list[dict]]:
    """Generate scenarios for all topics, grouped by grade."""
    client = anthropic.Anthropic()

    if grade_filter:
        topics = [t for t in topics if t["grade"] == grade_filter]

    # Group by grade
    by_grade: dict[str, list[dict]] = {}
    for t in topics:
        by_grade.setdefault(t["grade"], []).append(t)

    results: dict[str, list[dict]] = {}
    seen_ids: set[str] = set()

    for grade, grade_topics in sorted(by_grade.items()):
        print(f"\n=== Grade: {grade} ({len(grade_topics)} lessons) ===")
        grade_scenarios: list[dict] = []

        for topic in grade_topics:
            label = f"{topic['lesson_number']}: {topic['lesson_title']}"
            print(f"  [{label}]")

            if dry_run:
                print(f"    (dry run, skipping API call)")
                continue

            try:
                raw = _generate_scenarios_for_topic(client, topic)
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

            if not raw:
                print(f"    (no diagram-worthy content)")
                continue

            # Deduplicate IDs
            for s in raw:
                base_id = s["id"]
                counter = 1
                while s["id"] in seen_ids:
                    s["id"] = f"{base_id}-{counter}"
                    counter += 1
                seen_ids.add(s["id"])

            valid = _validate_and_filter(raw)
            print(f"    Generated {len(valid)} valid scenarios")
            grade_scenarios.extend(valid)

            # Brief pause to avoid rate limits
            time.sleep(0.5)

        results[grade] = grade_scenarios

    return results


def write_yaml_files(results: dict[str, list[dict]], output_dir: Path):
    """Write one YAML file per grade."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for grade, scenarios in sorted(results.items()):
        if not scenarios:
            continue
        out_path = output_dir / f"scenarios_{grade}.yaml"
        with open(out_path, "w") as f:
            yaml.dump(
                scenarios,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
        print(f"Wrote {len(scenarios)} scenarios to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate eval scenarios from curriculum")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, just show plan")
    parser.add_argument("--grade", type=str, default=None, help="Only process this grade")
    parser.add_argument(
        "--topic-index",
        type=str,
        default=str(CURRICULUM_DIR / "topic_index.json"),
        help="Path to topic_index.json",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(REPO_ROOT / "evals"),
        help="Directory to write scenario YAML files",
    )
    args = parser.parse_args()

    topic_path = Path(args.topic_index)
    if not topic_path.exists():
        print(f"ERROR: {topic_path} not found. Run extract_topics.py first.")
        sys.exit(1)

    topics = json.loads(topic_path.read_text())
    print(f"Loaded {len(topics)} topics from {topic_path}")

    results = generate_all(topics, grade_filter=args.grade, dry_run=args.dry_run)

    if not args.dry_run:
        write_yaml_files(results, Path(args.output_dir))

        total = sum(len(v) for v in results.values())
        print(f"\nTotal: {total} scenarios across {len(results)} grades")


if __name__ == "__main__":
    main()
