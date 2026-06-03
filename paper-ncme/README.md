# NCME submission — *From Language to Verified Diagram*

A 6-page, plain-language paper condensed from the full GeoGenBench paper
(`../paper/`, branch `feat/geogen-paper`), prepared for NCME.

**NCME uses the ACL format**, so this is typeset with the official ACL style
(`acl.sty`, vendored here) in `[preprint]` mode: the ACL two-column layout with
page numbers, but *without* the "Anonymous ACL submission" line or review line
numbers (those appear only in `[review]` mode).

**Focus:** how diagrams are *generated* — the model describes a construction, a
geometry engine computes the exact figure — and how automatic grading falls out
of that same description. Written for readability.

## Build

pdfLaTeX:

```
make            # latexmk -pdf -> main.pdf
make clean
```

No local TeX toolchain? Upload this folder to Overleaf (main document =
`main.tex`); `acl.sty` and `acl_natbib.bst` are vendored here.

## Format

- ACL style (`acl.sty`), two-column, Times. `[preprint]` mode in `main.tex`.
- For a line-numbered anonymous review copy, change `[preprint]` → `[review]`.
- Title ≤ 12 words; abstract ≤ 50 words (NCME portal limits).
- Citations: author–year (`acl_natbib`). Only real, verifiable references — no placeholders.

## Layout

| File | Section |
|---|---|
| `main.tex` | document root (ACL class, packages, title) |
| `preamble.tex` | project macros + math/tikz/tables (nothing acl.sty already loads) |
| `abstract.tex` | 49-word abstract |
| `acl.sty`, `acl_natbib.bst` | official ACL style + bib style (vendored) |
| `sections/01_motivation.tex` | 1 Introduction |
| `sections/02_pipeline.tex` | 2 How the model draws a diagram (+ trace figure) |
| `sections/03_scoring.tex` | 3 Grading comes for free (+ co-generation figure, checklist table) |
| `sections/04_benchmark.tex` | 4 Putting it to the test |
| `sections/05_measurement.tex` | 5 Why this matters for measurement |
