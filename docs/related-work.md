# Related Work

Working draft for Section 2 of the GeoGen paper. Each subsection ends with a **positioning paragraph** stating exactly how GeoGen differs.

---

## 2.1 Geometry-understanding benchmarks (model is given a diagram)

The dominant family of geometry benchmarks gives the model both a diagram and a textual question, and asks it to *answer* a question — typically multiple-choice or numeric.

**Geometry3K** [Lu et al., ACL 2021] introduced 3,002 high-school problems (grades 6-12) drawn from US textbooks, each densely annotated in a formal-language vocabulary of 91 predicates. Their accompanying solver, Inter-GPS, parses problem text and diagrams into formal language and applies symbolic theorem-based reasoning, achieving 57.5% test accuracy versus 90.9% for human experts. The dataset comes from McGraw-Hill and Geometryonline textbooks; problems span lines, triangles, quadrilaterals, polygons, and circles, with up to four problem goals. *Models are evaluated on whether they pick the correct multiple-choice answer; they never produce a diagram.*

**GeoQA** [Chen et al., Findings of ACL 2021] released 4,998 Chinese middle-school geometry problems with annotated program traces showing the solving steps. Their NGS (Neural Geometric Solver) reads diagram + text and emits a program; correctness is judged by program execution against the gold answer (e.g., 60.0% accuracy on test, broken down 71.5% angle / 48.8% length / 29.6% other). GeoQA was 25× larger than the prior GeoS dataset of 186 problems. *Same task family as Geometry3K, with explainable program annotations.*

**UniGeo** [Chen et al., EMNLP 2022] unifies geometry calculation (4,998 problems, reusing GeoQA) with proving (9,543 multi-step proofs), treating proving steps as sequences of mathematical-expression tokens compatible with calculation programs. Their Geoformer multitask transformer reaches 60.9% calculation / 55.8% proving accuracy after unified training. *Adds proof construction to the QA paradigm but still given-the-diagram.*

**MathVista** [Lu et al., ICLR 2024 Oral] aggregates 6,141 examples from 31 multimodal-math datasets — including 9 MathQA datasets and 19 VQA sources — plus three new sub-datasets (IQTest, FunctionQA, PaperQA) for puzzles, function plots, and scientific figures. Geometry Problem Solving (GPS) is one of five tasks in their taxonomy. GPT-4V scores 49.9% overall (vs. 60.3% human), and broader multimodal models achieve 30-37%. *Geometry is a subset; the geometry items themselves are given-diagram QA inherited from prior datasets.*

**GeoEval** [Zhang et al., Findings of ACL 2024] explicitly addresses LLM (vs. trained solver) evaluation on geometry, providing 2,000 main + 750 backward-reasoning + 2,000 augmented + 300 hard problems aggregated from seven public datasets, covering plane, solid, and analytic geometry. WizardMath-70B leads the main subset at 55.67%; on the hard subset every evaluated model (including GPT-4 and GPT-4V) drops below 11%, except InstructBLIP at 70.3% which the authors attribute to overlap with its training data. *Demonstrates that QA benchmarks can be saturated by training-data overlap; introduces "augmented" subsets to control. But still QA of given diagrams.*

**GeoBench** [Anonymous, ICLR 2026 submission, currently under review] introduces hierarchical evaluation across four reasoning levels grounded in van Hiele's theory of geometric thinking, with 1,021 formally-verified problems generated via a TrustGeoGen pipeline. Reports that o3 outperforms general MLLMs but degrades sharply with complexity; chain-of-thought prompting unexpectedly hurts on reflective-backtracking tasks. *Most methodologically modern of the QA family; introduces formal verification of problems but tests understanding, not generation.*

### Positioning vs. GeoGen

Every benchmark above tests whether a model can *interpret* a diagram and answer a question. **None tests whether the model can *produce* a correct diagram from a textual description.** This is a fundamentally different capability — generative geometric reasoning requires the model to translate a textual specification into a globally-consistent metric realization, not to read one. As frontier models are increasingly deployed as agents that must *create* visual artifacts (slides, math worksheets, technical drawings, illustrations), generative capability is what's being asked for in deployment but not measured in research.

---

## 2.2 Text-to-image benchmarks (no math grounding)

A separate literature evaluates whether text-to-image models can faithfully render compositions of objects, attributes, and relations.

**T2I-CompBench / T2I-CompBench++** [Huang et al., NeurIPS 2023; TPAMI 2025] provides 6,000 (later 8,000) compositional prompts across attribute binding (color, shape, texture), object relationships (spatial, non-spatial, 3D-spatial), generative numeracy, and complex compositions. Evaluated 11+ T2I models with detection-based metrics: BLIP-VQA for attribute binding, UniDet for spatial/numeracy, CLIPScore for non-spatial, MLLM-based 3-in-1 for complex. *Adopted as the official compositionality metric by Stable Diffusion 3, DALL-E 3, and PixArt-α.* It's the de-facto T2I compositional benchmark, but the prompts are real-world objects ("a red car next to a blue truck"), not geometric constructions, and verification relies on detection / VLM scoring rather than ground-truth geometry.

