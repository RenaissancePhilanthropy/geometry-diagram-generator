# Font Configuration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable NunitoSans font support to both SVG and TikZ diagram renderers, served via all three Vite UIs.

**Architecture:** `ir/font.py` defines `FontConfig(family: str)` with URL and embed helpers; `SVGRenderer` injects `@font-face` into SVG `<defs>`; `TikZRenderer` switches from DVI→PDF pipeline and adds `fontspec` to LaTeX; all three UIs serve fonts via `public/fonts` symlinks into `assets/fonts/`.

**Tech Stack:** Python dataclasses, xml.etree.ElementTree (SVG), Vite symlinks, LuaLaTeX + fontspec, dvisvgm PDF mode.

---

## Chunk 1: Font infrastructure and FontConfig

### Task 1: Move font files and create symlinks

**Files:**
- Create: `assets/fonts/` (directory)
- Move: `NunitoSans-*.ttf` from project root → `assets/fonts/`
- Create: `demo-ui/public/fonts` → `../../assets/fonts` (symlink)
- Create: `eval-viewer-ui/public/` (directory, if not exists)
- Create: `eval-viewer-ui/public/fonts` → `../../assets/fonts` (symlink)
- Create: `benchmark-ui/public/` (directory, if not exists)
- Create: `benchmark-ui/public/fonts` → `../../assets/fonts` (symlink)

- [ ] **Step 1: Create `assets/fonts/` and move the font files**

```bash
mkdir -p assets/fonts
mv NunitoSans-Regular.ttf NunitoSans-Bold.ttf NunitoSans-Italic.ttf NunitoSans-BoldItalic.ttf assets/fonts/
ls assets/fonts/
```

Expected output:
```
NunitoSans-Bold.ttf  NunitoSans-BoldItalic.ttf  NunitoSans-Italic.ttf  NunitoSans-Regular.ttf
```

- [ ] **Step 2: Create `public/fonts` symlinks for all three UIs**

```bash
# demo-ui already has public/ dir (checked); create for others
mkdir -p eval-viewer-ui/public benchmark-ui/public
ln -s ../../assets/fonts demo-ui/public/fonts
ln -s ../../assets/fonts eval-viewer-ui/public/fonts
ln -s ../../assets/fonts benchmark-ui/public/fonts
ls -la demo-ui/public/fonts eval-viewer-ui/public/fonts benchmark-ui/public/fonts
```

Expected: each resolves to `../../assets/fonts` and lists the four TTF files.

- [ ] **Step 3: Commit**

```bash
git add assets/fonts demo-ui/public/fonts eval-viewer-ui/public benchmark-ui/public
git commit -m "chore: move font files to assets/fonts, add public/fonts symlinks for all UIs"
```

---

### Task 2: Update Vite configs to follow symlinks

**Files:**
- Modify: `demo-ui/vite.config.js`
- Modify: `eval-viewer-ui/vite.config.js`
- Modify: `benchmark-ui/vite.config.js`

- [ ] **Step 1: Update `demo-ui/vite.config.js`**

Replace the entire file content:

