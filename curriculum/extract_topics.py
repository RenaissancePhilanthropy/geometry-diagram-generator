"""Phase 1: Extract topic/lesson/activity structure from marker-converted markdown.

Reads markdown files from curriculum/markdown/, builds a hierarchical index of
modules > topics > lessons > activities, filters for geometry-relevant content,
and writes curriculum/topic_index.json.

Usage:
    .venv/bin/python curriculum/extract_topics.py [--all]

By default only geometry-relevant lessons are included. Pass --all to keep
every lesson (useful for debugging).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CURRICULUM_DIR = Path(__file__).parent
MARKDOWN_DIR = CURRICULUM_DIR / "markdown"

GRADE_MAP = {
    "6th_vol1": ("6th", 1),
    "6th_vol2": ("6th", 2),
    "7th_vol1": ("7th", 1),
    "7th_vol2": ("7th", 2),
    "8th_vol1": ("8th", 1),
    "8th_vol2": ("8th", 2),
    "geometry_vol1": ("geometry", 1),
    "geometry_vol2": ("geometry", 2),
}

# Keywords that signal geometry-relevant content.  Used to filter 6th-8th
# grade lessons (geometry textbook is always included in full).
GEOMETRY_KEYWORDS = re.compile(
    r"triangle|angle|circle|parallel|perpendicular|congruent|similar"
    r"|polygon|quadrilateral|trapezoid|parallelogram|rhombus|rectangle|square"
    r"|symmetry|reflection|rotation|translation|transformation|dilation"
    r"|bisect|midpoint|median|altitude|circumscri|inscri"
    r"|tangent|chord|arc|sector|secant"
    r"|pythagorean|hypotenuse"
    r"|coordinate\s+plane|coordinate\s+grid"
    r"|area|perimeter|volume|surface\s+area"
    r"|segment|ray|plane|vertex|vertices"
    r"|rigid\s+motion|geometric|geometry|shape|solid|prism|pyramid|cone|cylinder|sphere",
    re.IGNORECASE,
)


def _parse_heading(line: str) -> tuple[int, str] | None:
    """Parse a markdown heading line, return (level, title) or None."""
    m = re.match(r"^(#{1,6})\s+(.+)$", line)
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def _clean_title(title: str) -> str:
    """Strip markdown bold/italic/span markers from a title."""
    title = re.sub(r"<[^>]+>", "", title)  # HTML tags
    title = re.sub(r"\*+", "", title)      # bold/italic markers
    title = title.strip()
    return title


def _extract_hierarchy(md_path: Path, grade: str, volume: int) -> list[dict]:
    """Extract a flat list of lessons+activities with full hierarchy context.

    Returns one entry per lesson, with nested activities.
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    current_module = ""
    current_topic = ""
    lessons: list[dict] = []
    current_lesson: dict | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        parsed = _parse_heading(line)

        if parsed:
            level, raw_title = parsed
            title = _clean_title(raw_title)

            # --- Module heading ---
            # e.g. "## **MODULE** 1" followed by "## Composing and Decomposing"
            if re.search(r"\bMODULE\b", title, re.IGNORECASE) and level <= 2:
                mod_match = re.search(r"MODULE\s*(\d+)", title, re.IGNORECASE)
                if mod_match:
                    mod_num = mod_match.group(1)
                    # Look ahead for the module name on subsequent headings
                    module_name = ""
                    for j in range(i + 1, min(i + 8, len(lines))):
                        next_parsed = _parse_heading(lines[j])
                        if next_parsed and next_parsed[0] <= 2:
                            candidate = _clean_title(next_parsed[1])
                            # Skip "MODULE 1 OVERVIEW" or meta headings
                            if re.search(r"MODULE|OVERVIEW|TEKS|Sessions:", candidate, re.IGNORECASE):
                                continue
                            if len(candidate) > 3:
                                module_name = candidate
                                break
                    current_module = f"Module {mod_num}: {module_name}".strip(": ")

            # --- Topic heading ---
            # e.g. "## **TOPIC 2** *Shapes and Solids* 10 SESSIONS"
            # or "## **TOPIC 1** *Factors and Multiples* 15 SESSIONS"
            topic_match = re.match(
                r".*\bTOPIC\s+(\d+)\b[^a-zA-Z]*(.*)",
                title,
                re.IGNORECASE,
            )
            if topic_match and level <= 3:
                topic_num = topic_match.group(1)
                topic_name = _clean_title(topic_match.group(2))
                # Strip trailing session counts, pacing info, etc.
                topic_name = re.sub(r"\d+\s*SESSIONS?\s*$", "", topic_name, flags=re.IGNORECASE).strip()
                topic_name = re.sub(r"PACING\s+GUIDE.*$", "", topic_name, flags=re.IGNORECASE).strip()
                topic_name = re.sub(r"\d+-Day\s+Pacing.*$", "", topic_name, flags=re.IGNORECASE).strip()
                topic_name = re.sub(r"^OVERVIEW$", "", topic_name, flags=re.IGNORECASE).strip()
                topic_name = re.sub(r"\d+\s*DAY.*$", "", topic_name, flags=re.IGNORECASE).strip()
                topic_name = re.sub(r"\d+-MINUTE.*$", "", topic_name, flags=re.IGNORECASE).strip()
                # If name is still empty or junk, look ahead
                if not topic_name or len(topic_name) < 3:
                    for j in range(i + 1, min(i + 6, len(lines))):
                        next_parsed = _parse_heading(lines[j])
                        if next_parsed:
                            candidate = _clean_title(next_parsed[1])
                            candidate = re.sub(r"^TOPIC\s+\d+\s*", "", candidate, flags=re.IGNORECASE)
                            candidate = re.sub(r"OVERVIEW|PACING|TEKS|Sessions:", "", candidate, flags=re.IGNORECASE).strip()
                            if len(candidate) > 3 and not re.match(r"^\d+$", candidate):
                                topic_name = candidate
                                break
                if topic_name:
                    current_topic = f"Topic {topic_num}: {topic_name}"

            # --- Lesson heading ---
            # e.g. "# 1 **Constructing Triangles Given Sides**"
            # or "# 3 **Area of Triangles and Quadrilaterals**"
            lesson_match = re.match(
                r"^(?:LESSON\s+)?(\d+)\s+(.+)",
                title,
                re.IGNORECASE,
            )
            if lesson_match and level <= 2:
                lesson_title = _clean_title(lesson_match.group(2))
                # Skip intro/summary/overview headings
                if re.search(
                    r"Introduction to the Problem|OVERVIEW|PACING|Summary|Assessment",
                    lesson_title,
                    re.IGNORECASE,
                ):
                    i += 1
                    continue

                if len(lesson_title) < 5:
                    i += 1
                    continue

                # Save previous lesson if exists
                if current_lesson:
                    lessons.append(current_lesson)

                current_lesson = {
                    "grade": grade,
                    "volume": volume,
                    "module": current_module,
                    "topic": current_topic,
                    "lesson_number": lesson_match.group(1),
                    "lesson_title": lesson_title,
                    "activities": [],
                    "essential_ideas": [],
                    "sample_text": "",
                }

            # --- LESSON OVERVIEW body ---
            if current_lesson and "LESSON OVERVIEW" in title:
                # Grab the paragraph(s) following this heading as the lesson overview
                overview_lines = []
                for j in range(i + 1, min(i + 20, len(lines))):
                    if lines[j].startswith("#"):
                        break
                    stripped = lines[j].strip()
                    if stripped and not stripped.startswith("!["): # skip images
                        overview_lines.append(stripped)
                if overview_lines:
                    current_lesson["sample_text"] = " ".join(overview_lines)[:1500]

            # --- Essential Ideas ---
            if current_lesson and "ESSENTIAL IDEAS" in title:
                for j in range(i + 1, min(i + 15, len(lines))):
                    if lines[j].startswith("#"):
                        break
                    stripped = lines[j].strip()
                    if stripped.startswith("- "):
                        current_lesson["essential_ideas"].append(stripped[2:])

            # --- Activity heading ---
            # e.g. "#### Activity 1.1: Pasta Triangles 30–35 minutes"
            # or "## ACTIVITY 2.1 Analyzing Angles and Sides"
            activity_match = re.match(
                r".*\bActivity\s+(\d+\.\d+)[:\s]+(.+?)(?:\s+\d+[\-–]\d+\s*minutes)?$",
                title,
                re.IGNORECASE,
            )
            if activity_match and current_lesson:
                act_title = _clean_title(activity_match.group(2))
                # Grab description from the next few lines
                desc_lines = []
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].startswith("#"):
                        break
                    stripped = lines[j].strip()
                    if stripped and not stripped.startswith("!["):
                        desc_lines.append(stripped)
                description = " ".join(desc_lines)[:500]

                current_lesson["activities"].append({
                    "id": activity_match.group(1),
                    "title": act_title,
                    "description": description,
                })

        i += 1

    # Don't forget the last lesson
    if current_lesson:
        lessons.append(current_lesson)

    # Deduplicate: remove lessons with identical (lesson_number, lesson_title)
    # keeping the one with the most content, and deduplicate activities by ID
    seen_lessons: dict[str, int] = {}
    deduped: list[dict] = []
    for lesson in lessons:
        key = f"{lesson['lesson_number']}:{lesson['lesson_title']}"
        if key in seen_lessons:
            idx = seen_lessons[key]
            existing = deduped[idx]
            # Merge: keep the version with more activities/content
            if len(lesson.get("activities", [])) > len(existing.get("activities", [])):
                deduped[idx] = lesson
            if not existing.get("sample_text") and lesson.get("sample_text"):
                existing["sample_text"] = lesson["sample_text"]
            if not existing.get("essential_ideas") and lesson.get("essential_ideas"):
                existing["essential_ideas"] = lesson["essential_ideas"]
        else:
            seen_lessons[key] = len(deduped)
            deduped.append(lesson)

    # Deduplicate activities within each lesson
    for lesson in deduped:
        acts = lesson.get("activities", [])
        seen_acts: set[str] = set()
        unique_acts = []
        for a in acts:
            if a["id"] not in seen_acts:
                seen_acts.add(a["id"])
                unique_acts.append(a)
        lesson["activities"] = unique_acts

    return deduped


