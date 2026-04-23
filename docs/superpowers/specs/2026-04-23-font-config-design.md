# Font Configuration Design

**Date:** 2026-04-23
**Status:** Approved

## Summary

Add configurable font support to both the SVG and TikZ diagram renderers, defaulting to NunitoSans. Font files live in `assets/fonts/`, exposed to the browser via a symlink at `demo-ui/public/fonts/`. A `FontConfig` dataclass wraps a family name string; an env var sets the default; renderers accept it as an optional parameter.

## Font Files & Location

**First step:** Move the four `NunitoSans-*.ttf` files from the project root to `assets/fonts/` (creating the directory).

`assets/fonts/` is the canonical home for TTF files. Each UI's `public/fonts/` is a symlink → `../../assets/fonts/` (one step up to the project root, then into `assets/fonts/`). Each UI's `vite.config.js` must be updated with `resolve.preserveSymlinks: true` and `server.fs.allow: ['../..']` to let Vite follow the symlink during both dev and build.

```
assets/fonts/
  NunitoSans-Regular.ttf
  NunitoSans-Bold.ttf
  NunitoSans-Italic.ttf
  NunitoSans-BoldItalic.ttf
demo-ui/public/fonts       →  ../../assets/fonts   (symlink)
eval-viewer-ui/public/fonts →  ../../assets/fonts   (symlink)
benchmark-ui/public/fonts   →  ../../assets/fonts   (symlink)
```

