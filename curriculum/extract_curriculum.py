"""Extract structured geometry curriculum from Carnegie Bluebonnet textbook markdowns.

Splits each textbook volume into topic-sized chunks at logical chapter
boundaries (MODULE/TOPIC OVERVIEW headings), then sends each chunk to Claude
for structured extraction.  Chunks are processed in parallel for speed.

For the geometry textbook, every topic is extracted.  For 6th-8th grade,
only geometry-relevant topics are extracted.

Usage:
    .venv/bin/python curriculum/extract_curriculum.py --targets geometry
    .venv/bin/python curriculum/extract_curriculum.py --targets all
    .venv/bin/python curriculum/extract_curriculum.py --targets 6th_vol1 7th_vol2
    .venv/bin/python curriculum/extract_curriculum.py --dry-run --targets all
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
from dotenv import load_dotenv

load_dotenv()

CURRICULUM_DIR = Path(__file__).parent
MARKDOWN_DIR = CURRICULUM_DIR / "markdown"
OUTPUT_PATH = CURRICULUM_DIR / "geometry_curriculum.json"

MODEL = "claude-sonnet-4-6"
MAX_WORKERS = 4

VOLUME_MAP: dict[str, tuple[str, int]] = {
    "6th_vol1": ("6th", 1),
    "6th_vol2": ("6th", 2),
    "7th_vol1": ("7th", 1),
    "7th_vol2": ("7th", 2),
    "8th_vol1": ("8th", 1),
    "8th_vol2": ("8th", 2),
    "geometry_vol1": ("geometry", 1),
    "geometry_vol2": ("geometry", 2),
}

# Non-geometry modules/topics to skip
SKIP_MODULES = {"5"}  # Module 5 = "Making Informed Decisions" (probability)
SKIP_TOPICS: set[str] = set()

# ---------------------------------------------------------------------------
# Chunking: split markdown at topic boundaries
# ---------------------------------------------------------------------------

def _find_topic_title(lines: list[str], overview_line: int) -> str:
    """Find the topic title by scanning headings after a TOPIC OVERVIEW line.

    Handles both bold titles (# **Circles**) and plain titles (# Composing and
    Decomposing Shapes), while skipping overview questions like "How are the
    key concepts organized?"
    """
    for j in range(overview_line + 1, min(overview_line + 8, len(lines))):
        line = lines[j].strip()
        if not line.startswith("#"):
            continue
        # Strip heading markers
        text = re.sub(r"^#{1,6}\s+", "", line).strip()
        # Strip bold/italic markers
        text = re.sub(r"\*+", "", text).strip()
        # Strip HTML
        text = re.sub(r"<[^>]+>", "", text).strip()
        # Skip meta headings and overview questions
        if re.search(r"^(How|What|Why)\s+(are|is|do)", text, re.IGNORECASE):
            continue
        if re.search(r"TOPIC|OVERVIEW|TEKS|PACING|MODULE|Assessment|organized", text, re.IGNORECASE):
            continue
        if len(text) > 3:
            return text
    return ""


def _find_topic_chunks(lines: list[str]) -> list[dict]:
    """Split markdown lines into topic-level chunks using heading boundaries.

    Two-pass approach:
      1. Collect all module markers and topic markers with line numbers.
      2. Deduplicate, assign modules to topics, compute chunk boundaries.

    Returns list of {"module_num", "module_title", "topic_num", "topic_title",
    "start_line", "end_line"} dicts.
    """
    # Pass 1: collect markers
    module_markers: list[tuple[int, str, str]] = []  # (line, num, title)
    topic_markers: list[tuple[int, str, str, str]] = []  # (line, mod_num|"", topic_num, title)

    for i, line in enumerate(lines):
        # MODULE N, TOPIC N PACING GUIDE — has explicit module+topic numbers
        p = re.match(
            r"^#{1,6}\s+\*\*MODULE\s+(\d+),?\s*TOPIC\s+(\d+)\s+PACING",
            line,
        )
        if p:
            topic_markers.append((i, p.group(1), p.group(2), ""))
            continue

        # MODULE N OVERVIEW — as heading or inline (PDF conversion artifacts)
        m = re.search(r"\*\*MODULE\s+(\d+)\s+OVERVIEW\*\*", line)
        if m:
            mod_num = m.group(1)
            # Look ahead for module title
            title = ""
            for j in range(i + 1, min(i + 15, len(lines))):
                tm = re.match(r"^#{1,6}\s+\*\*(.+?)\*\*", lines[j])
                if tm:
                    candidate = tm.group(1).strip()
                    if not re.search(r"MODULE|OVERVIEW|TEKS|Assessment|PACING", candidate, re.IGNORECASE):
                        if len(candidate) > 3:
                            title = candidate
                            break
            module_markers.append((i, mod_num, title))
            continue

        # MODULE N Title (table-of-contents style heading, skip these —
        # they appear at the top of the file, far from actual content)
        # We only use MODULE OVERVIEW markers for module boundaries.

        # TOPIC N OVERVIEW (standalone, module inferred from context)
        t = re.match(r"^#{1,6}\s+\*\*TOPIC\s+(\d+)\s+OVERVIEW", line)
        if t:
            topic_title = _find_topic_title(lines, i)
            topic_markers.append((i, "", t.group(1), topic_title))

    # Pass 2: assign module numbers to standalone TOPIC OVERVIEW markers
    # by finding the most recent module marker before each topic marker
    for idx, (line_no, mod_num, topic_num, title) in enumerate(topic_markers):
        if mod_num:
            continue
        # Find most recent module marker before this line
        best_mod = ""
        for m_line, m_num, _ in module_markers:
            if m_line < line_no:
                best_mod = m_num
        # Also check if a PACING GUIDE marker for this topic follows shortly
        for t_line, t_mod, t_topic, _ in topic_markers:
            if t_mod and t_topic == topic_num and abs(t_line - line_no) < 200:
                best_mod = t_mod
                break
        topic_markers[idx] = (line_no, best_mod, topic_num, title)

    # Deduplicate: keep earliest marker per (module, topic) pair
    seen: dict[tuple[str, str], int] = {}
    boundaries: list[dict] = []
    module_titles: dict[str, str] = {num: title for _, num, title in module_markers}

    for line_no, mod_num, topic_num, title in sorted(topic_markers):
        key = (mod_num, topic_num)
        if key in seen:
            # Update title if we found a better one
            if title and not boundaries[seen[key]]["topic_title"]:
                boundaries[seen[key]]["topic_title"] = title
            continue
        seen[key] = len(boundaries)
        boundaries.append({
            "module_num": mod_num,
            "module_title": module_titles.get(mod_num, ""),
            "topic_num": topic_num,
            "topic_title": title,
            "start_line": line_no,
        })

    # Fill in end_line for each boundary
    for i, b in enumerate(boundaries):
        if i + 1 < len(boundaries):
            b["end_line"] = boundaries[i + 1]["start_line"]
        else:
            b["end_line"] = len(lines)

    # Try to fill missing topic titles from early chunk content
    for b in boundaries:
        if b["topic_title"]:
            continue
        chunk_lines = lines[b["start_line"]:min(b["start_line"] + 50, b["end_line"])]
        for cl in chunk_lines:
            m = re.match(r"^#{1,6}\s+\*\*(?:TOPIC\s+\d+[:\s]+)?([A-Z][^*]+?)\*\*", cl)
            if m:
                candidate = m.group(1).strip()
                candidate = re.sub(r"\d+\s*DAY\s+PACING.*$", "", candidate, flags=re.IGNORECASE).strip()
                if not re.search(r"MODULE|OVERVIEW|PACING|Assessment|TEKS", candidate, re.IGNORECASE):
                    if len(candidate) > 3:
                        b["topic_title"] = candidate
                        break

    return boundaries


# ---------------------------------------------------------------------------
# System prompt (per-topic chunk)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = dedent("""\
You are a curriculum analyst extracting structured lesson data from a single
topic of a Carnegie Learning Bluebonnet Geometry teacher's edition that has
been converted from PDF to Markdown.

