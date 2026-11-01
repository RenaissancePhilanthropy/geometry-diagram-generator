import asyncio
import os
import re
import tempfile
from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = getLogger(__name__)

# PoC knobs
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "2"))
QUEUE_SIZE = int(os.getenv("QUEUE_SIZE", "64"))
TIMEOUT_S = int(os.getenv("RENDER_TIMEOUT_S", "15"))
# Longest a request may wait for its result (queue wait plus both stages).
REQUEST_TIMEOUT_S = int(os.getenv("REQUEST_TIMEOUT_S", "50"))
MAX_FIELD_CHARS = 200_000

# Paranoid file access for TeX: no dotfiles, no parent directories, no absolute
# paths outside the TeX trees. Combined with --no-shell-escape this keeps
# untrusted TikZ from reading or writing arbitrary files.
SUBPROCESS_ENV = {**os.environ, "openin_any": "p", "openout_any": "p"}

# Created in the lifespan so they belong to the running event loop.
sem: asyncio.Semaphore | None = None
queue: asyncio.Queue | None = None


class RenderReq(BaseModel):
    tikz: str = Field(max_length=MAX_FIELD_CHARS)
    # optional block for tkz-elements
    tkzelements: str | None = Field(default=None, max_length=MAX_FIELD_CHARS)
    font_family: str | None = Field(default=None, max_length=64)

TEMPLATE = r"""
\documentclass[border=0pt]{{standalone}}
\usepackage{{tikz}}
\usepackage{{luacode}}
\usepackage{{tkz-euclide}}
\usepackage{{tkz-elements}}
\usepackage{{amsmath}}
\usepackage{{fontspec}}
\setmainfont{{{font_family}}}[
  UprightFont    = *-Regular,
  BoldFont       = *-Bold,
  ItalicFont     = *-Italic,
  BoldItalicFont = *-BoldItalic,
  Extension      = .ttf,
  Path           = {font_path}
]
\begin{{document}}
{tkzelements_block}
\begin{{tikzpicture}}
{tikz}
\end{{tikzpicture}}
\end{{document}}
""".lstrip()


class CommandTimeout(Exception):
    """A subprocess exceeded TIMEOUT_S and was killed."""


async def run_cmd(cmd: list[str], cwd: str) -> tuple[int, str]:
    """Run ``cmd`` without blocking the event loop; return (returncode, output).

    Raises CommandTimeout (after killing the process) past TIMEOUT_S."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=SUBPROCESS_ENV,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_S)
    except (asyncio.TimeoutError, asyncio.CancelledError) as e:
        proc.kill()
        await proc.wait()
        if isinstance(e, asyncio.CancelledError):
            raise
        raise CommandTimeout(f"{cmd[0]} timed out after {TIMEOUT_S}s") from e
    return proc.returncode, out.decode("utf-8", errors="replace")


async def render_svg(req: RenderReq) -> dict:
    async with sem:
        with tempfile.TemporaryDirectory() as td:
            tkze = ""
            if req.tkzelements:
                tkze = "\\begin{tkzelements}\n" + req.tkzelements + "\n\\end{tkzelements}\n"

            family = req.font_family or "NunitoSans"
            if not re.fullmatch(r"[A-Za-z0-9_-]+", family):
                return {"ok": False, "stage": "validation", "log": f"Invalid font_family: {family!r}"}
            font_path = f"/usr/local/share/fonts/{family}/"
            tex = TEMPLATE.format(
                font_family=family,
                font_path=font_path,
                tkzelements_block=tkze,
                tikz=req.tikz,
            )
            tex_path = os.path.join(td, "main.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex)

            # 1) lualatex -> PDF
            try:
                code1, out1 = await run_cmd([
                    "lualatex",
                    "--no-shell-escape",
                    "--interaction=nonstopmode",
                    "--halt-on-error",
                    "-file-line-error",
                    "main.tex",
                ], cwd=td)
            except CommandTimeout as e:
                logger.warning("lualatex timed out")
                return {"ok": False, "stage": "lualatex", "log": str(e)}

            if code1 != 0:
                logger.warning("lualatex failed: %s", out1)
                return {"ok": False, "stage": "lualatex", "log": out1}

            logger.info("lualatex succeeded: %s", out1)

            # 2) dvisvgm -> SVG
            try:
                code2, out2 = await run_cmd([
                    "dvisvgm",
                    "--no-fonts",
                    "--pdf",
                    "--bbox=min",
                    "--exact-bbox",
                    "-Oall",
                    "-o", "out.svg",
                    "main.pdf",
                ], cwd=td)
            except CommandTimeout as e:
                logger.warning("dvisvgm timed out")
                return {"ok": False, "stage": "dvisvgm", "log": str(e)}

            if code2 != 0 or not os.path.exists(os.path.join(td, "out.svg")):
                logger.warning("dvisvgm failed: %s", out2)
                return {"ok": False, "stage": "dvisvgm", "log": out2}

            logger.info("dvisvgm succeeded: %s", out2)

            with open(os.path.join(td, "out.svg"), "r", encoding="utf-8") as f:
                svg = f.read()

            return {"ok": True, "svg": svg, "log": out1 + "\n" + out2}


async def worker() -> None:
    """Pull queued requests forever and resolve their futures."""
    while True:
        req, fut = await queue.get()
        try:
            if fut.done():
                # The handler gave up (timeout or disconnect) while it queued.
                continue
            try:
                res = await render_svg(req)
            except Exception as e:
                res = {"ok": False, "stage": "exception", "log": repr(e)}
            if not fut.done():
                fut.set_result(res)
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global sem, queue
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    # Strong references: the loop keeps only weak ones to tasks, and a
    # cancelled request handler must never take a worker down with it.
    app.state.workers = [asyncio.create_task(worker()) for _ in range(MAX_CONCURRENT)]
    try:
        yield
    finally:
        for task in app.state.workers:
            task.cancel()
        await asyncio.gather(*app.state.workers, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


@app.post("/render")
async def render(req: RenderReq):
    if queue.full():
        raise HTTPException(status_code=429, detail="Render queue full")

    fut = asyncio.get_running_loop().create_future()
    await queue.put((req, fut))
    try:
        return await asyncio.wait_for(fut, timeout=REQUEST_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Render timed out")


@app.get("/health")
async def health():
    return {"status": "ok"}
