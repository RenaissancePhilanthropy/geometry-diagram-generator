"""Font configuration for diagram renderers."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

FONT_VARIANTS = ("Regular", "Bold", "Italic", "BoldItalic")

_FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"


@dataclass
class FontConfig:
    family: str  # e.g. "NunitoSans"

    def url(self, variant: str) -> str:
        """URL path for browser @font-face src. Resolves when served by a UI web server."""
        return f"/fonts/{self.family}-{variant}.ttf"

    def file_path(self, variant: str) -> Path:
        """Absolute path to the TTF file in assets/fonts/."""
        return _FONTS_DIR / f"{self.family}-{variant}.ttf"

    def data_uri(self, variant: str) -> str:
        """Base64 data URI for embedding the font inline in an SVG @font-face src.

        Raises FileNotFoundError if the font file does not exist.
        """
        data = self.file_path(variant).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:font/ttf;base64,{b64}"


def default_font_config() -> FontConfig:
    """Return the default FontConfig, reading DIAGRAM_FONT_FAMILY env var."""
    family = os.environ.get("DIAGRAM_FONT_FAMILY", "NunitoSans")
    return FontConfig(family=family)
