import asyncio
import json
import logging
import os
import re
import uuid
from collections import OrderedDict

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv
from logging import basicConfig, INFO

from geometry_diagrams.config import GeometryConfig
from geometry_diagrams.ir.font import FontConfig

load_dotenv()

basicConfig(level=INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

# GEOMETRY_* names match the library's GeometryConfig; the older bare
# STRATEGY/RENDERER/MODEL names are still honoured as fallbacks.
strategy_name = os.environ.get("GEOMETRY_STRATEGY") or os.environ.get("STRATEGY", "raw_code")
renderer_name = os.environ.get("GEOMETRY_RENDERER") or os.environ.get("RENDERER", "svg")

# Request limits (overridable by env).
MAX_PROMPT_CHARS = int(os.environ.get("GEOMETRY_MAX_PROMPT_CHARS", "10000"))
MAX_BODY_BYTES = int(os.environ.get("GEOMETRY_MAX_BODY_BYTES", "2000000"))
MAX_MESSAGES = int(os.environ.get("GEOMETRY_MAX_MESSAGES", "200"))
MAX_CONCURRENT_RUNS = int(os.environ.get("GEOMETRY_MAX_CONCURRENT_RUNS", "4"))
MAX_SESSIONS = int(os.environ.get("GEOMETRY_MAX_SESSIONS", "64"))
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

# Bounds how many LLM-bound runs execute at once; the rest queue.
_llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)

GENERIC_ERROR = "The request failed. Please try again."


def _make_renderer():
    cfg = GeometryConfig.from_env()
    font_config = FontConfig(family=cfg.font_family)
    if renderer_name == "svg":
        from geometry_diagrams.ir.renderer import SVGRenderer
        return SVGRenderer(
            font_config=font_config,
            embed_fonts=cfg.embed_fonts,
            debug_show_implicit=cfg.debug_show_implicit,
        )
    elif renderer_name == "tikz":
        from geometry_diagrams.ir.renderer import TikZRenderer
        return TikZRenderer(renderer_url=cfg.renderer_url, font_config=font_config)
    else:
        raise ValueError(f"Unknown renderer: {renderer_name!r}. Supported: tikz, svg")


def _make_strategy():
    if strategy_name in ("raw_code", "raw_svg"):
        if strategy_name == "raw_svg" or renderer_name == "svg":
            from geometry_diagrams.strategies.raw_svg import RawSVGStrategy
            return RawSVGStrategy(enable_cache=True)
        else:
            from geometry_diagrams.strategies.raw_code import RawCodeStrategy
            return RawCodeStrategy(enable_cache=True)
    elif strategy_name in ("raw_code_with_revise", "raw_svg_with_revise"):
        if strategy_name == "raw_svg_with_revise" or renderer_name == "svg":
            from geometry_diagrams.strategies.raw_svg_with_revise import RawSVGWithReviseStrategy
            return RawSVGWithReviseStrategy(enable_cache=True)
        else:
            from geometry_diagrams.strategies.raw_code_with_revise import RawCodeWithReviseStrategy
            return RawCodeWithReviseStrategy(enable_cache=True)
    elif strategy_name == "structured":
        from geometry_diagrams.strategies.structured import StructureStrategy
        return StructureStrategy(enable_cache=True, features=GeometryConfig.from_env().features)
    elif strategy_name == "recipe":
        from geometry_diagrams.strategies.recipe import RecipeStrategy
        return RecipeStrategy(enable_cache=True, features=GeometryConfig.from_env().features)
    elif strategy_name == "python_full":
        from geometry_diagrams.strategies.python_full import PythonFullStrategy
        return PythonFullStrategy(enable_cache=True, features=GeometryConfig.from_env().features)
    else:
        raise ValueError(
            f"Unknown STRATEGY: {strategy_name!r}. "
            "Supported: raw_code, raw_svg, raw_code_with_revise, raw_svg_with_revise, structured, recipe, python_full"
        )


_strategy = _make_strategy()
_renderer = _make_renderer() if strategy_name in ("structured", "recipe", "python_full") else None
_model = os.environ.get("GEOMETRY_MODEL") or os.environ.get("MODEL", "anthropic:claude-sonnet-4-6")
_geometry_config = GeometryConfig.from_env()
_edit_generation_mode = _geometry_config.edit_generation_mode
_sandbox_timeout_seconds = _geometry_config.sandbox_timeout_seconds


