import asyncio
import os
import subprocess
import tempfile
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from logging import getLogger

logger = getLogger(__name__)

# PoC knobs
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "2"))
QUEUE_SIZE = int(os.getenv("QUEUE_SIZE", "64"))
TIMEOUT_S = int(os.getenv("RENDER_TIMEOUT_S", "15"))

app = FastAPI()
sem = asyncio.Semaphore(MAX_CONCURRENT)
queue = asyncio.Queue(maxsize=QUEUE_SIZE)

class RenderReq(BaseModel):
    tikz: str
    tkzelements: str | None = None  # optional block for tkz-elements

TEMPLATE = r"""
\documentclass[dvisvgm,border=0pt]{{standalone}}
\usepackage{{tikz}}
\usepackage{{luacode}}
\usepackage{{tkz-euclide}}
\usepackage{{tkz-elements}}
\usepackage{{amsmath}}
\begin{{document}}
{tkzelements_block}
\begin{{tikzpicture}}
{tikz}
\end{{tikzpicture}}
\end{{document}}
""".lstrip()

def run_cmd(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=TIMEOUT_S,
    )

async def render_svg(req: RenderReq) -> dict:
    async with sem:
        with tempfile.TemporaryDirectory() as td:
            tkze = ""
            if req.tkzelements:
                tkze = "\\begin{tkzelements}\n" + req.tkzelements + "\n\\end{tkzelements}\n"

            tex = TEMPLATE.format(tkzelements_block=tkze, tikz=req.tikz)
            tex_path = os.path.join(td, "main.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(tex)

            # 1) lualatex -> DVI (per TikZ docs for dvisvgm flow) :contentReference[oaicite:15]{index=15}
            p1 = run_cmd([
                "lualatex",
                "--output-format=dvi",
                "--interaction=nonstopmode",
                "--halt-on-error",
                "-file-line-error",
                "main.tex",
            ], cwd=td)

            if p1.returncode != 0:
                logger.warning("lualatex failed: %s", p1.stdout)
                return {"ok": False, "stage": "lualatex", "log": p1.stdout}

            logger.info("lualatex succeeded: %s", p1.stdout)

            # 2) dvisvgm -> SVG
            # --no-fonts improves browser compatibility :contentReference[oaicite:16]{index=16}
            # --bbox=min gives a tight bbox :contentReference[oaicite:17]{index=17}
            # --exact-bbox can avoid clipped glyphs :contentReference[oaicite:18]{index=18}
            p2 = run_cmd([
                "dvisvgm",
                "--no-fonts",
                "--bbox=min",
                "--exact-bbox",
                "-Oall",
                "-o", "out.svg",
                "main.dvi",
            ], cwd=td)

            if p2.returncode != 0 or not os.path.exists(os.path.join(td, "out.svg")):
                logger.warning("dvisvgm failed: %s", p2.stdout)
                return {"ok": False, "stage": "dvisvgm", "log": p2.stdout}

            logger.info("dvisvgm succeeded: %s", p2.stdout)
            
            with open(os.path.join(td, "out.svg"), "r", encoding="utf-8") as f:
                svg = f.read()

            return {"ok": True, "svg": svg, "log": p1.stdout + "\n" + p2.stdout}

@app.post("/render")
async def render(req: RenderReq):
    if queue.full():
        raise HTTPException(status_code=429, detail="Render queue full")

    fut = asyncio.get_running_loop().create_future()
    await queue.put((req, fut))
    return await fut

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def _startup():
    async def worker():
        while True:
            req, fut = await queue.get()
            try:
                res = await render_svg(req)
                fut.set_result(res)
            except Exception as e:
                fut.set_result({"ok": False, "stage": "exception", "log": repr(e)})
            finally:
                queue.task_done()

    # One dispatcher; concurrency is handled by the semaphore
    asyncio.create_task(worker())