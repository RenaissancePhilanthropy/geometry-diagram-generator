import json
import os
import uuid

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
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
        from geometry_diagrams.ir.renderer import SVGRenderer
        return SVGRenderer()
    elif renderer_name == "tikz":
        from geometry_diagrams.ir.renderer import TikZRenderer
        return TikZRenderer()
    else:
        raise ValueError(f"Unknown RENDERER: {renderer_name!r}. Supported: tikz, svg")


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
        return StructureStrategy(enable_cache=True)
    elif strategy_name == "recipe":
        from geometry_diagrams.strategies.recipe import RecipeStrategy
        return RecipeStrategy(enable_cache=True)
    else:
        raise ValueError(
            f"Unknown STRATEGY: {strategy_name!r}. "
            "Supported: raw_code, raw_svg, raw_code_with_revise, raw_svg_with_revise, structured, recipe"
        )


_strategy = _make_strategy()
_renderer = _make_renderer() if strategy_name in ("structured", "recipe") else None
_model = os.environ.get("MODEL", "anthropic:claude-sonnet-4-6")

# Build agent once at startup so _last_sym persists across conversational turns.
_agent = _strategy.build_agent(model=_model, renderer=_renderer) if hasattr(_strategy, "build_agent") else None


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


async def agent(request: Request) -> StreamingResponse:
    """POST /api/ — conversational agent endpoint with SSE streaming."""
    from langchain_core.messages import HumanMessage, AIMessage

    body = await request.json()
    messages_data = body.get("messages", [])

    lc_messages = []
    for msg in messages_data:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))

    graph = _agent or _strategy.build_agent(model=_model, renderer=_renderer)

    async def generate():
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

        except Exception as e:
            yield sse({"type": "RUN_ERROR", "message": str(e)})

    return StreamingResponse(generate(), media_type="text/event-stream")


routes: list = [
    Route("/api/invoke", invoke, methods=["POST"]),
    Route("/api/", agent, methods=["POST"]),
]
if os.path.isdir("demo-ui/dist"):
    routes.append(Mount("/", app=StaticFiles(directory="demo-ui/dist", html=True)))

app = Starlette(routes=routes)