def _is_geometry_relevant(lesson: dict) -> bool:
    """Check if a lesson is geometry-related based on title, topic, and content.

    Uses a two-tier approach: strong keywords match on title/topic alone,
    while weaker keywords (area, volume) must appear in a geometric context.
    """
    title_topic = " ".join([
        lesson.get("lesson_title", ""),
        lesson.get("topic", ""),
    ])

    # Strong signals — these in the title or topic mean the lesson is about geometry
    strong_title = re.compile(
        r"triangle|angle|circle|parallel|perpendicular|congruent|similar"
        r"|polygon|quadrilateral|trapezoid|parallelogram|rhombus"
        r"|symmetry|reflection|rotation|translation|transformation|dilation"
        r"|bisect|midpoint|median|altitude|circumscri|inscri"
        r"|tangent|chord|arc|sector|secant"
        r"|pythagorean|hypotenuse"
        r"|coordinate\s+plane|coordinate\s+grid"
        r"|rigid\s+motion|geometry|shapes?\s+and\s+solid"
        r"|prism|pyramid|cone|cylinder|sphere"
        r"|area\s+of\s+\w+|volume\s+of\s+\w+|surface\s+area|perimeter"
        r"|construct.*triangle",
        re.IGNORECASE,
    )
    if strong_title.search(title_topic):
        return True

    # For content-based matching, require strong geometry terms (not just
    # "area models" or "coordinate" in an algebra context)
    full_text = " ".join([
        title_topic,
        lesson.get("sample_text", ""),
        " ".join(lesson.get("essential_ideas", [])),
        " ".join(a.get("title", "") for a in lesson.get("activities", [])),
    ])
    return bool(strong_title.search(full_text))


