"""Local server for the GeoGenBench human-correlation study viewer.

Run from the repo root:

    .venv/bin/python -m evals.human_study.serve --rater mei

This starts a tiny HTTP server on http://localhost:8765 (configurable),
serves the static viewer and the SVG files from disk, and accepts POSTs to
/human_study/save which write rater responses directly to:

    evals/human_study/responses_<rater>.csv

The page auto-saves on every answer; raters never have to manually download
CSVs. The CSV is also incrementally sortable so daily git commits are clean.
"""

from __future__ import annotations

import argparse
import csv
import http.server
import json
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
HUMAN_STUDY_DIR = REPO_ROOT / "evals" / "human_study"
DEFAULT_PORT = 8765

CSV_HEADERS = [
    "item_id", "scenario_id", "model", "strategy", "tier",
    "auto_verdict",
    "q1_overall",
    "q2_predicate", "q2_agreement",
    "notes",
    "rater_id", "answered_at",
]


def _csv_path(rater: str) -> Path:
    safe = "".join(c for c in rater if c.isalnum() or c in "_-").lower() or "anon"
    return HUMAN_STUDY_DIR / f"responses_{safe}.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open() as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})


class StudyHandler(http.server.SimpleHTTPRequestHandler):
    """Serve from the repo root + handle a POST /human_study/save."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        if "/human_study/save" in args[0] if args else False:
            super().log_message(fmt, *args)
        elif self.path.endswith(".svg") or self.path.endswith(".json") or self.path.endswith(".html"):
            return
        else:
            super().log_message(fmt, *args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/human_study/save":
            self._send_json(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except json.JSONDecodeError as e:
            self._send_json(400, {"error": "bad_json", "detail": str(e)})
            return

        rater = body.get("rater_id")
        rows = body.get("rows", [])
        if not rater or not isinstance(rows, list):
            self._send_json(400, {"error": "missing_rater_or_rows"})
            return

        path = _csv_path(rater)

        try:
            rows.sort(key=lambda r: (r.get("item_id", ""), r.get("q2_predicate", "")))
            _write_csv(path, rows)
        except OSError as e:
            self._send_json(500, {"error": "write_failed", "detail": str(e)})
            return

        self._send_json(200, {"ok": True, "wrote": len(rows), "path": str(path.relative_to(REPO_ROOT))})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/human_study/load":
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            rater = (params.get("rater") or [""])[0]
            if not rater:
                self._send_json(400, {"error": "missing_rater"})
                return
            rows = _read_csv(_csv_path(rater))
            self._send_json(200, {"ok": True, "rows": rows})
            return
        super().do_GET()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--rater", type=str, default="", help="Default rater name (used in opened URL)")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()

    sample_path = HUMAN_STUDY_DIR / "sample.json"
    if not sample_path.exists():
        print(f"ERROR: {sample_path} not found.")
        print("Run:  .venv/bin/python -m evals.human_study.sample_human_study")
        return 2

    rel = lambda p: str(p.relative_to(REPO_ROOT))
    qs = f"?rater={args.rater}" if args.rater else ""
    url = f"http://localhost:{args.port}/{rel(HUMAN_STUDY_DIR / 'viewer.html')}{qs}"

    print(f"Serving from {REPO_ROOT}")
    print(f"Sample:  {rel(sample_path)} ({sample_path.stat().st_size // 1024} KB)")
    if args.rater:
        print(f"Rater:   {args.rater}  (responses -> {rel(_csv_path(args.rater))})")
    print(f"\nOpen:    {url}\n")

    if not args.no_open:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), StudyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
