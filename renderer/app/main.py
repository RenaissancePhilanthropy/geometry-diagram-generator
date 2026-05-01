import asyncio
import os
import re
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
    font_family: str | None = None

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
            p1 = run_cmd([
                "lualatex",
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
            p2 = run_cmd([
                "dvisvgm",
                "--no-fonts",
                "--pdf",
                "--bbox=min",
                "--exact-bbox",
                "-Oall",
                "-o", "out.svg",
                "main.pdf",
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