# Which file is the paper

`workshop_readable.tex` is the final, camera-ready version of the confidence paper,
"Knowing Before Saying: Internal Correctness Signals in Mathematical Reasoning"
(MATH-AI 2026, the 6th Workshop on Mathematical Reasoning and AI at NeurIPS 2026).

- Submitted 2026-09-07. Git tag: `mathai-2026-submitted`.
  Exact submitted PDF: `archive/knowing-before-saying_mathai2026_submitted.pdf`.
- Accepted 2026-09-30. Camera-ready finalized 2026-10-02. Git tag: `confidence-mathai-2026-camera-ready`.
  Exact camera-ready PDF: `archive/knowing-before-saying_confidence_mathai2026_camera-ready.pdf`.
  Camera-ready changes: author block (style option `final`), sampling correction in the
  checkpoints appendix, and intro/Section 3/lens wording from the 2026-10-02 read-through.
- Build: `lualatex workshop_readable && bibtex workshop_readable && lualatex workshop_readable && lualatex workshop_readable`
  (TeX Live at /Library/TeX/texbin on the laptop).
- Appendices: `appendices/W_worked_example.tex`. References: `refs.bib` + `refs_confidence.bib`.
- Style: `style/neurips_2026.sty`, identical to the MATH-AI template, option `dblblindworkshop`.

Earlier drafts (`workshop_confidence.tex`, `workshop_combined.tex`, `workshop.tex`) were
removed on 2026-10-02 to avoid confusion; they are in git history before commit `cbb9ee8`
and in `archive/`. `geogenbench.tex` is the separate full-length GeoGenBench paper, not a
draft of this one. The GeoGenBench workshop 4-pager lives on branch `paper/geogenbench-4pager`.

Data behind the paper: `s3://renphil-geogen-interp/activations/` (all cells) and the
`interp/results/` directory on branch `feat/spatial-interp` of the geometry-diagram-generator repo.
The lab notebook there (`interp/LAB_NOTEBOOK.md`) has the full run history, including the
2026-09-06/07 recovery of the Qwen3.6 cell.