```js
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    preserveSymlinks: true,
  },
  server: {
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 2: Update `eval-viewer-ui/vite.config.js`**

```js
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    preserveSymlinks: true,
  },
  server: {
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8002',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: Update `benchmark-ui/vite.config.js`**

```js
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: {
    preserveSymlinks: true,
  },
  server: {
    fs: {
      allow: ['../..'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8004',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: Verify fonts are accessible in dev server (manual check)**

Start `cd demo-ui && pnpm dev`, then open `http://localhost:5173/fonts/NunitoSans-Regular.ttf` in a browser. Expected: font file downloads (or browser shows binary content). Kill the dev server.

- [ ] **Step 5: Commit**

```bash
git add demo-ui/vite.config.js eval-viewer-ui/vite.config.js benchmark-ui/vite.config.js
git commit -m "chore: configure Vite symlink support and fs.allow for font serving"
```

---

### Task 3: Create `ir/font.py`

**Files:**
- Create: `ir/font.py`
- Create: `tests/test_font_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_font_config.py`:

```python
"""Tests for ir/font.py FontConfig."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ir.font import FontConfig, FONT_VARIANTS, default_font_config, _FONTS_DIR


def test_font_variants_tuple():
    assert FONT_VARIANTS == ("Regular", "Bold", "Italic", "BoldItalic")


def test_font_config_url():
    cfg = FontConfig(family="NunitoSans")
    assert cfg.url("Regular") == "/fonts/NunitoSans-Regular.ttf"
    assert cfg.url("Bold") == "/fonts/NunitoSans-Bold.ttf"
    assert cfg.url("Italic") == "/fonts/NunitoSans-Italic.ttf"
    assert cfg.url("BoldItalic") == "/fonts/NunitoSans-BoldItalic.ttf"


def test_font_config_url_custom_family():
    cfg = FontConfig(family="MyFont")
    assert cfg.url("Regular") == "/fonts/MyFont-Regular.ttf"


def test_font_config_file_path():
    cfg = FontConfig(family="NunitoSans")
    p = cfg.file_path("Regular")
    assert p == _FONTS_DIR / "NunitoSans-Regular.ttf"
    assert isinstance(p, Path)


def test_font_config_data_uri(tmp_path):
    # Write a fake font file and patch _FONTS_DIR
    fake_ttf = b"\x00\x01\x02\x03fake font data"
    family = "TestFont"
    (tmp_path / f"{family}-Regular.ttf").write_bytes(fake_ttf)

    cfg = FontConfig(family=family)
    with patch("ir.font._FONTS_DIR", tmp_path):
        uri = cfg.data_uri("Regular")

    expected_b64 = base64.b64encode(fake_ttf).decode("ascii")
    assert uri == f"data:font/ttf;base64,{expected_b64}"


def test_font_config_data_uri_missing_file():
    cfg = FontConfig(family="DoesNotExist")
    with pytest.raises(FileNotFoundError):
        cfg.data_uri("Regular")


def test_default_font_config_default():
    with patch.dict(os.environ, {}, clear=True):
        cfg = default_font_config()
    assert cfg.family == "NunitoSans"


def test_default_font_config_env_override():
    with patch.dict(os.environ, {"DIAGRAM_FONT_FAMILY": "Roboto"}):
        cfg = default_font_config()
    assert cfg.family == "Roboto"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_font_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'ir.font'`

- [ ] **Step 3: Create `ir/font.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_font_config.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ir/font.py tests/test_font_config.py
git commit -m "feat: add FontConfig dataclass and default_font_config()"
```

---

## Chunk 2: SVG renderer font injection

### Task 4: Add `@font-face` injection to `ir_to_svg()`

**Files:**
- Modify: `ir/to_svg.py` (signature + defs injection)
- Modify: `tests/test_to_svg.py` (new font tests)

The `ir_to_svg()` function starts at line 87. It builds a `defs` element at line 160. We will:
1. Add `font_config` and `embed_fonts` parameters to `ir_to_svg()`
2. After the existing marker `<defs>` block, append a `<style>` element with `@font-face` rules

- [ ] **Step 1: Write failing tests for font injection**

Add to `tests/test_to_svg.py`:

```python
from ir.font import FontConfig


def test_svg_has_font_face_defs():
    """SVG output includes @font-face rules in <defs><style>."""
    diagram = DiagramIR(define=[PointFixed(id="A", x=0, y=0)],
                        render=[DrawPoints(ids=["A"])])
    sym = compile_defs(diagram)
    cfg = FontConfig(family="NunitoSans")
    svg_str = ir_to_svg(diagram, sym, font_config=cfg)
    assert "@font-face" in svg_str
    assert "NunitoSans-Regular.ttf" in svg_str
    assert "NunitoSans-Bold.ttf" in svg_str


def test_svg_font_family_attribute():
    """Text elements use the configured font family."""
    diagram = DiagramIR(
        define=[PointFixed(id="A", x=0, y=0)],
        render=[LabelPoint(id="A", label="A")],
    )
    sym = compile_defs(diagram)
    cfg = FontConfig(family="NunitoSans")
    svg_str = ir_to_svg(diagram, sym, font_config=cfg)
    assert 'font-family' in svg_str
    # Should not contain old hardcoded families
    assert '"serif"' not in svg_str
    assert '"sans-serif"' not in svg_str
    assert "NunitoSans" in svg_str


def test_svg_embed_fonts_uses_data_uri(tmp_path, monkeypatch):
    """embed_fonts=True uses data: URIs instead of URL paths."""
    import ir.font as font_mod
    fake_ttf = b"\x00fake"
    font_dir = tmp_path
    for variant in ("Regular", "Bold", "Italic", "BoldItalic"):
        (font_dir / f"NunitoSans-{variant}.ttf").write_bytes(fake_ttf)
    monkeypatch.setattr(font_mod, "_FONTS_DIR", font_dir)

    diagram = DiagramIR(define=[PointFixed(id="A", x=0, y=0)],
                        render=[DrawPoints(ids=["A"])])
    sym = compile_defs(diagram)
    cfg = FontConfig(family="NunitoSans")
    svg_str = ir_to_svg(diagram, sym, font_config=cfg, embed_fonts=True)
    assert "data:font/ttf;base64," in svg_str
    assert "/fonts/NunitoSans" not in svg_str


def test_svg_no_font_config_uses_default():
    """Passing font_config=None uses default_font_config() (NunitoSans)."""
    diagram = DiagramIR(define=[PointFixed(id="A", x=0, y=0)],
                        render=[DrawPoints(ids=["A"])])
    sym = compile_defs(diagram)
    svg_str = ir_to_svg(diagram, sym)
    assert "NunitoSans" in svg_str
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_to_svg.py::test_svg_has_font_face_defs tests/test_to_svg.py::test_svg_font_family_attribute tests/test_to_svg.py::test_svg_embed_fonts_uses_data_uri tests/test_to_svg.py::test_svg_no_font_config_uses_default -v
```

Expected: FAIL (TypeError on unexpected keyword argument `font_config`).

- [ ] **Step 3: Update `ir_to_svg()` signature**

In `ir/to_svg.py`, update the `ir_to_svg` function signature at line 87:

Old:
```python
def ir_to_svg(
    diagram: ir.DiagramIR,
    sym: SymTable,
    warnings: list[str] | None = None,
) -> str:
```

New:
```python
def ir_to_svg(
    diagram: ir.DiagramIR,
    sym: SymTable,
    warnings: list[str] | None = None,
    font_config: "FontConfig | None" = None,
    embed_fonts: bool = False,
) -> str:
```

Also add the import at the top of `ir/to_svg.py` (after the existing imports):

```python
from ir.font import FontConfig, FONT_VARIANTS, default_font_config
```

And at the start of the function body, resolve `None`:

```python
if font_config is None:
    font_config = default_font_config()
```

- [ ] **Step 4: Inject `@font-face` into `<defs>`**

Inject after line 180 (after the `marker_start` path element, immediately before the `# White background` comment at line 182). The `defs` variable is still in scope there. Append a `<style>` child to `defs`:

```python
# Font @font-face declarations
_FONT_WEIGHTS = {
    "Regular":    ("normal", "normal"),
    "Bold":       ("bold",   "normal"),
    "Italic":     ("normal", "italic"),
    "BoldItalic": ("bold",   "italic"),
}
font_rules = []
for variant in FONT_VARIANTS:
    weight, style = _FONT_WEIGHTS[variant]
    src = font_config.data_uri(variant) if embed_fonts else font_config.url(variant)
    font_rules.append(
        f"@font-face {{ font-family: '{font_config.family}'; "
        f"font-weight: {weight}; font-style: {style}; "
        f"src: url('{src}'); }}"
    )
style_el = ET.SubElement(defs, "style")
style_el.text = "\n    ".join([""] + font_rules + [""])
```

- [ ] **Step 5: Run tests to confirm font injection passes**

```bash
.venv/bin/python -m pytest tests/test_to_svg.py::test_svg_has_font_face_defs tests/test_to_svg.py::test_svg_embed_fonts_uses_data_uri tests/test_to_svg.py::test_svg_no_font_config_uses_default -v
```

Expected: PASS. `test_svg_font_family_attribute` still fails (family names not yet replaced).

- [ ] **Step 6: Commit partial progress**

```bash
git add ir/to_svg.py tests/test_to_svg.py ir/font.py
git commit -m "feat: inject @font-face rules into SVG <defs>, add embed_fonts option"
```

---

### Task 5: Replace hardcoded font families in SVG output

**Files:**
- Modify: `ir/to_svg.py` (4 occurrences of `serif`/`sans-serif`)

There are 4 occurrences to replace (lines 914, 1233, 1244, 1263, 1279 — the last two are `sans-serif` for axis tick labels).

- [ ] **Step 1: Add `font_family: str` parameter to `_append_label`**

`_append_label` is a module-level function at line 900. Add `font_family: str = "serif"` as the last parameter and replace the hardcoded `"serif"` at line 914:

```python
def _append_label(
    svg: ET.Element,
    x: float,
    y: float,
    text: str,
    color: str,
    anchor: str = "middle",
    extra_attrs: dict[str, str] | None = None,
    font_family: str = "serif",
) -> None:
    """Append a <text> element with LaTeX-to-SVG tspan conversion."""
    el = ET.SubElement(svg, "text", {
        **(extra_attrs or {}),
        "x": f"{x:.2f}",
        "y": f"{y:.2f}",
        "font-family": font_family,    # was "serif"
        "font-size": str(_FONT_SIZE),
        "fill": color,
        "text-anchor": anchor,
        "dominant-baseline": "central",
    })
```

- [ ] **Step 2: Add `font_family: str` parameter to `_append_axes` and replace all four occurrences**

`_append_axes` (line 1202) has four `font-family` attributes to replace — all should become `font_family`. Add the parameter:

```python
def _append_axes(
    svg: ET.Element,
    canvas: ir.Canvas,
    xmin: float, xmax: float, ymin: float, ymax: float,
    gxy,
    scale: float,
    font_family: str = "serif",
) -> None:
```

Then replace:
- Line 1233: `"font-family": "serif"` → `"font-family": font_family` (x-axis letter label)
- Line 1244: `"font-family": "serif"` → `"font-family": font_family` (y-axis letter label)
- Line 1263: `"font-family": "sans-serif"` → `"font-family": font_family` (x tick numbers)
- Line 1279: `"font-family": "sans-serif"` → `"font-family": font_family` (y tick numbers)

- [ ] **Step 3: Update all call sites in `ir_to_svg()`**

`_append_axes` is called once at line 195:
```python
_append_axes(svg, canvas, xmin, xmax, ymin, ymax, gxy, scale,
             font_family=font_config.family)
```

`_append_label` is called at lines 259, 632, 661, 695, and 719. Add `font_family=font_config.family` to each:
```python
_append_label(svg, lp.x, lp.y, lp.text, lp.color,
              anchor=lp.anchor, extra_attrs=lp.attrs,
              font_family=font_config.family)
```

- [ ] **Step 4: Run the font family test**

```bash
.venv/bin/python -m pytest tests/test_to_svg.py::test_svg_font_family_attribute -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite to catch regressions**

```bash
.venv/bin/python -m pytest tests/test_to_svg.py -v
```

Expected: all existing tests PASS (font change is visual-only, no geometry change).

- [ ] **Step 6: Commit**

```bash
git add ir/to_svg.py
git commit -m "feat: replace hardcoded serif/sans-serif with configured font family in SVG output"
```

---

### Task 6: Wire `FontConfig` into `SVGRenderer` and `TikZRenderer` in `ir/renderer.py`

**Files:**
- Modify: `ir/renderer.py`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_renderer.py` (check the existing file first to match its style):

```python
from ir.font import FontConfig, default_font_config
from ir.renderer import SVGRenderer, TikZRenderer


def test_svg_renderer_default_font_config():
    """SVGRenderer stores a FontConfig, defaulting to NunitoSans."""
    r = SVGRenderer()
    assert r._font_config.family == "NunitoSans"


def test_svg_renderer_custom_font_config():
    cfg = FontConfig(family="Roboto")
    r = SVGRenderer(font_config=cfg)
    assert r._font_config.family == "Roboto"


def test_tikz_renderer_default_font_config():
    r = TikZRenderer()
    assert r._font_config.family == "NunitoSans"


def test_tikz_renderer_custom_font_config():
    cfg = FontConfig(family="Roboto")
    r = TikZRenderer(font_config=cfg)
    assert r._font_config.family == "Roboto"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_renderer.py::test_svg_renderer_default_font_config tests/test_renderer.py::test_svg_renderer_custom_font_config tests/test_renderer.py::test_tikz_renderer_default_font_config tests/test_renderer.py::test_tikz_renderer_custom_font_config -v
```

Expected: FAIL (TypeError — `SVGRenderer.__init__` doesn't accept `font_config`).

- [ ] **Step 3: Update `SVGRenderer` in `ir/renderer.py`**

```python
from ir.font import FontConfig, default_font_config

class SVGRenderer(Renderer):
    """Renders DiagramIR → SVG directly from SymPy geometry, no LaTeX needed."""

    def __init__(
        self,
        font_config: FontConfig | None = None,
        embed_fonts: bool = False,
    ) -> None:
        self._font_config = font_config if font_config is not None else default_font_config()
        self._embed_fonts = embed_fonts

    def render(
        self,
        diagram: DiagramIR,
        sym: SymTable,
        warnings: list[str] | None = None,
    ) -> RenderResult:
        from ir.to_svg import ir_to_svg
        svg = ir_to_svg(
            diagram, sym,
            warnings=warnings,
            font_config=self._font_config,
            embed_fonts=self._embed_fonts,
        )
        return RenderResult(output=svg, format="svg", intermediate="")
```

- [ ] **Step 4: Update `TikZRenderer` in `ir/renderer.py`**

```python
class TikZRenderer(Renderer):
    """Renders DiagramIR → TikZ code → SVG via the LaTeX Docker container."""

    def __init__(
        self,
        renderer_url: str | None = None,
        font_config: FontConfig | None = None,
    ) -> None:
        self._url = renderer_url
        self._font_config = font_config if font_config is not None else default_font_config()

    def render(
        self,
        diagram: DiagramIR,
        sym: SymTable,
        warnings: list[str] | None = None,
    ) -> RenderResult:
        from ir.to_tikz import ir_to_tikz
        from util.tikz_renderer import render_tikz

        tikz = ir_to_tikz(diagram, sym, warnings=warnings)
        svg = render_tikz(tikz, renderer_url=self._url, font_family=self._font_config.family)
        return RenderResult(output=svg, format="svg", intermediate=tikz)

    def check_health(self) -> bool:
        from util.tikz_renderer import check_renderer_health
        return check_renderer_health(self._url)
```

- [ ] **Step 5: Update `main.py` to pass font config to renderers**

In `main.py`, the `_make_renderer()` function constructs `SVGRenderer()` and `TikZRenderer()`. They now call `default_font_config()` internally, so no change is required in `main.py`. Verify by reading `_make_renderer()` — if it constructs renderers with no font args, it's already correct.

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python -m pytest tests/test_renderer.py -v
```

Expected: all tests including the four new ones PASS.

- [ ] **Step 7: Run the full test suite**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_agent_e2e.py --ignore=tests/test_tikz_renderer.py --ignore=tests/test_tikz_analysis_integration.py --ignore=tests/test_svg_checks_integration.py
```

Expected: all non-integration tests PASS.

- [ ] **Step 8: Commit**

```bash
git add ir/renderer.py tests/test_renderer.py
git commit -m "feat: wire FontConfig into SVGRenderer and TikZRenderer"
```

---

## Chunk 3: TikZ renderer — Docker pipeline changes

### Task 7: Add `font_family` to `util/tikz_renderer.py`

**Files:**
- Modify: `util/tikz_renderer.py`
- Modify: `tests/test_tikz_renderer_unit.py`

- [ ] **Step 1: Check existing unit tests**

```bash
head -60 tests/test_tikz_renderer_unit.py
```

Understand the test style before adding new tests.

- [ ] **Step 2: Write failing tests**

Add to `tests/test_tikz_renderer_unit.py` (matching the existing `patch("httpx.post", ...)` pattern):

```python
def test_includes_font_family_in_payload():
    """font_family is included in the POST payload when provided."""
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\draw (0,0)--(1,1);", font_family="Roboto")
    payload = mock_post.call_args[1]["json"]
    assert payload["font_family"] == "Roboto"


def test_omits_font_family_when_none():
    """font_family is omitted from the POST payload when not provided."""
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        render_tikz(r"\draw (0,0)--(1,1);")
    payload = mock_post.call_args[1]["json"]
    assert "font_family" not in payload
```

- [ ] **Step 3: Update `render_tikz()` signature and payload**

In `util/tikz_renderer.py`, update `render_tikz()`:

Old signature:
```python
def render_tikz(
    tikz: str,
    *,
    tkzelements: str | None = None,
    renderer_url: str | None = None,
) -> str:
```

New:
```python
def render_tikz(
    tikz: str,
    *,
    tkzelements: str | None = None,
    renderer_url: str | None = None,
    font_family: str | None = None,
) -> str:
```

And in the payload construction:
```python
payload: dict = {"tikz": tikz}
if tkzelements:
    payload["tkzelements"] = tkzelements
if font_family:
    payload["font_family"] = font_family
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/test_tikz_renderer_unit.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add util/tikz_renderer.py tests/test_tikz_renderer_unit.py
git commit -m "feat: add font_family param to render_tikz()"
```

---

### Task 8: Update renderer Docker app — switch DVI→PDF, add fontspec

**Files:**
- Modify: `renderer/app/main.py`
- Modify: `renderer/Texlivefile`
- Modify: `renderer/Dockerfile`

- [ ] **Step 1: Add `fontspec` to `renderer/Texlivefile`**

Append `fontspec` to the file:

```
amsmath
dvisvgm
standalone
pgf
luacode
tkz-euclide
tkz-elements
fontspec
```

- [ ] **Step 2: Update `renderer/Dockerfile`**

Add font copy and cache steps, and update the build context note.

After the existing `COPY app /srv/app` line, add:

The base image (`reitzig/texlive-base-luatex`) is Alpine-based; install `fontconfig` if `fc-cache` is not already present. Place these lines after the existing `RUN pip install ...` line and before `WORKDIR /srv`:

```dockerfile
# Build from project root: docker build -f renderer/Dockerfile .
RUN apk add --no-cache fontconfig
COPY assets/fonts /usr/local/share/fonts/NunitoSans/
RUN fc-cache -fv
```

- [ ] **Step 3: Update `renderer/app/main.py` — add `font_family` to `RenderReq`**

```python
class RenderReq(BaseModel):
    tikz: str
    tkzelements: str | None = None
    font_family: str | None = None
```

- [ ] **Step 4: Update the LaTeX TEMPLATE in `renderer/app/main.py`**

Replace the current TEMPLATE with a parameterised version. Change the template string to accept `font_family` and `font_path` format fields, and update `render_svg()` to resolve and inject them:

```python
TEMPLATE = r"""
\documentclass[border=0pt]{{standalone}}
\usepackage{{tikz}}
\usepackage{{luacode}}
\usepackage{{tkz-euclide}}
\usepackage{{tkz-elements}}
\usepackage{{amsmath}}
\usepackage{{fontspec}}
\setmainfont{{{font_family}}}[
  UprightFont    = *-Regular,
  BoldFont       = *-Bold,
  ItalicFont     = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Extension      = .ttf,
  Path           = {font_path}
]
\begin{{document}}
{tkzelements_block}
\begin{{tikzpicture}}
{tikz}
\end{{tikzpicture}}
\end{{document}}
""".lstrip()
```

In `render_svg()`, resolve the family before formatting. The existing `tkze` construction (the `\begin{tkzelements}...` block from `req.tkzelements`) is unchanged — just add the two new variables and update the `.format()` call:

```python
family = req.font_family or "NunitoSans"
font_path = f"/usr/local/share/fonts/{family}/"
tex = TEMPLATE.format(
    font_family=family,
    font_path=font_path,
    tkzelements_block=tkze,   # existing variable, unchanged
    tikz=req.tikz,
)
```

- [ ] **Step 5: Switch lualatex to PDF mode in `render_svg()`**

Old:
```python
p1 = run_cmd([
    "lualatex",
    "--output-format=dvi",
    "--interaction=nonstopmode",
    "--halt-on-error",
    "-file-line-error",
    "main.tex",
], cwd=td)
```

New (remove `--output-format=dvi`):
```python
p1 = run_cmd([
    "lualatex",
    "--interaction=nonstopmode",
    "--halt-on-error",
    "-file-line-error",
    "main.tex",
], cwd=td)
```

- [ ] **Step 6: Switch dvisvgm to PDF mode**

Old:
```python
p2 = run_cmd([
    "dvisvgm",
    "--no-fonts",
    "--bbox=min",
    "--exact-bbox",
    "-Oall",
    "-o", "out.svg",
    "main.dvi",
], cwd=td)
```

New (use `--pdf` and `main.pdf`):
```python
p2 = run_cmd([
    "dvisvgm",
    "--no-fonts",
    "--pdf",
    "--bbox=min",
    "--exact-bbox",
    "-Oall",
    "-o", "out.svg",
    "main.pdf",
], cwd=td)
```

The file-existence check at the end of the render pipeline checks for `out.svg` — no change needed there.

- [ ] **Step 7: Rebuild Docker image and smoke test**

```bash
# From project root:
docker build -f renderer/Dockerfile . -t tikz-renderer
docker run -d -p 8001:8001 --name tikz-test tikz-renderer
sleep 3
curl -s http://localhost:8001/health
```

Expected: `{"status":"ok"}`

Then test a render:
```bash
curl -s -X POST http://localhost:8001/render \
  -H "Content-Type: application/json" \
  -d '{"tikz": "\\draw (0,0) -- (1,1);"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d['ok'] else d['log'][:200])"
```

Expected: `ok`

Then test with a font label:
```bash
curl -s -X POST http://localhost:8001/render \
  -H "Content-Type: application/json" \
  -d '{"tikz": "\\node at (0,0) {Hello NunitoSans};"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d['ok'] else d['log'][:500])"
```

Expected: `ok`

Then test with explicit `font_family` field to confirm wiring (not just the default fallback):
```bash
curl -s -X POST http://localhost:8001/render \
  -H "Content-Type: application/json" \
  -d '{"tikz": "\\node at (0,0) {Test};", "font_family": "NunitoSans"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d['ok'] else d['log'][:500])"
```

Expected: `ok`

```bash
docker stop tikz-test && docker rm tikz-test
```

- [ ] **Step 8: Commit**

```bash
git add renderer/Dockerfile renderer/Texlivefile renderer/app/main.py
git commit -m "feat: switch TikZ renderer to PDF pipeline with fontspec/NunitoSans support"
```

---

### Task 9: Final integration check

- [ ] **Step 1: Run the full unit test suite**

```bash
.venv/bin/python -m pytest tests/ -v \
  --ignore=tests/test_agent_e2e.py \
  --ignore=tests/test_tikz_renderer.py \
  --ignore=tests/test_tikz_analysis_integration.py \
  --ignore=tests/test_svg_checks_integration.py
```

Expected: all tests PASS.

- [ ] **Step 2: SVG renderer smoke test**

```python
# Run from project root with .venv activated
from ir.ir import DiagramIR, PointFixed, Segment, DrawPoints, Draw, LabelPoint
from ir.to_sympy import compile_defs
from ir.to_svg import ir_to_svg

diagram = DiagramIR(
    define=[PointFixed(id="A", x=0, y=0), PointFixed(id="B", x=3, y=4)],
    render=[Draw(ids=["AB"]), DrawPoints(ids=["A", "B"]), LabelPoint(id="A", label="A"), LabelPoint(id="B", label="B")],
)
sym = compile_defs(diagram)
svg = ir_to_svg(diagram, sym)
assert "NunitoSans" in svg
assert "@font-face" in svg
print("SVG renderer: OK")
```

Run as:
```bash
.venv/bin/python -c "
from ir.ir import DiagramIR, PointFixed, DrawPoints, LabelPoint
from ir.to_sympy import compile_defs
from ir.to_svg import ir_to_svg
diagram = DiagramIR(define=[PointFixed(id='A', x=0, y=0)], render=[DrawPoints(ids=['A']), LabelPoint(id='A', label='A')])
sym = compile_defs(diagram)
svg = ir_to_svg(diagram, sym)
assert 'NunitoSans' in svg and '@font-face' in svg
print('SVG renderer: OK')
"
```

- [ ] **Step 3: Commit any remaining changes and tag**

```bash
git add -p  # review anything unstaged
git commit -m "chore: font config integration complete" --allow-empty
```

---

## Notes

- **Docker build context changed:** The Docker image must now be built from the project root (`docker build -f renderer/Dockerfile .`), not from `renderer/`. Update any CI scripts or build aliases accordingly.
- **System font:** For `cairosvg`-based visual judging to use NunitoSans, install the TTF files as a system font (e.g. `cp assets/fonts/*.ttf ~/Library/Fonts/ && fc-cache` on macOS). This is a one-time setup step, not automated by this plan.
- **`embed_fonts=True`:** Available on `ir_to_svg()` and `SVGRenderer` for producing portable standalone SVGs. Not the default; call explicitly when needed.
