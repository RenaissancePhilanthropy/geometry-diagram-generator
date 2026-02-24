"""
Calls to @penrose/roger using npx to allow SVG generation on the backend.
More importantly, this allows for validating that a substance is valid without sending it to the frontend.
"""

from pathlib import Path
import subprocess
import os
import tempfile
from typing import Optional

def render_svg(substance: str, substance_name: Optional[str] = None, *, variation: Optional[str] = None) -> str:
    """
    Renders an SVG from a substance string using @penrose/roger.

    Args:
        substance: The substance string to render.
        substance_name: An optional name for the substance, used for error messages.
    Returns:
        The rendered SVG as a string.
    Raises:
        RuntimeError: If the rendering process fails.
    """

    substance_name = substance_name or "substance"
    project_root = Path(__file__).resolve().parent.parent
    demo_ui_dir = project_root / "demo-ui"
    style_file = "geometry.style"
    domain_file = "geometry.domain"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".substance",
        prefix="penrose-",
        dir=demo_ui_dir,
        delete=False,
    ) as temp_substance_file:
        temp_substance_file.write(substance)
        substance_file = Path(temp_substance_file.name)

    try:
        cmd = [
            "npx",
            "@penrose/roger",
            "trio",
            "--path",
            str(demo_ui_dir),
        ]
        if variation is not None:
            cmd += ["--variation", variation]
        cmd += [
            "--trio",
            style_file,
            domain_file,
            substance_file.name,
        ]
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            error_message = (
                f"Failed to render {substance_name}: Process exited with code "
                f"{result.returncode}. {details}"
            )
            raise RuntimeError(error_message)

        combined_output = (result.stdout or "") + (result.stderr or "")
        start = combined_output.find("<svg")
        end = combined_output.rfind("</svg>")
        if start == -1 or end == -1:
            details = combined_output.strip()
            error_message = (
                f"Failed to render {substance_name}: roger produced no SVG output. "
                f"Output: {details}"
            )
            raise RuntimeError(error_message)

        svg_content = combined_output[start:end + len("</svg>")]
        return svg_content
    finally:
        try:
            os.remove(substance_file)
        except OSError:
            pass