All three UIs serve fonts at `/fonts/` in both dev (Vite) and prod (each UI's built `dist/` served by its respective FastAPI backend). URL-based `@font-face` references in SVG-renderer output therefore resolve correctly in all three UIs without font embedding.

Naming convention (required): `{Family}-{Variant}.ttf` where Variant ∈ `{Regular, Bold, Italic, BoldItalic}`. No validation is performed at runtime; a misconfigured family name silently falls back to the browser default (SVG) or causes a LaTeX compile error (TikZ).

## FontConfig (`ir/font.py`)

```python
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
        """URL path for browser @font-face src. Only valid in browser context."""
        return f"/fonts/{self.family}-{variant}.ttf"

    def file_path(self, variant: str) -> Path:
        """Absolute path to the TTF file on the host filesystem."""
        return _FONTS_DIR / f"{self.family}-{variant}.ttf"

    def data_uri(self, variant: str) -> str:
        """Base64 data URI for embedding the font inline in SVG @font-face src."""
        data = self.file_path(variant).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:font/ttf;base64,{b64}"

def default_font_config() -> FontConfig:
    family = os.environ.get("DIAGRAM_FONT_FAMILY", "NunitoSans")
    return FontConfig(family=family)
```

## SVG Renderer Changes (`ir/to_svg.py`)

### API

`SVGRenderer.__init__` gains `font_config: FontConfig | None = None` and `embed_fonts: bool = False`. When `font_config` is `None`, it calls `default_font_config()` at construction time and stores the result. The `render()` method passes both to the internal rendering function.

The top-level `ir_to_svg()` function gains the same `font_config: FontConfig | None = None` and `embed_fonts: bool = False` parameters.

### SVG output

Each generated SVG gets a `<defs><style>` block with `@font-face` rules for all four variants. The `src` value depends on `embed_fonts`:

**`embed_fonts=False` (default)** — URL reference, only resolves in browser context:
```xml
<defs>
  <style>
    @font-face { font-family: 'NunitoSans'; font-weight: normal; font-style: normal;
                 src: url('/fonts/NunitoSans-Regular.ttf'); }
    @font-face { font-family: 'NunitoSans'; font-weight: bold; font-style: normal;
                 src: url('/fonts/NunitoSans-Bold.ttf'); }
    @font-face { font-family: 'NunitoSans'; font-weight: normal; font-style: italic;
                 src: url('/fonts/NunitoSans-Italic.ttf'); }
    @font-face { font-family: 'NunitoSans'; font-weight: bold; font-style: italic;
                 src: url('/fonts/NunitoSans-BoldItalic.ttf'); }
  </style>
</defs>
```

**`embed_fonts=True`** — base64 data URI, self-contained, works in any context:
```xml
<defs>
  <style>
    @font-face { font-family: 'NunitoSans'; font-weight: normal; font-style: normal;
                 src: url('data:font/ttf;base64,AAEC...'); }
    ...
  </style>
</defs>
```

`FontConfig.data_uri(variant)` reads the file from `assets/fonts/` and returns the data URI string. If a font file is missing, `FileNotFoundError` propagates to the caller (no silent fallback).

All `font-family: "serif"` and `font-family: "sans-serif"` occurrences are replaced with the configured family name in both modes.

### Scope boundary

With `embed_fonts=False` (default): font resolution works via two independent paths:

1. **Web server context** (all three UIs): the `/fonts/...` URL in `@font-face` resolves because each UI serves fonts at `/fonts/`.
2. **System font** (browser file://, cairosvg, any other context): if NunitoSans is installed as a system font, browsers and cairo/pango find it by `font-family` name directly — no `@font-face` URL needed. `cairosvg` (`util/llm_judge.py`, `benchmark/ai_judge.py`) uses fontconfig and ignores `@font-face` URLs entirely.

Fallback to system default only occurs if NunitoSans is not system-installed *and* the SVG is viewed outside a web server (e.g. sent to someone who hasn't installed the font).

With `embed_fonts=True`: SVGs are fully self-contained regardless of system font installation. Use for distribution to external recipients. Trade-off: ~300 KB added per SVG (four TTF variants).

### `main.py` wiring

`_make_renderer()` constructs `SVGRenderer(font_config=default_font_config())`. `default_font_config()` reads `DIAGRAM_FONT_FAMILY` at construction time (not per-request); since `_make_renderer()` is called once at startup, the env var is effectively read once per server start.

## TikZ Renderer Changes

### Output mode: DVI → PDF

`fontspec` (required to load TTF fonts in LuaLaTeX) is incompatible with `--output-format=dvi`. The TikZ renderer therefore switches from the DVI pipeline to a PDF pipeline when a font is configured:

| Step | Current (DVI) | With font (PDF) |
|---|---|---|
| LaTeX class option | `[dvisvgm,border=0pt]` | `[border=0pt]` |
| lualatex invocation | `lualatex --output-format=dvi` | `lualatex` (PDF default) |
| dvisvgm invocation | `dvisvgm --no-fonts main.dvi` | `dvisvgm --no-fonts --pdf main.pdf` |

With `--no-fonts`, dvisvgm traces all glyph outlines (including NunitoSans) into SVG `<path>` elements. The SVG is fully portable — no font references, no browser font delivery needed. The font choice determines what the glyph *shapes* look like, which is the correct behaviour for the TikZ path.

Since the default font config is always populated (NunitoSans), the renderer always runs in PDF mode. The DVI code path can be removed.

### LaTeX template changes

```latex
\documentclass[border=0pt]{standalone}   % remove dvisvgm driver option
\usepackage{tikz}
\usepackage{luacode}
\usepackage{tkz-euclide}
\usepackage{tkz-elements}
\usepackage{amsmath}
\usepackage{fontspec}
\setmainfont{NunitoSans}[
  UprightFont    = *-Regular,
  BoldFont       = *-Bold,
  ItalicFont     = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Extension      = .ttf,
  Path           = /usr/local/share/fonts/NunitoSans/
]
```

The font family name and `Path` are derived from `font_family` in the request using `f"/usr/local/share/fonts/{font_family}/"`. When no `font_family` is provided, the default (`NunitoSans`) is used.

### Renderer API (`renderer/app/main.py`)

`RenderReq` gains `font_family: str | None = None`. In `render_svg()`, resolve `None` before template formatting: `family = req.font_family or "NunitoSans"`. The TEMPLATE string is parameterised by `family` and `f"/usr/local/share/fonts/{family}/"`.

### `renderer/Texlivefile`

Add `fontspec` to the package list.

### Dockerfile (`renderer/Dockerfile`)

Copy font files into the image and register them:

```dockerfile
COPY assets/fonts /usr/local/share/fonts/NunitoSans/
RUN fc-cache -fv
```

Note: the `COPY` source path is relative to the Docker build context. The build must be invoked from the **project root**: `docker build -f renderer/Dockerfile .` — this is a change from the previous invocation from `renderer/`. Add a `# Build from project root` comment to the Dockerfile and update any build scripts/CI accordingly.

### `util/tikz_renderer.py`

`render_tikz()` gains `font_family: str | None = None`. When provided, it is included in the request payload as `"font_family": font_family`.

### `ir/renderer.py`

`TikZRenderer.__init__` gains `font_config: FontConfig | None = None`, defaulting to `default_font_config()`. The `render()` method passes `font_config.family` to `render_tikz()` as `font_family`.

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `DIAGRAM_FONT_FAMILY` | `NunitoSans` | Diagram font family for both renderers |

## Out of Scope

- Demo-UI HTML/CSS font (chat interface) — deferred
- Multiple font weight variants beyond Regular/Bold/Italic/BoldItalic
- Variable fonts
- Font validation at `FontConfig` construction time