def extract_all(include_all: bool = False) -> list[dict]:
    """Extract topics from all available markdown files."""
    all_topics = []

    for stem, (grade, volume) in sorted(GRADE_MAP.items()):
        md_path = MARKDOWN_DIR / f"{stem}.md"
        if not md_path.exists():
            print(f"  SKIP {stem} (not yet converted)")
            continue

        size_mb = md_path.stat().st_size / 1024 / 1024
        lessons = _extract_hierarchy(md_path, grade, volume)

        if include_all or grade == "geometry":
            filtered = lessons
        else:
            filtered = [l for l in lessons if _is_geometry_relevant(l)]

        print(f"  {stem} ({size_mb:.1f} MB): {len(lessons)} lessons, {len(filtered)} geometry-relevant")
        all_topics.extend(filtered)

    return all_topics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Include non-geometry lessons too")
    args = parser.parse_args()

    if not MARKDOWN_DIR.exists():
        print(f"ERROR: {MARKDOWN_DIR} not found. Run convert_pdfs.py first.")
        return

    print("Extracting topics from markdown files...\n")
    topics = extract_all(include_all=args.all)

    output_path = CURRICULUM_DIR / "topic_index.json"
    with open(output_path, "w") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)

    # Print summary
    total_activities = sum(len(t.get("activities", [])) for t in topics)
    print(f"\nWrote {len(topics)} lessons ({total_activities} activities) to {output_path}")
    print("\nBreakdown by grade:")
    by_grade: dict[str, int] = {}
    for t in topics:
        by_grade[t["grade"]] = by_grade.get(t["grade"], 0) + 1
    for g, count in sorted(by_grade.items()):
        print(f"  {g}: {count} lessons")


if __name__ == "__main__":
    main()