def _build_agent_for_strategy():
    if hasattr(_strategy, "build_agent"):
        if strategy_name == "python_full":
            return _strategy.build_agent(
                model=_model, renderer=_renderer, edit_generation_mode=_edit_generation_mode,
                retry_on_apply_failure=True, sandbox_timeout_seconds=_sandbox_timeout_seconds,
            )
        return _strategy.build_agent(model=_model, renderer=_renderer)
    return None


# Build agent once at startup so state (e.g. python_full's edit stack,
# structured/recipe's _last_ir) persists across conversational turns.
_agent = _build_agent_for_strategy()

# Per-session agents (request body "session_id"), least-recently-used evicted.
_session_agents: "OrderedDict[str, object]" = OrderedDict()


def _agent_for_session(session_id: str | None):
    """The agent holding conversation state for ``session_id``.

    ``None`` is the single shared conversation. Each named session gets its own
    agent (its own edit state); at most MAX_SESSIONS are kept.
    """
    global _agent
    if session_id is None:
        if _agent is None:
            _agent = _build_agent_for_strategy()
        return _agent
    graph = _session_agents.get(session_id)
    if graph is not None:
        _session_agents.move_to_end(session_id)
        return graph
    graph = _build_agent_for_strategy()
    _session_agents[session_id] = graph
    while len(_session_agents) > MAX_SESSIONS:
        _session_agents.popitem(last=False)
    return graph


