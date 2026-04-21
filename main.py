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

if strategy_name == "raw_code":
    from strategies.raw_code import RawCodeStrategy
    agent = RawCodeStrategy(enable_cache=True).build_agent()
elif strategy_name == "structured":
    from strategies.structured import StructureStrategy
    agent = StructureStrategy(enable_cache=True).build_agent()
elif strategy_name == "recipe":
    from strategies.recipe import RecipeStrategy
    recipe_catalog = os.environ.get("RECIPE_CATALOG", "default")
    agent = RecipeStrategy(enable_cache=True, catalog=recipe_catalog).build_agent()
else:
    raise ValueError(f"Unknown STRATEGY: {strategy_name!r}. Supported: raw_code, structured, recipe")

agui_app = AGUIApp(agent)

routes = [Mount('/api', app=agui_app)]
if os.path.isdir('demo-ui/dist'):
    routes.append(Mount('/', app=StaticFiles(directory='demo-ui/dist', html=True)))

app = Starlette(routes=routes)
