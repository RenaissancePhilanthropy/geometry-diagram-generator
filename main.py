import os

from pydantic_ai.ui.ag_ui.app import AGUIApp
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv
from logging import basicConfig, INFO

from strategies.raw_code import RawCodeStrategy

load_dotenv()  # Load environment variables from .env file

basicConfig(level=INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

agent = RawCodeStrategy().build_agent()

agui_app = AGUIApp(agent)

routes = [Mount('/api', app=agui_app)]
if os.path.isdir('demo-ui/dist'):
    routes.append(Mount('/', app=StaticFiles(directory='demo-ui/dist', html=True)))

app = Starlette(routes=routes)