**DrawBench** [Saharia et al., 2022] (200 prompts on counting, compositions, conflicts, writing) and earlier benchmarks like **PaintSkills** test similar compositional skills.

### Positioning vs. GeoGen

T2I benchmarks operate in pixel space and rely on visual evaluators (CLIP, BLIP, MLLMs) to score outputs. They cannot tell whether a "right triangle" actually has a right angle — only whether the image *looks like* a right triangle to a vision-language judge. GeoGen operates in symbolic space (TikZ → compiled SymPy geometry) where automatic exact verification is possible: angle-equal checks are computed by `sympy.geometry.Triangle.angles`, midpoint checks by coordinate equality, etc. This shifts grading from "does it look right to a model" to "does the underlying geometry satisfy a checkable predicate."

---

## 2.3 Generative-exam and exam-style image benchmarks

**GenExam** [Wang et al., arXiv 2509.14232, Sep 2025; submitted to ICLR 2026] is the closest prior art and explicitly motivates the need for generative-exam benchmarks. GenExam introduces 1,000 multidisciplinary text-to-image exam-style prompts across 10 subjects (math, physics, chemistry, biology, etc.) with ground-truth images and per-problem scoring rubrics. It uses an MLLM judge (the released code targets GPT-5 evaluation) to assign strict and relaxed scores. Their key empirical finding: even frontier T2I models (GPT-Image-1, Gemini-2.5-Flash-Image) score under 15% strict on the full set; most models near zero. The latest closed leaderboard entry (Nano Banana Pro, Nov 2025) reaches 72.7 strict / 93.7 relaxed on a likely smaller / re-scored split.

### Positioning vs. GeoGen

GenExam and GeoGen share a generative-exam framing, but differ on three axes that matter for paper-writing science:

1. **Grading mechanism**: GenExam's per-problem rubrics are scored by an MLLM judge against the generated image and a ground-truth reference. GeoGen's per-problem checks are evaluated by a deterministic SymPy program against the compiled symbolic geometry. The latter is ~1000× cheaper, fully reproducible, and not contestable as "the judge was confused." When a GeoGen scenario marks `right_angle_at_C: pass`, that's `sympy.Triangle(B, C, A).angles[C] == pi/2 ± tol`, not "the judge said it looked perpendicular."
2. **Modality**: GenExam evaluates raster image generation. GeoGen evaluates structured TikZ generation that compiles to vector SVG. This makes GeoGen accessible to text-only LLMs without image-token capability, dramatically widens the model pool, and means a Haiku-tier text model can be a serious competitor.
3. **Domain breadth**: GenExam spans 10 disciplines, ~100 prompts each. GeoGen is geometry-only, with ~800 prompts covering more constructions per topic. Trade-off: GenExam is broader but more subjectively graded; GeoGen is deeper but narrower.

We view GeoGen as the *automatic-grading complement* to GenExam: same generative-exam framing, but in a domain (geometry) where symbolic verification replaces visual judgment.

---

## 2.4 Symbolic verification & formal grading benchmarks

A growing line of work treats math benchmarks as opportunities for *exact*, machine-checked grading rather than approximate string-matching:

- **Lean / Isabelle / Coq corpora** (miniF2F, ProofNet, MathLib) check mathematical proofs symbolically, but require formal-language outputs.
- **AlphaProof / AlphaGeometry** [DeepMind, 2024] solve IMO-level geometry problems with a neuro-symbolic architecture that uses a deduction engine for verification.
- **Lean-Workbook** [Wang et al., 2024] generates auto-formalizable problems with exact verifiability.

GeoGen extends this *automatic-verification* tradition into **diagram generation**, where the verifiability target is the geometric configuration produced rather than a propositional proof.

---

## 2.5 Tool-use and agent benchmarks adjacent to diagram production

**SWE-bench / SWE-bench-VL** evaluates code-edit correctness with executable tests. **AgentBench**, **GAIA**, and others stress multi-step reasoning. Diagrammatic output rarely shows up in these as a first-class target. Where it does (e.g., when an agent must produce a UI mock or chart), grading typically falls back to LLM-as-judge. GeoGen offers a self-contained domain where execution-style grading (compile-to-SymPy + check) replaces judge-based grading for diagrammatic output.

---

## 2.6 Comparison table

