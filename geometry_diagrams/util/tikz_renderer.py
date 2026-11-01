"""
HTTP client for the TikZ renderer container.
Sends TikZ code to the renderer service and returns the rendered SVG.
"""

import os
import time
from logging import getLogger

import httpx

logger = getLogger(__name__)

_DEFAULT_RENDERER_URL = "http://localhost:8001"

# Must cover the server's two 15 s stage timeouts plus time spent queued
# behind other requests (the server itself gives up on a request at 50 s).
_RENDER_TIMEOUT_S = 60.0


def check_renderer_health(renderer_url: str | None = None) -> bool:
    """Return True if the renderer container is reachable, False otherwise.

    Retries up to 3 times with a 5s timeout each. Docker Desktop on macOS can
    have transient bridge-network hiccups that cause spurious connection
    failures when many concurrent processes hit the container at once.
    """
    url = renderer_url or os.getenv("TIKZ_RENDERER_URL", _DEFAULT_RENDERER_URL)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.get(f"{url}/health", timeout=5.0)
            if response.status_code == 200:
                return True
            last_error = RuntimeError(f"non-200 status: {response.status_code}")
        except httpx.HTTPError as e:
            last_error = e
        if attempt < 2:
            time.sleep(1.0)
    logger.warning("Renderer health check failed after 3 attempts: %s", last_error)
    return False


def render_tikz(
    tikz: str,
    *,
    renderer_url: str | None = None,
    font_family: str | None = None,
) -> str:
    """
    Render TikZ code to SVG via the renderer container.

    Args:
        tikz: TikZ code to place inside \\begin{tikzpicture}...\\end{tikzpicture}.
        renderer_url: Base URL of the renderer. Defaults to TIKZ_RENDERER_URL env
                      var or http://localhost:8001.
        font_family: Optional font family name to pass to the renderer.

    Returns:
        Rendered SVG as a string.

    Raises:
        RuntimeError: If rendering fails, with stage and LaTeX/dvisvgm log in message.
    """
    url = renderer_url or os.getenv("TIKZ_RENDERER_URL", _DEFAULT_RENDERER_URL)
    endpoint = f"{url}/render"

    payload: dict = {"tikz": tikz}
    if font_family:
        payload["font_family"] = font_family

    logger.debug("Sending TikZ render request to %s", endpoint)

    try:
        response = httpx.post(endpoint, json=payload, timeout=_RENDER_TIMEOUT_S)
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
