"""Standalone helpers shared by strategies, evals and the renderer client.

`tikz_renderer.py` is the HTTP client for the renderer container.
`tikz_extraction.py`, `tikz_geometry.py`, `tikz_validation.py` and
`tikz_analysis.py` inspect TikZ source without compiling it;
`svg_checks.py` validates rendered SVG; `llm_judge.py` scores diagrams with
an LLM; `message_helpers.py` pulls content from LangChain messages and
`tracing.py` builds the optional LangFuse callback. None are re-exported here.
"""
