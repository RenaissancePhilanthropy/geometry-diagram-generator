"""
HTTP client for the TikZ renderer container.
Sends TikZ code to the renderer service and returns the rendered SVG.
"""

import os
from logging import getLogger

import httpx

logger = getLogger(__name__)

_DEFAULT_RENDERER_URL = "http://localhost:8001"


def render_tikz(
    tikz: str,
    *,
    tkzelements: str | None = None,
    renderer_url: str | None = None,
) -> str:
    """
    Render TikZ code to SVG via the renderer container.

    Args:
        tikz: TikZ code to place inside \\begin{tikzpicture}...\\end{tikzpicture}.
        tkzelements: Optional tkz-elements Lua code block.
        renderer_url: Base URL of the renderer. Defaults to TIKZ_RENDERER_URL env
                      var or http://localhost:8001.

    Returns:
        Rendered SVG as a string.

    Raises:
        RuntimeError: If rendering fails, with stage and LaTeX/dvisvgm log in message.
    """
    url = renderer_url or os.getenv("TIKZ_RENDERER_URL", _DEFAULT_RENDERER_URL)
    endpoint = f"{url}/render"

    payload: dict = {"tikz": tikz}
    if tkzelements:
        payload["tkzelements"] = tkzelements

    logger.debug("Sending TikZ render request to %s", endpoint)

    try:
        response = httpx.post(endpoint, json=payload, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise RuntimeError(f"Renderer request failed: {e}") from e

    data = response.json()

    if not data.get("ok"):
        stage = data.get("stage", "unknown")
        log = data.get("log", "")
        logger.warning("TikZ rendering failed at stage '%s': %s", stage, log)
        raise RuntimeError(
            f"TikZ rendering failed at stage '{stage}'.\n\nLog:\n{log}"
        )

    svg = data["svg"]
    logger.debug("TikZ rendering succeeded, SVG length=%d", len(svg))
    return svg