DOWNSTREAM USE
The output drives generation of student-style geometry diagram prompts.
COMPLETENESS of lesson and activity coverage is the highest priority.

TEXTBOOK STRUCTURE (within each topic)
  Topic → Lesson → Activity

Pedagogical sub-sections inside every lesson (NOT separate lessons):
  ENGAGE / Getting Started, DEVELOP / Activities, DEMONSTRATE / Talk the Talk,
  Objectives, Key Terms, Essential Question, Prepare, Worked Example,
  Practice, Assignment, Remember

A "lesson" is a numbered unit with a geometric title.
An "activity" is a numbered student task (e.g. "Activity 1.1").

WHAT TO INCLUDE
- Every lesson and activity in this topic. Be exhaustive.
- A "Talk the Talk" or "Getting Started" that involves drawing/constructing
  counts as an activity.

WHAT TO SKIP
- Meta sections (Acknowledgments, Instructional Design, Self-Reflection,
  Topic Summary, Assessment Summary).
- Duplicate content from PDF conversion (include each lesson once).

OUTPUT JSON SCHEMA
{
  "topic": {
    "number": "1",
    "title": "Geometry Reasoning",
    "geometric_focus": "1-2 sentence summary of the geometry concepts.",
    "lessons": [
      {
        "number": "1",
        "title": "Points, Lines, Planes, Rays, and Line Segments",
        "essential_question": "Why are points, lines, and planes foundational?",
        "objectives": ["..."],
        "key_terms": ["point", "line", "plane"],
        "activities": [
          {
            "number": "1.1",
            "title": "Planes",
            "description": "Students investigate planes and their properties.",
            "diagram_type": "points and planes",
            "concepts": ["plane", "coplanar points", "intersection"]
          }
        ]
      }
    ]
  }
}

RULES
- Return ONLY the JSON object. No prose, no markdown fences, no commentary.
- Use the textbook's own numbering.
- Concept tags should be SPECIFIC (e.g. "perpendicular bisector construction").
- Do not invent content. Extract only what is in the markdown.
- If the same lesson appears multiple times (PDF duplication), include it once.
""")

MIDDLE_GRADE_SYSTEM_PROMPT = dedent("""\
You are a curriculum analyst extracting GEOMETRY-RELATED content from a single
topic of a Carnegie Learning Bluebonnet middle-school math teacher's edition
(PDF converted to Markdown).

DOWNSTREAM USE
The output drives generation of student-style geometry diagram prompts.
ONLY extract geometry-related lessons. Skip everything else.

GEOMETRY TOPICS TO INCLUDE
Triangles, angles, circles, polygons, quadrilaterals, parallel/perpendicular
lines, congruence, similarity, symmetry, transformations (reflection, rotation,
translation, dilation), bisectors, midpoints, Pythagorean theorem, coordinate
plane geometry, area/perimeter/volume of geometric figures, constructions,
3D shapes (prisms, pyramids, cones, cylinders, spheres), nets, cross-sections.

SKIP: Pure algebra, number theory, ratios (unless applied to similar figures),
statistics, probability, financial literacy, function notation.

OUTPUT JSON SCHEMA
{
  "topic": {
    "number": "1",
    "title": "Shapes and Solids",
    "geometric_focus": "1-2 sentence summary of geometry concepts.",
    "lessons": [
      {
        "number": "1",
        "title": "Constructing Triangles Given Sides",
        "essential_question": "How can you determine ...?",
        "objectives": ["..."],
        "key_terms": ["triangle inequality", "..."],
        "activities": [
          {
            "number": "1.1",
            "title": "Pasta Triangles",
            "description": "Students construct triangles from pasta pieces.",
            "diagram_type": "triangle construction",
            "concepts": ["triangle inequality", "side lengths"]
          }
        ]
      }
    ]
  }
}

If this topic has NO geometry-related lessons, return:
{"topic": {"number": "...", "title": "...", "geometric_focus": "", "lessons": []}}

