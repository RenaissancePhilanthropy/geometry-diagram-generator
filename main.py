import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv
from logging import basicConfig, INFO

load_dotenv()

basicConfig(level=INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

strategy_name = os.environ.get("STRATEGY", "raw_code")
renderer_name = os.environ.get("RENDERER", "tikz")


def _make_renderer():
    if renderer_name == "svg":
        from ir.renderer import SVGRenderer
        return SVGRenderer()
    elif renderer_name == "tikz":
        from ir.renderer import TikZRenderer
        return TikZRenderer()
    else:
        raise ValueError(f"Unknown RENDERER: {renderer_name!r}. Supported: tikz, svg")


def _make_strategy():
    if strategy_name == "raw_code":
        if renderer_name == "svg":
            from strategies.raw_svg import RawSVGStrategy
            return RawSVGStrategy(enable_cache=True)
        else:
            from strategies.raw_code import RawCodeStrategy
            return RawCodeStrategy(enable_cache=True)
    elif strategy_name == "raw_code_with_revise":
        if renderer_name == "svg":
            from strategies.raw_svg_with_revise import RawSVGWithReviseStrategy
            return RawSVGWithReviseStrategy(enable_cache=True)
        else:
            from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
            return RawCodeWithReviseStrategy(enable_cache=True)
    elif strategy_name == "structured":
        from strategies.structured import StructureStrategy
        return StructureStrategy(enable_cache=True)
    elif strategy_name == "recipe":
        from strategies.recipe import RecipeStrategy
        return RecipeStrategy(enable_cache=True)
    else:
        raise ValueError(
            f"Unknown STRATEGY: {strategy_name!r}. "
            "Supported: raw_code, raw_code_with_revise, structured, recipe"
        )


_strategy = _make_strategy()
_renderer = _make_renderer() if strategy_name in ("structured", "recipe") else None
_model = os.environ.get("MODEL", "anthropic:claude-sonnet-4-6")


async def invoke(request: Request) -> JSONResponse:
    """POST /api/invoke — run the strategy and return SVG."""
    body = await request.json()
    prompt = body.get("prompt", "")
    try:
        result = await _strategy.run(prompt, model=_model, renderer=_renderer)
        svg = getattr(result, "svg", "")
        return JSONResponse({"svg": svg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


routes: list = [Route("/api/invoke", invoke, methods=["POST"])]
if os.path.isdir("demo-ui/dist"):
    routes.append(Mount("/", app=StaticFiles(directory="demo-ui/dist", html=True)))

app = Starlette(routes=routes)
