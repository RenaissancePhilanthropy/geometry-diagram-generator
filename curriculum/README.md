# Curriculum-Based Prompt Generation

Generate eval scenario YAML files from Carnegie Bluebonnet textbook PDFs. The
pipeline extracts lesson structure, then uses Claude to produce student-style
geometry diagram prompts compatible with `evals/run.py`.

## Prerequisites

- The project `.venv` must exist (`uv sync` from repo root).
- `ANTHROPIC_API_KEY` must be set in the repo-root `.env` file.
- The textbook PDFs must be unzipped into `curriculum/textbooks/`. If the zip
  file `curriculum/Textbooks-20260406T162832Z-1-001.zip` is present but
  `curriculum/textbooks/Textbooks/` does not exist, unzip it first:

```bash
cd curriculum && mkdir -p textbooks && unzip Textbooks-20260406T162832Z-1-001.zip -d textbooks/
```

After unzipping, the structure should be:

```
curriculum/textbooks/Textbooks/
  bluebonnet6th/    # 2 PDFs (Vol 1, Vol 2)
  bluebonnet7th/    # 2 PDFs
  bluebonnet8th/    # 2 PDFs
  bluebonnetgeometry/  # 2 PDFs
```

## Pipeline overview

```
Step 1: convert_pdfs.py   — PDF → Markdown (via marker-pdf, separate venv)
Step 2: extract_topics.py — Markdown → topic_index.json (lesson structure)
Step 3: generate_prompts.py — topic_index.json → scenario YAML files (via Claude)
```

## Step 1: Convert PDFs to Markdown

This step uses [marker-pdf](https://github.com/datalab-to/marker) which
requires PyTorch and has dependency conflicts with the main project. It runs in
its own virtualenv at `curriculum/.marker-venv/`.

### 1a. Create the marker virtualenv (one-time setup)

```bash
uv venv curriculum/.marker-venv --python 3.11
uv pip install --python curriculum/.marker-venv 'marker-pdf>=1.10' pymupdf
```

### 1b. Run the conversion

```bash
curriculum/.marker-venv/bin/python curriculum/convert_pdfs.py
```

This converts all 8 PDFs to Markdown files in `curriculum/markdown/`. It runs
2 PDFs in parallel per batch, using CPU-only mode to avoid Apple Silicon MPS
crashes on large documents.

**Expected runtime:** 1-2 hours on Apple Silicon (M-series), longer on older
hardware. Each PDF is 700-1400 pages. The script skips already-converted files,
so it is safe to re-run if interrupted.

**Output:** 8 files in `curriculum/markdown/`:

```
6th_vol1.md, 6th_vol2.md
7th_vol1.md, 7th_vol2.md
8th_vol1.md, 8th_vol2.md
geometry_vol1.md, geometry_vol2.md
```

### Troubleshooting

- **MPS/torch errors on Apple Silicon:** The script forces `TORCH_DEVICE=cpu`.
  If it still crashes, try setting `batch_size = 1` in `convert_pdfs.py`.
- **Out of memory:** Reduce `batch_size` to 1 (sequential processing).
- **Partial conversion:** Just re-run; it skips files that already exist with
  size > 1KB.

## Step 2: Extract topics from Markdown

This parses the converted Markdown files, identifies lesson headings and their
content, and writes a structured index.

```bash
.venv/bin/python curriculum/extract_topics.py
```

**Output:** `curriculum/topic_index.json` — a JSON array of topic objects:

```json
[
  {
    "grade": "geometry",
    "volume": 1,
    "module": "MODULE 1 Reasoning with Shapes",
    "topic": "TOPIC 2 Using a Rectangular Coordinate System",
    "lesson_number": "3",
    "lesson_title": "Classifying Quadrilaterals on the Coordinate Plane",
    "sample_text": "First ~1500 chars of lesson content..."
  }
]
```

The extraction script:
- Splits Markdown by headings and tracks the current module/topic context.
- Matches lesson headings (`LESSON N Title` or `N Title` patterns).
- Skips non-lesson sections (introductions, summaries, test prep).
- Grabs ~1500 chars of lesson body text as context for prompt generation.

**If heading formats don't match well** (too few or too many lessons found),
adjust the regex patterns in `_extract_topics_from_markdown()`. Run with
`--dry-run` first to inspect what was found before calling Claude.

## Step 3: Generate eval scenario YAML

This calls Claude to produce student-style diagram prompts for each geometry
lesson, then validates them against the eval runner schema.

```bash
# Dry run first — shows what lessons will be processed, no API calls
.venv/bin/python curriculum/generate_prompts.py --dry-run

# Generate for all grades
.venv/bin/python curriculum/generate_prompts.py

# Generate for one grade only
.venv/bin/python curriculum/generate_prompts.py --grade geometry
```

**Output:** YAML files in `evals/`, one per grade:

```
evals/scenarios_6th.yaml
evals/scenarios_7th.yaml
evals/scenarios_8th.yaml
evals/scenarios_geometry.yaml
```

Each file is directly loadable by the eval runner:

```bash
uv run python -m evals.run --scenarios evals/scenarios_geometry.yaml --strategies structured
```

### How prompt generation works

For each topic in `topic_index.json`, the script sends the lesson title and
sample text to Claude with a system prompt that:

1. Asks for 2-5 student-style diagram requests per lesson.
2. Requires each scenario to include `id`, `tier`, `tags`, `prompt`,
   `required_labels`, and `expected_properties`.
3. Constrains `expected_properties` to the supported property types from
   `evals/scenarios.py` (right_angle, midpoint, parallel, etc.).
4. Instructs Claude to return `[]` for lessons with no diagram-worthy content
   (e.g., statistics, pure algebra).

Each generated scenario is validated against `_validate_scenarios()` before
being written. Invalid scenarios are logged and skipped.

### Cost estimate

~150 lessons across all textbooks, ~2-5 API calls each at ~1K tokens per
call. Total: roughly $1-3 in Claude API costs.

## What gets gitignored

The following are in `.gitignore` and should not be committed:

- `curriculum/textbooks/` — extracted PDFs (~1GB)
- `curriculum/markdown/` — converted Markdown files
- `curriculum/.marker-venv/` — marker's virtualenv (~2GB with PyTorch)
- `curriculum/topic_index.json` — intermediate extraction output

The generated YAML files in `evals/scenarios_*.yaml` **are** committed — they
are the deliverable.

## Filtering for geometry content

Not all lessons in the 6th-8th grade textbooks involve geometry. The pipeline
handles this at two levels:

1. **extract_topics.py** extracts all lessons. No filtering here — let Claude
   decide what is diagram-worthy.
2. **generate_prompts.py** tells Claude to return `[]` for non-geometry
   lessons. The system prompt explicitly says to skip pure algebra, statistics,
   financial literacy, etc.

If you want to pre-filter before calling Claude (to save API costs), add
keyword filtering in `extract_topics.py` or pass `--grade geometry` to only
process the geometry textbook.
