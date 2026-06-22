#!/usr/bin/env bash
set -euo pipefail

# Start the TikZ renderer (FastAPI on port 8001) that compiles TikZ/LaTeX to SVG
# via lualatex -> dvisvgm. Used by `evals.run --renderer tikz`, the genexam
# dry_run, docs/gen_examples, and the eval viewer's re-render.
#
# This box has no Docker, so the renderer runs bare-metal against the
# system TeX toolchain. One-time setup (only needed once per machine):
#   apt-get install -y dvisvgm texlive-luatex
#   mkdir -p /usr/local/share/fonts/NunitoSans
#   cp assets/fonts/NunitoSans-*.ttf /usr/local/share/fonts/NunitoSans/
#   fc-cache -f /usr/local/share/fonts
#   uv pip install fastapi uvicorn
#
# Usage:
#   ./start_tikz_renderer.sh              # foreground (Ctrl-C to stop)
#   ./start_tikz_renderer.sh --background  # detach, log to /tmp/tikz_renderer.log
#   PORT=8011 ./start_tikz_renderer.sh     # custom port
#
# Env knobs (passed through to the server):
#   PORT (default 8001), MAX_CONCURRENT (default 2), QUEUE_SIZE (default 64),
#   RENDER_TIMEOUT_S (default 15)

PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/bin/python"

cd "$ROOT/renderer"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY not found. Run 'uv sync' first." >&2
  exit 1
fi

# Bail out (don't start a duplicate) if something is already serving the port.
if curl -sf -m 2 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
  echo "Renderer already healthy on port ${PORT} — nothing to do."
  exit 0
fi

# Sanity-check the toolchain the server shells out to.
for bin in lualatex dvisvgm; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: '$bin' not found. One-time setup:" >&2
    echo "  apt-get install -y dvisvgm texlive-luatex" >&2
    exit 1
  fi
done
if ! "$PY" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "ERROR: fastapi/uvicorn missing from the venv. One-time setup:" >&2
  echo "  uv pip install fastapi uvicorn" >&2
  exit 1
fi

export MAX_CONCURRENT="${MAX_CONCURRENT:-2}"
export QUEUE_SIZE="${QUEUE_SIZE:-64}"
export RENDER_TIMEOUT_S="${RENDER_TIMEOUT_S:-15}"

if [[ "${1:-}" == "--background" ]]; then
  LOG="${LOG:-/tmp/tikz_renderer.log}"
  nohup "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
  echo "Started renderer on port ${PORT} (pid $!, log $LOG). Waiting for health..."
  for _ in $(seq 1 40); do
    if curl -sf -m 2 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
      echo "Healthy: http://localhost:${PORT}/health"
      exit 0
    fi
    sleep 0.5
  done
  echo "ERROR: renderer did not become healthy within 20s — check $LOG" >&2
  exit 1
else
  echo "Starting renderer on http://localhost:${PORT} (foreground; Ctrl-C to stop)..."
  exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi