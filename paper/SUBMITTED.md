# Which file is the paper

`workshop_readable.tex` is the final, submitted version of
"Knowing Before Saying: Internal Correctness Signals in Mathematical Reasoning"
(MATH-AI 2026, the 6th Workshop on Mathematical Reasoning and AI at NeurIPS 2026).

- Submitted 2026-09-07. Git tag: `mathai-2026-submitted`.
- Exact submitted PDF: `archive/knowing-before-saying_mathai2026_submitted.pdf`.
- Build: `lualatex workshop_readable && bibtex workshop_readable && lualatex workshop_readable && lualatex workshop_readable`
  (TeX Live at /Library/TeX/texbin on the laptop).
- Appendices: `appendices/W_worked_example.tex`. References: `refs.bib` + `refs_confidence.bib`.
- Style: `style/neurips_2026.sty`, identical to the MATH-AI template, option `dblblindworkshop`.

`workshop_confidence.tex` and `workshop_combined.tex` are earlier drafts kept for history.
Do not edit them. `geogenbench.tex` is the separate GeoGenBench paper.

Data behind the paper: `s3://renphil-geogen-interp/activations/` (all cells) and the
`interp/results/` directory on branch `feat/spatial-interp` of the geometry-diagram-generator repo.
The lab notebook there (`interp/LAB_NOTEBOOK.md`) has the full run history, including the
2026-09-06/07 recovery of the Qwen3.6 cell.
