import os
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui.app import AGUIApp
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

agent = Agent(
    'anthropic:claude-sonnet-4-6',
    instructions='Be concise, reply with one sentence.',
)

agui_app = AGUIApp(agent)

routes = [Mount('/api', app=agui_app)]
if os.path.isdir('demo-ui/dist'):
    routes.append(Mount('/', app=StaticFiles(directory='demo-ui/dist', html=True)))

app = Starlette(routes=routes)