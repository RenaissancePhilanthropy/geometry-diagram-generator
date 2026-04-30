# GeoGenBench — paper

LaTeX source for the **GeoGenBench** NeurIPS Datasets & Benchmarks paper.

**Naming convention** (also defined in §1 of the paper):

- **GeoGen** = the methodology / pipeline (text → TikZ → SymPy → automatic geometric verification).
- **GeoGenBench** = the released benchmark instantiating that methodology
  (801 prompts paired with machine-checkable property lists).

This paper is principally about the benchmark; the methodology is the means.

## Layout

```
paper/
├── geogenbench.tex         # main file; \input's everything below
├── preamble.tex            # packages, project-specific macros
├── abstract.tex
├── sections/
│   ├── 01_introduction.tex
│   ├── 02_related_work.tex
│   ├── 03_benchmark_design.tex
│   ├── 04_verification_reliability.tex
│   ├── 05_models_strategies.tex
│   ├── 06_results.tex
│   ├── 07_discussion.tex
│   └── 08_conclusion.tex
├── appendices/
│   ├── A_template_specs.tex
│   ├── B_property_reference.tex
│   ├── C_completeness_witnesses.tex
│   ├── D_reproduction.tex
│   ├── E_human_study.tex
│   └── F_failure_coding.tex
├── figures/                # symlinks → docs/figures/geogen-pilot/*.pdf
├── style/
│   └── neurips_2024.sty    # official NeurIPS 2024 style file
├── refs.bib
├── Makefile
└── README.md
```

## Building (three options)

### Option 1: local TeX install (recommended for active editing)

Requires MacTeX (or a full TeX Live install) with `latexmk` and `lualatex`:

```bash
brew install --cask mactex-no-gui     # one-time install (~4 GB)
make                                  # build geogenbench.pdf
make watch                            # continuous rebuild on save (latexmk -pvc)
make view                             # open PDF
make clean                            # remove aux files
```

### Option 2: Docker (no install)

Uses the official `texlive/texlive` image. From `paper/`:

```bash
docker run --rm -v "$PWD:/workdir" -w /workdir texlive/texlive:latest \
    latexmk -lualatex -interaction=nonstopmode geogenbench.tex
```

`paper/` is fully self-contained — figures live as PDFs under `paper/figures/`
(not symlinks), so the build does not depend on anything outside the directory.

### Option 3: Overleaf

1. `cd paper && zip -r ../geogen-paper.zip .`
2. Upload `geogen-paper.zip` as a new project on Overleaf.
3. Set the compiler to **LuaLaTeX** in Menu → Compiler.

## Editing conventions

- **Don't edit files under `figures/` directly** — they are PDF copies emitted
  by `evals/leaderboard_plot.py`. To regenerate from the latest hardened pilot
  data and copy into `paper/figures/`:

  ```bash
  bash paper/scripts/refresh_figures.sh
  ```

  Override the source dir via `PILOT_DIR=... bash paper/scripts/refresh_figures.sh`.

- **TODO markers** use the `\TODO{...}` macro (red, visible in the draft) and
  `\NOTE{...}` for editorial notes. Both are stripped at camera-ready time by
  redefining the macros to `\gobble`.

- **Cross-references** use `\cref` (capitalised at sentence start with `\Cref`).
  Conventions: `sec:foo` for sections, `tab:foo` for tables, `fig:foo` for
  figures, `app:foo` for appendices.

- **Numbers and citations** in the body should not be hard-coded if they appear
  in the markdown drafts under `docs/`. Update `docs/section6-leaderboard.md` etc.
  first, then port to the LaTeX. (Eventually we may auto-generate the headline
  table from the leaderboard CSV; for now it's manual.)

## Style: NeurIPS 2024

The `style/neurips_2024.sty` file is the official 2024 style. It is included
unmodified per the NeurIPS rules. Submission options in `geogenbench.tex`:

- `[preprint]` — author names visible, no copyright box (use for arXiv preprint
  and during writing).
- `[final]` — camera-ready.
- (no option) — anonymised submission with line numbers.

We pass `[nonatbib]` to avoid a clash with the natbib loaded in `preamble.tex`.

When NeurIPS 2026 publishes its style file, replace `style/neurips_2024.sty`
with `style/neurips_2026.sty` and update the `\usepackage` line in `geogenbench.tex`.

## Status

- [x] Scaffold + build infrastructure
- [x] Abstract drafted from `docs/abstract-draft.md`
- [x] §1 Introduction drafted from `docs/section1-introduction.md`
- [x] §2 Related work drafted from `docs/related-work.md`
- [x] §3 Benchmark design drafted from `docs/section3-benchmark-design.md`
- [x] §4 Verification reliability drafted from `docs/section4-verification-reliability.md`
- [x] §5 Models & strategies drafted
- [x] §6 Results drafted from `docs/section6-leaderboard.md` with embedded figures
- [x] §7 Discussion drafted
- [x] §8 Conclusion drafted
- [ ] Appendix A — template specifications (skeleton)
- [ ] Appendix B — predicate reference (skeleton)
- [ ] Appendix C — completeness witnesses (skeleton)
- [ ] Appendix D — reproduction instructions (drafted)
- [ ] Appendix E — human-study materials (skeleton, pending study)
- [ ] Appendix F — failure-mode coding manual (skeleton)
- [ ] Headline run on full 600 scenarios with 3 repeats
- [ ] Human-correlation study results
- [ ] Per-template case studies (3 universally-hard templates)
