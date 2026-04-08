"""Extract a clean geometry curriculum hierarchy from the marker-converted
geometry textbook markdown using Claude Sonnet.

Replaces the regex-based extraction in extract_topics.py for the geometry
volumes specifically. The teacher's edition has heading structure that doesn't
fit a simple regex, and we need comprehensive geometric topic coverage to
drive realistic student prompt generation downstream.

Usage:
    .venv/bin/python curriculum/extract_geometry_curriculum.py [--volume 1|2|both]
    .venv/bin/python curriculum/extract_geometry_curriculum.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from textwrap import dedent

import anthropic
from dotenv import load_dotenv

load_dotenv()

CURRICULUM_DIR = Path(__file__).parent
MARKDOWN_DIR = CURRICULUM_DIR / "markdown"
OUTPUT_PATH = CURRICULUM_DIR / "geometry_curriculum.json"

MODEL = "claude-sonnet-4-6"
BETAS = ["context-1m-2025-08-07"]  # 1M context window (each geometry vol is ~600K tokens)

SYSTEM_PROMPT = dedent("""\
You are a curriculum analyst extracting structured lesson data from a Carnegie
Learning Bluebonnet Geometry teacher's edition that has been converted from PDF
to Markdown. The conversion is imperfect: headings are inconsistent, lessons
are split across multiple heading lines, and pedagogical scaffolding is
interleaved with the actual lesson content.

DOWNSTREAM USE
The output of this extraction will be used to generate realistic
student-style geometry diagram prompts that cover every geometric topic in
the curriculum. COMPLETENESS of geometric topic coverage is the highest
priority. Missing a topic means students will never get prompts about it.

TEXTBOOK STRUCTURE
The textbook is organized as:
  Module → Topic → Lesson → Activity

Pedagogical sub-sections that appear inside every lesson (NOT lessons or
activities themselves):
  - ENGAGE / Getting Started        — warm-up
  - DEVELOP / Activities            — main instructional activities
  - DEMONSTRATE / Talk the Talk     — wrap-up
  - Objectives, Key Terms, Essential Question, Prepare, Worked Example,
    Practice, Assignment, Remember  — lesson framing/support material

A "lesson" is a numbered unit within a Topic with a real geometric title like
"Constructing a Coordinate Plane" or "Proving Triangle Congruence Theorems".
A heading like "Objectives", "Getting Started", "Prepare", or "Key Terms" is
NOT a lesson — it is a sub-section inside a lesson.

An "activity" is a numbered student task inside a lesson, typically appearing
under headings like "Activity 1.1", or as the main numbered work that follows
a "DEVELOP" / "Activities" header. Each activity has a title and a short
description of what students do.

WHAT TO INCLUDE
- Every geometry-related lesson and activity. Be exhaustive.
- A "Talk the Talk" wrap-up that asks students to draw / construct / label
  something counts as an activity.

WHAT TO SKIP
- Lessons that are purely non-geometric (probability, statistics, expected
  value, sample spaces, financial literacy). The geometry textbook contains
  a few of these at the end of vol2 — omit them entirely from the output.
- Course-level meta sections (Acknowledgments, Welcome, Instructional Design,
  Year-at-a-Glance, TEKS Summary, etc.).

