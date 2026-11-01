"""Font configuration for diagram renderers."""
from __future__ import annotations

import base64
import functools
import os
import re
from dataclasses import dataclass
from pathlib import Path

FONT_VARIANTS = ("Regular", "Bold", "Italic", "BoldItalic")

_FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# The same family syntax the renderer container accepts.
FONT_FAMILY_RE = re.compile(r"[A-Za-z0-9_-]+")
DEFAULT_FONT_FAMILY = "NunitoSans"


@functools.lru_cache(maxsize=32)
def _read_data_uri(path: str, mtime_ns: int, size: int) -> str:
    """Base64 data URI of the font file at ``path``. ``mtime_ns`` and ``size``
    key the cache so an edited file is re-read."""
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:font/ttf;base64,{b64}"


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
        path = self.file_path(variant)
        st = path.stat()
        return _read_data_uri(str(path), st.st_mtime_ns, st.st_size)


def default_font_config() -> FontConfig:
    """Return the default FontConfig, reading DIAGRAM_FONT_FAMILY env var."""
    family = os.environ.get("DIAGRAM_FONT_FAMILY", "NunitoSans")
    return FontConfig(family=family)