RULES
- Return ONLY the JSON object. No prose, no markdown fences.
- Use the textbook's own numbering.
- Concept tags should be SPECIFIC.
- Do not invent content. Extract only what is in the markdown.
""")


def _system_prompt_for(grade: str) -> str:
    if grade == "geometry":
        return SYSTEM_PROMPT
    return MIDDLE_GRADE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def _call_llm(
    client: anthropic.Anthropic,
    system: str,
    user_msg: str,
    label: str,
) -> dict:
    """Send a topic chunk to Sonnet and parse the JSON response."""
    t0 = time.time()

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )
    elapsed = time.time() - t0

    usage = response.usage
    print(
        f"  [{label}] {elapsed:.0f}s "
        f"in={usage.input_tokens:,} out={usage.output_tokens:,} "
        f"stop={response.stop_reason}"
    )

    text = response.content[0].text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        debug_path = CURRICULUM_DIR / f"{label}_raw.txt"
        debug_path.write_text(text)
        print(f"    ERROR parsing JSON: {e} (saved to {debug_path})")
        raise


def _extract_topic_chunk(
    client: anthropic.Anthropic,
    chunk: dict,
    lines: list[str],
    grade: str,
    volume: int,
) -> dict | None:
    """Extract structured data from a single topic chunk."""
    label = f"{grade}_vol{volume}_m{chunk['module_num']}_t{chunk['topic_num']}"
    topic_title = chunk.get("topic_title", "")

    if chunk["module_num"] in SKIP_MODULES or topic_title in SKIP_TOPICS:
        print(f"  [{label}] SKIP (non-geometry: {topic_title or 'Module ' + chunk['module_num']})")
        return None

    chunk_text = "\n".join(lines[chunk["start_line"]:chunk["end_line"]])
    chunk_tokens = len(chunk_text) // 4

    system = _system_prompt_for(grade)
    user_msg = (
        f"Grade: {grade}, Volume: {volume}\n"
        f"Module {chunk['module_num']}: {chunk['module_title']}\n"
        f"Topic {chunk['topic_num']}: {topic_title}\n\n"
        f"Extract all lessons and activities from this topic.\n\n---\n\n"
        f"{chunk_text}"
    )

    print(f"  [{label}] {topic_title or '?'} (~{chunk_tokens:,} tokens)...")

    try:
        result = _call_llm(client, system, user_msg, label)
        return {
            "module_num": chunk["module_num"],
            "module_title": chunk["module_title"],
            "result": result,
        }
    except Exception as e:
        print(f"    [{label}] FAILED: {e}")
        return None


# ---------------------------------------------------------------------------
# Volume-level orchestration
# ---------------------------------------------------------------------------

def _assemble_volume(
    grade: str,
    volume: int,
    chunk_results: list[dict],
) -> dict:
    """Merge per-topic results into a single volume structure."""
    modules: dict[str, dict] = {}

    for cr in chunk_results:
        mod_num = cr["module_num"]
        mod_title = cr["module_title"]
        topic_data = cr["result"].get("topic", cr["result"])

        if mod_num not in modules:
            modules[mod_num] = {
                "number": mod_num,
                "title": mod_title,
                "topics": [],
            }
        modules[mod_num]["topics"].append(topic_data)

    return {
        "grade": grade,
        "volume": volume,
        "modules": [modules[k] for k in sorted(modules)],
    }


def extract_volume(client: anthropic.Anthropic, stem: str, workers: int = MAX_WORKERS) -> dict:
    """Extract curriculum from a single volume by chunking at topic boundaries."""
    grade, volume = VOLUME_MAP[stem]
    md_path = MARKDOWN_DIR / f"{stem}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"{md_path} not found. Run convert_pdfs.py first.")

    print(f"\n=== {stem} ===")
    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    print(f"  {len(lines):,} lines ({len(text):,} chars)")

    chunks = _find_topic_chunks(lines)
    print(f"  Found {len(chunks)} topic chunks:")
    for c in chunks:
        size = c["end_line"] - c["start_line"]
        title = c.get("topic_title", "?")
        should_skip = c["module_num"] in SKIP_MODULES or title in SKIP_TOPICS
        skip = " [SKIP]" if should_skip else ""
        print(f"    M{c['module_num']} T{c['topic_num']}: {title} ({size:,} lines){skip}")

    # Extract each chunk in parallel
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_extract_topic_chunk, client, chunk, lines, grade, volume): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    assembled = _assemble_volume(grade, volume, results)
    _summarize(assembled)
    return assembled


def _summarize(result: dict) -> None:
    grade = result.get("grade", "?")
    vol = result.get("volume", "?")
    modules = result.get("modules", [])
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
    print(
        f"  Result: {grade} vol{vol} — {len(modules)} modules, {n_topics} topics, "
        f"{n_lessons} lessons, {n_activities} activities"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_targets(targets: list[str]) -> list[str]:
    stems: list[str] = []
    for t in targets:
        if t == "all":
            return sorted(VOLUME_MAP.keys())
        if t in VOLUME_MAP:
            stems.append(t)
        else:
            matches = sorted(s for s in VOLUME_MAP if s.startswith(t))
            if matches:
                stems.extend(matches)
            else:
                print(f"WARNING: unknown target '{t}', skipping")
    return stems


def main():
    parser = argparse.ArgumentParser(
        description="Extract geometry curriculum from textbook markdowns via LLM",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["geometry"],
        help=(
            "Volume stems (geometry_vol1), grade prefixes (geometry, 6th), "
            "or 'all'. Default: geometry"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show chunks and estimated costs without calling the API.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Max parallel API calls. Default: {MAX_WORKERS}",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_PATH),
        help=f"Output JSON path. Default: {OUTPUT_PATH}",
    )
    args = parser.parse_args()

    stems = _resolve_targets(args.targets)
    if not stems:
        print("No valid targets. Available:", ", ".join(sorted(VOLUME_MAP.keys())))
        sys.exit(1)

    print(f"Targets: {', '.join(stems)}")

    if args.dry_run:
        total_tokens = 0
        total_chunks = 0
        for stem in stems:
            grade, volume = VOLUME_MAP[stem]
            md_path = MARKDOWN_DIR / f"{stem}.md"
            if not md_path.exists():
                print(f"\n  {stem}: NOT FOUND")
                continue
            text = md_path.read_text(encoding="utf-8")
            lines = text.split("\n")
            chunks = _find_topic_chunks(lines)
            prompt_type = "full" if grade == "geometry" else "geo-filter"
            print(f"\n  {stem} [{prompt_type}]: {len(chunks)} chunks")
            for c in chunks:
                size = c["end_line"] - c["start_line"]
                chunk_chars = sum(len(lines[l]) for l in range(c["start_line"], c["end_line"]))
                tokens = chunk_chars // 4
                title = c.get("topic_title", "?")
                should_skip = c["module_num"] in SKIP_MODULES or title in SKIP_TOPICS
                skip = " [SKIP]" if should_skip else ""
                print(f"    M{c['module_num']} T{c['topic_num']}: {title} "
                      f"({size:,} lines, ~{tokens:,} tok){skip}")
                if not should_skip:
                    total_tokens += tokens
                    total_chunks += 1

        est_cost = total_tokens * 3 / 1_000_000
        print(f"\n{total_chunks} chunks, ~{total_tokens:,} input tokens, ~${est_cost:.2f}")
        return

    workers = args.workers

    # Load existing output for incremental extraction
    output_path = Path(args.output)
    existing: dict[str, dict] = {}
    if output_path.exists():
        try:
            data = json.loads(output_path.read_text())
            for entry in data.get("textbooks", []):
                g = entry.get("grade", "")
                v = entry.get("volume", 0)
                key = next(
                    (s for s, (eg, ev) in VOLUME_MAP.items() if eg == g and ev == v),
                    None,
                )
                if key and key not in stems:
                    existing[key] = entry
        except (json.JSONDecodeError, KeyError):
            pass

    client = anthropic.Anthropic()
    results: dict[str, dict] = dict(existing)

    t0 = time.time()
    for stem in stems:
        try:
            results[stem] = extract_volume(client, stem, workers=workers)
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
        except Exception as e:
            print(f"  ERROR extracting {stem}: {e}")
            raise

    elapsed = time.time() - t0

    textbooks = [
        results[s]
        for s in sorted(results, key=lambda s: (VOLUME_MAP[s][0], VOLUME_MAP[s][1]))
    ]
    out = {"textbooks": textbooks}
    output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 50}")
    print(f"Wrote {output_path} in {elapsed:.0f}s")
    total_lessons = 0
    total_activities = 0
    for tb in textbooks:
        _summarize(tb)
        for m in tb.get("modules", []):
            for t in m.get("topics", []):
                total_lessons += len(t.get("lessons", []))
                for l in t.get("lessons", []):
                    total_activities += len(l.get("activities", []))
    print(f"\nGrand total: {total_lessons} lessons, {total_activities} activities")


if __name__ == "__main__":
    main()
