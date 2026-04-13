"""Convert all textbook PDFs to markdown using marker-pdf.

Runs conversions in parallel batches for speed.

Run with the marker venv:
    curriculum/.marker-venv/bin/python curriculum/convert_pdfs.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

CURRICULUM_DIR = Path(__file__).parent
TEXTBOOKS_DIR = CURRICULUM_DIR / "textbooks" / "Textbooks"
OUTPUT_DIR = CURRICULUM_DIR / "markdown"
MARKER_VENV_PYTHON = str(CURRICULUM_DIR / ".marker-venv" / "bin" / "python")

PDFS = [
    ("6th_vol1", "bluebonnet6th/Sixth Grade Teacher Edition, Vol 1.pdf"),
    ("6th_vol2", "bluebonnet6th/Sixth Grade Teacher Edition, Vol 2.pdf"),
    ("7th_vol1", "bluebonnet7th/Seventh Grade Math Teacher Edition, Volume 1.pdf"),
    ("7th_vol2", "bluebonnet7th/Seventh Grade Math Teacher Edition, Volume 2.pdf"),
    ("8th_vol1", "bluebonnet8th/Eighth Grade Math Teacher Edition, Volume 1.pdf"),
    ("8th_vol2", "bluebonnet8th/Eighth Grade Math Teacher Edition, Volume 2.pdf"),
    ("geometry_vol1", "bluebonnetgeometry/Teacher Edition, Volume 1.pdf"),
    ("geometry_vol2", "bluebonnetgeometry/Teacher Edition, Volume 2.pdf"),
]


def convert_one(label: str, rel_path: str) -> str:
    """Convert a single PDF. Runs in a subprocess to enable true parallelism."""
    out_file = OUTPUT_DIR / f"{label}.md"
    if out_file.exists() and out_file.stat().st_size > 1000:
        return f"SKIP {label} (already converted)"

    pdf_path = TEXTBOOKS_DIR / rel_path
    if not pdf_path.exists():
        return f"SKIP {label} (not found)"

    t0 = time.time()

    # Each subprocess loads its own models, avoiding GIL and memory contention.
    # Force CPU to avoid MPS crashes on Apple Silicon with large PDFs.
    script = f"""
import os, time, sys
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["TORCH_DEVICE"] = "cpu"

import torch
torch.set_default_device("cpu")

from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

models = create_model_dict()
converter = PdfConverter(artifact_dict=models)
rendered = converter("{pdf_path}")
Path("{out_file}").write_text(rendered.markdown, encoding="utf-8")
"""
    result = subprocess.run(
        [MARKER_VENV_PYTHON, "-c", script],
        capture_output=True,
        text=True,
        env={**subprocess.os.environ, "PYTORCH_ENABLE_MPS_FALLBACK": "1", "TORCH_DEVICE": "cpu"},
    )

    elapsed = time.time() - t0
    if result.returncode != 0:
        return f"FAIL {label} ({elapsed:.0f}s): {result.stderr[-500:]}"

    size_mb = out_file.stat().st_size / 1024 / 1024
    return f"DONE {label} ({elapsed:.0f}s, {size_mb:.1f} MB)"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Batch into groups of 2 (CPU mode uses more time but less memory per worker)
    batch_size = 2
    batches = [PDFS[i:i + batch_size] for i in range(0, len(PDFS), batch_size)]

    for batch_idx, batch in enumerate(batches):
        print(f"\n=== Batch {batch_idx + 1}/{len(batches)}: {[b[0] for b in batch]} ===")
        t0 = time.time()

        with ProcessPoolExecutor(max_workers=len(batch)) as pool:
            futures = {
                pool.submit(convert_one, label, rel_path): label
                for label, rel_path in batch
            }
            for future in as_completed(futures):
                label = futures[future]
                try:
                    msg = future.result()
                except Exception as e:
                    msg = f"ERROR {label}: {e}"
                print(f"  {msg}")

        print(f"  Batch took {time.time() - t0:.0f}s")

    print("\nAll conversions complete.")


if __name__ == "__main__":
    main()
