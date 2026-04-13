# Curriculum-Based Prompt Generation

Extract geometry curriculum structure from Carnegie Bluebonnet textbook PDFs,
then generate student-style diagram request prompts for the eval suite.

## Prerequisites

- The project `.venv` must exist (`uv sync` from repo root).
- `ANTHROPIC_API_KEY` must be set in the repo-root `.env` file.
- The textbook PDFs must be unzipped into `curriculum/textbooks/`. If the zip
  file is present but `curriculum/textbooks/Textbooks/` does not exist:

```bash
cd curriculum && mkdir -p textbooks && unzip Textbooks-*.zip -d textbooks/
```

## Pipeline

```
Step 1: convert_pdfs.py        PDF → Markdown        (marker-pdf, separate venv)
Step 2: extract_curriculum.py   Markdown → JSON        (Claude Sonnet, chunked by topic)
Step 3: generate_prompts.py     JSON → scenario YAML   (Claude Sonnet, chunked by topic)
```

### Step 1: Convert PDFs to Markdown

Uses [marker-pdf](https://github.com/datalab-to/marker) in its own virtualenv.

```bash
# One-time setup
uv venv curriculum/.marker-venv --python 3.11
uv pip install --python curriculum/.marker-venv 'marker-pdf>=1.10' pymupdf

# Run conversion (skips already-converted files)
curriculum/.marker-venv/bin/python curriculum/convert_pdfs.py
```

**Runtime:** 1-2 hours on Apple Silicon. Produces 8 markdown files in
`curriculum/markdown/`.

### Step 2: Extract curriculum via LLM

Splits each textbook volume into topic-sized chunks at logical chapter
boundaries, then sends each chunk to Claude Sonnet for structured extraction.
Chunks are processed in parallel (4 workers).

```bash
# Geometry textbook only (default, ~$3)
.venv/bin/python curriculum/extract_curriculum.py --targets geometry

# All textbooks (~$10)
.venv/bin/python curriculum/extract_curriculum.py --targets all

# Dry run — show chunks and cost estimate
.venv/bin/python curriculum/extract_curriculum.py --dry-run --targets all
```

**Output:** `curriculum/geometry_curriculum.json` — hierarchical JSON with
modules, topics, lessons, and activities. Each activity has `diagram_type`
and `concepts` tags. Incremental: re-running with new targets merges into
existing output.

### Step 3: Generate student diagram queries

Reads the extracted curriculum and generates student-style diagram request
prompts as eval scenarios. Also chunked by topic, processed in parallel.

```bash
# Generate scenarios
.venv/bin/python curriculum/generate_prompts.py

# Dry run
.venv/bin/python curriculum/generate_prompts.py --dry-run
```

**Output:**
- `evals/scenarios_geometry_curriculum.yaml` — eval runner format
- `curriculum/student_queries.md` — human-readable summary

Each scenario includes a natural-language prompt, required labels, and
verifiable geometric properties (right_angle, parallel, midpoint, etc.)
compatible with `evals/run.py`.

## Files

### Scripts (committed)
- `convert_pdfs.py` — Step 1: PDF → Markdown
- `extract_curriculum.py` — Step 2: Markdown → structured JSON
- `generate_prompts.py` — Step 3: JSON → student query scenarios

### Generated outputs (committed)
- `geometry_curriculum.md` — readable curriculum hierarchy
- `student_queries.md` — readable student diagram queries

### Gitignored (local only)
- `textbooks/` — extracted PDFs (~1GB)
- `markdown/` — converted Markdown files
- `.marker-venv/` — marker's virtualenv (~2GB)
- `geometry_curriculum.json` — LLM extraction output (intermediate)
- `Textbooks-*.zip` — source zip file