def _bad_request(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


async def _read_json_object(request: Request) -> tuple[dict | None, JSONResponse | None]:
    """Parse the request body as a JSON object, or return a 4xx response."""
    try:
        raw = await request.body()
    except Exception:
        return None, _bad_request("Could not read request body")
    if len(raw) > MAX_BODY_BYTES:
        return None, _bad_request("Request body too large", 413)
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, _bad_request("Invalid JSON body")
    if not isinstance(body, dict):
        return None, _bad_request("JSON body must be an object")
    return body, None


async def invoke(request: Request) -> JSONResponse:
    """POST /api/invoke — run the strategy and return SVG."""
    body, err = await _read_json_object(request)
    if err is not None:
        return err
    prompt = body.get("prompt", "")
    if not isinstance(prompt, str):
        return _bad_request("prompt must be a string")
    if len(prompt) > MAX_PROMPT_CHARS:
        return _bad_request(f"prompt exceeds {MAX_PROMPT_CHARS} characters", 413)
    try:
        run_kwargs = {"model": _model, "renderer": _renderer}
        if strategy_name == "python_full":
            run_kwargs["sandbox_timeout_seconds"] = _sandbox_timeout_seconds
        async with _llm_semaphore:
            result = await _strategy.run(prompt, **run_kwargs)
        svg = getattr(result, "svg", "")
        return JSONResponse({"svg": svg})
    except Exception:
        logger.exception("/api/invoke failed")
        return JSONResponse({"error": GENERIC_ERROR}, status_code=500)


async def agent(request: Request) -> Response:
    """POST /api/ — conversational agent endpoint with SSE streaming.

    Optional body field ``session_id`` selects a per-session conversation
    (LRU-capped); absent, every request shares the one default conversation.
    """
    from langchain_core.messages import HumanMessage, AIMessage

    body, err = await _read_json_object(request)
    if err is not None:
        return err
    messages_data = body.get("messages", [])
    if not isinstance(messages_data, list):
        return _bad_request("messages must be a list")
    if len(messages_data) > MAX_MESSAGES:
        return _bad_request(f"too many messages (max {MAX_MESSAGES})", 413)
    session_id = body.get("session_id")
    if session_id is not None and (
        not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id)
    ):
        return _bad_request("session_id must be 1-128 characters of [A-Za-z0-9_.:-]")

    lc_messages = []
    for msg in messages_data:
        if not isinstance(msg, dict):
            return _bad_request("each message must be an object")
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, (str, list)):
            return _bad_request("message content must be a string or list")
        if role == "user" and isinstance(content, str) and len(content) > MAX_PROMPT_CHARS:
            return _bad_request(f"message exceeds {MAX_PROMPT_CHARS} characters", 413)
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    graph = _agent_for_session(session_id)

    async def run():
        def sse(event: dict) -> str:
            return f"data: {json.dumps(event)}\n\n"

        yield sse({"type": "RUN_STARTED"})

        current_msg_id: str | None = None
        tool_index_to_id: dict[int, str] = {}
        tool_run_to_call_id: dict[str, str] = {}  # fallback if output is not ToolMessage

        try:
            async for event in graph.astream_events(
                {"messages": lc_messages},
                version="v2",
            ):
                evt_type = event["event"]
                data = event.get("data", {})
                metadata = event.get("metadata", {})

                if evt_type == "on_chat_model_stream":
                    # Only the top-level ReAct agent's own model calls (tagged
                    # "agent" by LangGraph) are user-facing text. Edit modes
                    # like search_replace/patch/hashline/line_number make their
                    # OWN internal LLM calls from inside the render_diagram
                    # tool's implementation — those stream through this same
                    # astream_events feed tagged "tools", and forwarding them
                    # unfiltered leaks raw generation output (e.g. a SEARCH/
                    # REPLACE block) into the chat as if the assistant said it.
                    if metadata.get("langgraph_node") != "agent":
                        continue

                    chunk = data.get("chunk")
                    if not chunk:
                        continue

                    content = chunk.content
                    if isinstance(content, str) and content:
                        if current_msg_id is None:
                            current_msg_id = str(uuid.uuid4())
                            yield sse({"type": "TEXT_MESSAGE_START", "messageId": current_msg_id})
                        yield sse({"type": "TEXT_MESSAGE_CONTENT", "messageId": current_msg_id, "delta": content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text = item.get("text", "")
                                if text:
                                    if current_msg_id is None:
                                        current_msg_id = str(uuid.uuid4())
                                        yield sse({"type": "TEXT_MESSAGE_START", "messageId": current_msg_id})
                                    yield sse({"type": "TEXT_MESSAGE_CONTENT", "messageId": current_msg_id, "delta": text})

                    for tc in (chunk.tool_call_chunks or []):
                        tc_id = tc.get("id")
                        tc_name = tc.get("name")
                        tc_args = tc.get("args", "")
                        tc_index = tc.get("index") or 0

                        if tc_id and tc_id not in tool_index_to_id.values():
                            if current_msg_id is not None:
                                yield sse({"type": "TEXT_MESSAGE_END", "messageId": current_msg_id})
                                current_msg_id = None
                            tool_index_to_id[tc_index] = tc_id
                            yield sse({"type": "TOOL_CALL_START", "toolCallId": tc_id, "toolCallName": tc_name or ""})

                        resolved_id = tc_id or tool_index_to_id.get(tc_index)
                        if resolved_id and tc_args:
                            yield sse({"type": "TOOL_CALL_ARGS", "toolCallId": resolved_id, "delta": tc_args})

                elif evt_type == "on_chat_model_end":
                    if current_msg_id is not None:
                        yield sse({"type": "TEXT_MESSAGE_END", "messageId": current_msg_id})
                        current_msg_id = None
                    for tc_id in tool_index_to_id.values():
                        yield sse({"type": "TOOL_CALL_END", "toolCallId": tc_id})
                    tool_index_to_id = {}

                elif evt_type == "on_tool_start":
                    run_id = event.get("run_id", "")
                    tc_id = metadata.get("tool_call_id")
                    if run_id and tc_id:
                        tool_run_to_call_id[run_id] = tc_id

                elif evt_type == "on_tool_end":
                    from langchain_core.messages import ToolMessage
                    output = data.get("output")
                    if isinstance(output, ToolMessage):
                        tc_id = output.tool_call_id
                        content = output.content if isinstance(output.content, str) else json.dumps(output.content)
                    else:
                        tc_id = metadata.get("tool_call_id") or tool_run_to_call_id.get(event.get("run_id", ""))
                        content = output if isinstance(output, str) else json.dumps(str(output))
                    if tc_id:
                        yield sse({"type": "TOOL_CALL_RESULT", "toolCallId": tc_id, "content": content})

            yield sse({"type": "RUN_FINISHED"})

        except Exception:
            logger.exception("/api/ agent run failed")
            yield sse({"type": "RUN_ERROR", "message": GENERIC_ERROR})

    async def generate():
        async with _llm_semaphore:
            async for chunk in run():
                yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream")


routes: list = [
    Route("/api/invoke", invoke, methods=["POST"]),
    Route("/api/", agent, methods=["POST"]),
]
if os.path.isdir("demo-ui/dist"):
    routes.append(Mount("/", app=StaticFiles(directory="demo-ui/dist", html=True)))

app = Starlette(routes=routes)
