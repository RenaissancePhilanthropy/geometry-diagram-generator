# slides/

Onboarding presentations for the GeoGenBench project.

## Decks

| File | Audience | Length |
|---|---|---|
| `onboarding.html` | New project contributors (engineers, researchers ramping up) | ~10–12 min, 10 slides |
| `SPEAKER_NOTES.md` | The presenter — conversational walkthrough script for `onboarding.html` |  |

## Presenting

Open `onboarding.html` on the projector and `SPEAKER_NOTES.md` on a second screen (laptop, phone, or printed). The notes are written as natural spoken-aloud prose, with stage directions, what-to-emphasize bullets, and an anticipated-Q&A table at the end.

## How to view

It's a single self-contained HTML file. No install, no server.

```bash
open slides/onboarding.html
```

Or any of:

```bash
# Chrome / Safari / Firefox — just open the file
open -a "Google Chrome" slides/onboarding.html
```

## Navigation

- **Arrow keys** (←/→/↑/↓), **Space**, **Page Up/Down** — next/previous slide
- **Home / End** — first / last slide
- **Mouse wheel / trackpad scroll** — works (native scroll-snap)
- **Touch swipe** — works on mobile / tablet
- **Click the navigation dots** on the right edge
- **`S` key** — toggle the speaker-notes overlay (sticky panel at the bottom of the viewport, shows the notes for whichever slide you're on)

## Presenter mode

Press **`S`** at any time to reveal a slim notes panel along the bottom of the screen. The panel shows speaker notes for the slide currently in view; as you advance, the notes track. Press `S` again to hide them. The notes are also mirrored in `SPEAKER_NOTES.md` if you'd rather read on a second device.

## How to edit

The HTML is hand-authored and well-commented:

1. **Theme**: change CSS variables at the top of the `<style>` block (`--accent-blue`, `--bg-dark`, etc.) to retheme the whole deck in one place.
2. **Content**: each slide is a `<section class="slide ...">` near the bottom of the file. Edit the inner HTML directly. Remember to keep content within the per-slide density limits — every slide must fit within 100vh without scrolling.
3. **Add a slide**: copy any existing `<section class="slide ...">`, paste it in the right order, and update the `data-title`. The nav dots and slide numbers regenerate automatically on page load.

## Style preset

Built using the [Frontend Slides](https://github.com/zarazhangrui/frontend-slides) skill,
**Electric Studio** preset (Manrope display + body, accent blue `#4361ee`, high-contrast white/dark split panels).

## Export

Export to PDF (e.g. for sending to someone who'd rather read a static deck):

```bash
# One-off via Chrome's headless print:
google-chrome --headless --disable-gpu --print-to-pdf=onboarding.pdf \
  file://$(pwd)/slides/onboarding.html
```

Or use the `frontend-slides` skill's bundled exporter (Playwright, captures one slide per page at 1920×1080).