OUTPUT JSON SCHEMA
{
  "volume": <int>,
  "modules": [
    {
      "number": "1",
      "title": "Reasoning with Shapes",
      "topics": [
        {
          "number": "1",
          "title": "Composing and Decomposing Shapes",
          "geometric_focus": "Brief 1-2 sentence summary of the geometry
                              concepts this topic teaches. This is the
                              coverage checklist for prompt generation.",
          "lessons": [
            {
              "number": "1",
              "title": "Constructing a Coordinate Plane",
              "essential_question": "How can ...?",
              "objectives": ["...", "..."],
              "key_terms": ["coordinate plane", "..."],
              "activities": [
                {
                  "number": "1",
                  "title": "Constructing a Perpendicular Line Using Patty Paper",
                  "description": "Students fold patty paper to construct a
                                  perpendicular line through a given point.",
                  "diagram_type": "perpendicular line construction",
                  "concepts": ["perpendicular line", "patty paper construction",
                               "midpoint"]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}

RULES
- Return ONLY the JSON object. No prose, no markdown fences, no commentary.
- Use the textbook's own numbering for modules, topics, lessons, activities.
- Use null or [] for missing fields, but try hard to fill them in.
- Concept tags should be SPECIFIC (e.g. "perpendicular bisector construction",
  not "construction"). They drive student prompt generation.
- Do not invent lessons or activities. Extract only what is in the markdown.
- If the same lesson is duplicated by the PDF conversion, include it once.
""")


def _call_sonnet(client: anthropic.Anthropic, volume: int, markdown: str) -> dict:
    """Send the full markdown to Sonnet and parse the JSON response.

    Uses streaming because max_tokens=64000 requires it to avoid HTTP timeouts,
    and the 1M context beta header because each volume is ~600K input tokens.
    """
    user_msg = (
        f"Volume: {volume}\n\n"
        "Markdown content follows. Extract the full curriculum hierarchy as "
        "specified, prioritizing completeness of geometric topic coverage.\n\n"
        "---\n\n"
        f"{markdown}"
    )

    print(f"  Calling {MODEL} (input ~{len(user_msg)//4:,} tokens, streaming)...")
    t0 = time.time()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        betas=BETAS,
    ) as stream:
        # Drain the stream — we don't need per-token output, just the final message
        for _ in stream.text_stream:
            pass
        response = stream.get_final_message()
    elapsed = time.time() - t0

    usage = response.usage
    print(
        f"  Done in {elapsed:.0f}s. "
        f"input={usage.input_tokens:,} output={usage.output_tokens:,} "
        f"stop={response.stop_reason}"
    )

    text = response.content[0].text.strip()

    # Strip ```json fences if present (the prompt says not to use them but
    # belt-and-suspenders)
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Save raw output for debugging
        debug_path = CURRICULUM_DIR / f"geometry_vol{volume}_raw.txt"
        debug_path.write_text(text)
        print(f"  ERROR parsing JSON: {e}")
        print(f"  Raw output saved to {debug_path}")
        raise


def _summarize(curriculum: dict) -> None:
    """Print a quick summary of the extracted hierarchy."""
    vol = curriculum.get("volume")
    modules = curriculum.get("modules", [])
    n_topics = sum(len(m.get("topics", [])) for m in modules)
    n_lessons = sum(
        len(t.get("lessons", []))
        for m in modules
        for t in m.get("topics", [])
    )
    n_activities = sum(
        len(l.get("activities", []))
        for m in modules
        for t in m.get("topics", [])
        for l in t.get("lessons", [])
    )
    print(f"  Vol {vol}: {len(modules)} modules, {n_topics} topics, "
          f"{n_lessons} lessons, {n_activities} activities")


def extract_volume(volume: int) -> dict:
    md_path = MARKDOWN_DIR / f"geometry_vol{volume}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"{md_path} not found. Run convert_pdfs.py first.")

    print(f"\n=== Extracting geometry vol{volume} ===")
    markdown = md_path.read_text(encoding="utf-8")
    print(f"  Source: {md_path} ({len(markdown):,} chars)")

    client = anthropic.Anthropic()
    curriculum = _call_sonnet(client, volume, markdown)
    _summarize(curriculum)
    return curriculum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--volume",
        choices=["1", "2", "both"],
        default="1",
        help="Which volume(s) to extract. Default: 1 (sanity check).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without calling the API.",
    )
    args = parser.parse_args()

    volumes = [1, 2] if args.volume == "both" else [int(args.volume)]

    if args.dry_run:
        for v in volumes:
            md_path = MARKDOWN_DIR / f"geometry_vol{v}.md"
            size = md_path.stat().st_size if md_path.exists() else 0
            print(f"Would extract vol{v}: {md_path} ({size:,} bytes, "
                  f"~{size//4:,} input tokens)")
        return

    results = {}
    for v in volumes:
        results[v] = extract_volume(v)

    # Merge into a single output file. If only vol1, write that alone.
    # If both, write a combined object keyed by volume.
    if len(results) == 1:
        out = list(results.values())[0]
    else:
        out = {"volumes": [results[v] for v in sorted(results)]}

    OUTPUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