| Benchmark | Year | Task | Domain | # items | Auto-grade | Modality |
|---|---|---|---|---:|---|---|
| Geometry3K | 2021 | QA (multi-choice) | plane geom (HS) | 3,002 | yes (MC match) | image+text |
| GeoQA | 2021 | QA (program → answer) | plane geom (MS, Chinese) | 4,998 | yes (program exec) | image+text |
| UniGeo | 2022 | QA + proving (sequence) | plane geom + proofs | 14,541 | yes (sequence match) | image+text |
| MathVista (geo) | 2024 | QA (mixed) | mixed math (geom subset) | 6,141 | partial | image+text |
| GeoEval | 2024 | QA + variants | plane/solid/analytic | 5,050 | yes | image+text |
| GeoBench | 2026 (ICLR sub) | hierarchical QA | plane geom | 1,021 | yes (verified) | image+text |
| T2I-CompBench++ | 2023/25 | T2I generation | natural compositions | 8,000 | partial (VLM/det) | text → image |
| GenExam | 2025/26 | T2I generation | exam-style (10 disc) | 1,000 | LLM-judge | text → image |
| **GeoGen (ours)** | **2026** | **diagram generation** | **plane geom (templated + curriculum)** | **~800** | **yes (symbolic)** | **text → TikZ → SVG** |

The key structural insight: **all auto-graded prior benchmarks are QA over diagrams; all generation-side benchmarks rely on visual judges.** GeoGen occupies the previously-empty cell of *generation-side, automatically-graded* geometry — enabled by the choice to grade in symbolic space (compiled SymPy geometry) rather than pixel space.

---

## Citations (BibTeX, working set)

```bibtex
@inproceedings{lu2021intergps,
  title={Inter-GPS: Interpretable Geometry Problem Solving with Formal Language and Symbolic Reasoning},
  author={Lu, Pan and Gong, Ran and Jiang, Shibiao and Qiu, Liang and Huang, Siyuan and Liang, Xiaodan and Zhu, Song-Chun},
  booktitle={ACL-IJCNLP},
  year={2021}
}

@inproceedings{chen2021geoqa,
  title={GeoQA: A Geometric Question Answering Benchmark Towards Multimodal Numerical Reasoning},
  author={Chen, Jiaqi and Tang, Jianheng and Qin, Jinghui and Liang, Xiaodan and Liu, Lingbo and Xing, Eric P. and Lin, Liang},
  booktitle={Findings of ACL-IJCNLP},
  year={2021}
}

@inproceedings{chen2022unigeo,
  title={UniGeo: Unifying Geometry Logical Reasoning via Reformulating Mathematical Expression},
  author={Chen, Jiaqi and Li, Tong and Qin, Jinghui and Lu, Pan and Lin, Liang and Chen, Chongyu and Liang, Xiaodan},
  booktitle={EMNLP},
  year={2022}
}

@inproceedings{lu2024mathvista,
  title={MathVista: Evaluating Mathematical Reasoning of Foundation Models in Visual Contexts},
  author={Lu, Pan and Bansal, Hritik and Xia, Tony and Liu, Jiacheng and Li, Chunyuan and Hajishirzi, Hannaneh and Cheng, Hao and Chang, Kai-Wei and Galley, Michel and Gao, Jianfeng},
  booktitle={ICLR},
  year={2024}
}

@inproceedings{zhang2024geoeval,
  title={GeoEval: Benchmark for Evaluating LLMs and Multi-Modal Models on Geometry Problem-Solving},
  author={Zhang, Jiaxin and Li, Zhongzhi and Zhang, Mingliang and Yin, Fei and Liu, Chenglin and Moshfeghi, Yashar},
  booktitle={Findings of ACL},
  year={2024}
}

@article{wang2025genexam,
  title={GenExam: A Multidisciplinary Text-to-Image Exam},
  author={Wang, Zhaokai and Yin, Penghao and Zhao, Xiangyu and Tian, Changyao and Qiao, Yu and Wang, Wenhai and Dai, Jifeng and Luo, Gen},
  journal={arXiv:2509.14232},
  year={2025}
}

@inproceedings{huang2023t2icompbench,
  title={T2I-CompBench: A Comprehensive Benchmark for Open-world Compositional Text-to-image Generation},
  author={Huang, Kaiyi and Sun, Kaiyue and Xie, Enze and Li, Zhenguo and Liu, Xihui},
  booktitle={NeurIPS Datasets and Benchmarks},
  year={2023}
}

@article{huang2025t2icompbench++,
  title={T2I-CompBench++: An Enhanced and Comprehensive Benchmark for Compositional Text-to-image Generation},
  author={Huang, Kaiyi and Duan, Chengqi and Sun, Kaiyue and Xie, Enze and Li, Zhenguo and Liu, Xihui},
  journal={IEEE TPAMI},
  year={2025}
}
```
