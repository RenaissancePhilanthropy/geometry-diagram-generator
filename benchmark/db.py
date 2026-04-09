from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "benchmark" / "data" / "benchmark.db"

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    benchmark_id TEXT NOT NULL,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    prompt_id TEXT NOT NULL,
    svg_path TEXT,
    tikz_code TEXT,
    generation_success INTEGER NOT NULL DEFAULT 0,
    metadata TEXT,
    UNIQUE(run_id, prompt_id)
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL REFERENCES results(result_id),
    rubric_item_id TEXT NOT NULL,
    annotator_id TEXT NOT NULL,
    annotator_type TEXT NOT NULL,
    value INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(result_id, rubric_item_id, annotator_id)
);
"""


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else _DEFAULT_DB_PATH
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    return conn


def insert_run(conn: sqlite3.Connection, run_id: str, benchmark_id: str, label: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO runs (run_id, benchmark_id, label, created_at) VALUES (?, ?, ?, ?)",
        (run_id, benchmark_id, label, created_at),
    )
    conn.commit()


def insert_result(
    conn: sqlite3.Connection,
    result_id: str,
    run_id: str,
    prompt_id: str,
    svg_path: str | None,
    tikz_code: str | None,
    generation_success: bool,
    metadata: dict[str, Any] | None,
) -> None:
    metadata_json = json.dumps(metadata) if metadata is not None else None
    conn.execute(
        """
        INSERT INTO results
            (result_id, run_id, prompt_id, svg_path, tikz_code, generation_success, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (result_id, run_id, prompt_id, svg_path, tikz_code, int(generation_success), metadata_json),
    )
    conn.commit()


def upsert_annotation(
    conn: sqlite3.Connection,
    result_id: str,
    rubric_item_id: str,
    annotator_id: str,
    annotator_type: str,
    value: int,
) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR REPLACE INTO annotations
            (result_id, rubric_item_id, annotator_id, annotator_type, value, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (result_id, rubric_item_id, annotator_id, annotator_type, value, created_at),
    )
    conn.commit()


def get_annotations_for_result(conn: sqlite3.Connection, result_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE result_id = ?", (result_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def get_result(conn: sqlite3.Connection, result_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM results WHERE result_id = ?", (result_id,)).fetchone()
    if row is None:
        return None
    row_dict = dict(row)
    if row_dict.get("metadata"):
        row_dict["metadata"] = json.loads(row_dict["metadata"])
    return row_dict


def list_runs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def list_results_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM results WHERE run_id = ?", (run_id,)
    ).fetchall()
    result = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("metadata"):
            row_dict["metadata"] = json.loads(row_dict["metadata"])
        result.append(row_dict)
    return result
