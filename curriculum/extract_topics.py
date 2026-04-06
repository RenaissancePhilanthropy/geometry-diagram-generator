"""Phase 1: Extract topic/lesson structure from marker-converted markdown files.

Reads markdown files from curriculum/markdown/, parses lesson headings and
surrounding content, and writes curriculum/topic_index.json.

Usage:
    .venv/bin/python curriculum/extract_topics.py
"""
from __future__ import annotations

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


def _split_into_sections(text: str) -> list[dict]:
    """Split markdown into sections by headings, preserving hierarchy."""
    sections = []
    # Split on markdown headings (# through ####)
    parts = re.split(r"^(#{1,4})\s+(.+)$", text, flags=re.MULTILINE)

    # parts is: [preamble, level, title, body, level, title, body, ...]
    i = 1
    while i < len(parts):
        level = len(parts[i])
        title = parts[i + 1].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        sections.append({"level": level, "title": title, "body": body.strip()})
        i += 3

    return sections


def _extract_topics_from_markdown(md_path: Path, grade: str, volume: int) -> list[dict]:
    """Extract lesson topics from a single markdown file."""
    text = md_path.read_text(encoding="utf-8")
    sections = _split_into_sections(text)

    topics = []
    current_module = ""
    current_topic = ""

    for i, sec in enumerate(sections):
        title = sec["title"]
        body = sec["body"]

        # Detect module headings
        mod_match = re.search(r"MODULE\s+(\d+)", title, re.IGNORECASE)
        if mod_match:
            current_module = title

        # Detect topic headings
        topic_match = re.search(r"TOPIC\s+(\d+)", title, re.IGNORECASE)
        if topic_match:
            current_topic = title

        # Detect lesson headings -- various formats across grades:
        #   "LESSON 3 Conjectures and Deductive Reasoning"
        #   "Lesson 1 Writing Equivalent Expressions..."
        #   "1 Exploring the Ratio of Circle Circumference to Diameter"
        lesson_match = re.match(
            r"(?:LESSON\s+)?(\d+)\s+(.+)",
            title,
            re.IGNORECASE,
        )
        if not lesson_match:
            continue

        lesson_num = lesson_match.group(1)
        lesson_title = lesson_match.group(2).strip()

        # Skip non-lesson entries (intro lessons, summaries, test sections)
        skip_patterns = [
            r"Introduction to the Problem",
            r"Summary\b",
            r"Review\b",
            r"Test\b",
            r"^SR\b",
            r"^TS\b",
        ]
        if any(re.search(p, lesson_title, re.IGNORECASE) for p in skip_patterns):
            continue
        if len(lesson_title) < 5:
            continue

        # Gather context: the body of this section + a bit of the next
        sample_text = body[:1200]
        if i + 1 < len(sections):
            sample_text += "\n" + sections[i + 1]["body"][:400]
        sample_text = sample_text[:1500]

        topics.append({
            "grade": grade,
            "volume": volume,
            "module": current_module,
            "topic": current_topic,
            "lesson_number": lesson_num,
            "lesson_title": lesson_title,
            "sample_text": sample_text,
        })

    return topics


def extract_all() -> list[dict]:
    """Extract topics from all available markdown files."""
    all_topics = []

    for stem, (grade, volume) in sorted(GRADE_MAP.items()):
        md_path = MARKDOWN_DIR / f"{stem}.md"
        if not md_path.exists():
            print(f"WARNING: {md_path} not found, skipping")
            continue

        size_mb = md_path.stat().st_size / 1024 / 1024
        print(f"Processing {stem} ({size_mb:.1f} MB)")
        topics = _extract_topics_from_markdown(md_path, grade, volume)
        print(f"  Found {len(topics)} lessons")
        all_topics.extend(topics)

    return all_topics


def main():
    if not MARKDOWN_DIR.exists():
        print(f"ERROR: {MARKDOWN_DIR} not found. Run convert_pdfs.py first.")
        return

    topics = extract_all()
    output_path = CURRICULUM_DIR / "topic_index.json"
    with open(output_path, "w") as f:
        json.dump(topics, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(topics)} topics to {output_path}")


if __name__ == "__main__":
    main()
