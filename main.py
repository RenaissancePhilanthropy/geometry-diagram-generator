import os

from pydantic_ai.ui.ag_ui.app import AGUIApp
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv
from logging import basicConfig, INFO

load_dotenv()  # Load environment variables from .env file

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

if strategy_name == "raw_code":
    if renderer_name == "svg":
        from strategies.raw_svg import RawSVGStrategy
        agent = RawSVGStrategy(enable_cache=True).build_agent()
    else:
        from strategies.raw_code import RawCodeStrategy
        agent = RawCodeStrategy(enable_cache=True).build_agent()
elif strategy_name == "raw_code_with_revise":
    if renderer_name == "svg":
        from strategies.raw_svg_with_revise import RawSVGWithReviseStrategy
        agent = RawSVGWithReviseStrategy(enable_cache=True).build_agent()
    else:
        from strategies.raw_code_with_revise import RawCodeWithReviseStrategy
        agent = RawCodeWithReviseStrategy(enable_cache=True).build_agent()
elif strategy_name == "structured":
    from strategies.structured import StructureStrategy
    agent = StructureStrategy(enable_cache=True, renderer=_make_renderer()).build_agent()
elif strategy_name == "structured_plus_refine":
    from strategies.structured_plus_refine import StructuredPlusRefineStrategy
    agent = StructuredPlusRefineStrategy(enable_cache=True, renderer=_make_renderer()).build_agent()
elif strategy_name == "recipe":
    from strategies.recipe import RecipeStrategy
    recipe_catalog = os.environ.get("RECIPE_CATALOG", "default")
    agent = RecipeStrategy(enable_cache=True, catalog=recipe_catalog, renderer=_make_renderer()).build_agent()
else:
    raise ValueError(
        f"Unknown STRATEGY: {strategy_name!r}. "
        "Supported: raw_code, raw_code_with_revise, structured, structured_plus_refine, recipe"
    )

agui_app = AGUIApp(agent)

routes = [Mount('/api', app=agui_app)]
if os.path.isdir('demo-ui/dist'):
    routes.append(Mount('/', app=StaticFiles(directory='demo-ui/dist', html=True)))

app = Starlette(routes=routes)
