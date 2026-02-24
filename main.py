import os
from pathlib import Path

from pydantic_ai.ui.ag_ui.app import AGUIApp
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

from strategies.raw_code import RawCodeStrategy
from strategies.structured import StructuredStrategy

load_dotenv()  # Load environment variables from .env file

domain = Path('demo-ui/geometry.domain').read_text()

_strategy_name = os.getenv('SUBSTANCE_STRATEGY', 'raw_code')
if _strategy_name == 'structured':
    strategy = StructuredStrategy()
else:
    strategy = RawCodeStrategy()

agent = strategy.build_agent(domain)

agui_app = AGUIApp(agent)

routes = [Mount('/api', app=agui_app)]
if os.path.isdir('demo-ui/dist'):
    routes.append(Mount('/', app=StaticFiles(directory='demo-ui/dist', html=True)))

app = Starlette(routes=routes)
