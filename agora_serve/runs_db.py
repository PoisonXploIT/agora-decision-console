"""Persistencia del historial de decisiones en SQLite.

Antes vivia en memoria y se perdia al reiniciar. Ahora:

    ~/.agora/runs.db   (o AGORA_CONFIG_DIR/runs.db)

- Una fila por decision, con la pregunta y el estado (hasta 8 KB) para replay.
- Se guardan los ultimos MAX_RUNS (poda al insertar).
- Conexion corta por llamada y WAL: el servicio es de un solo usuario.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

MAX_RUNS = 5000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  backend TEXT,
  question_id TEXT,
  question TEXT,
  state TEXT,
  type TEXT,
  probabilities TEXT,
  expected REAL,
  action TEXT,
  latency_ms REAL,
  replay_of TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_runs_backend ON runs(backend);
"""


def config_dir() -> Path:
    d = os.environ.get("AGORA_CONFIG_DIR")
    return Path(d) if d else (Path.home() / ".agora")


def db_path() -> Path:
    return config_dir() / "runs.db"


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    return c


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def _from_json(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def insert(item: dict[str, Any]) -> dict[str, Any]:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (id, ts, backend, question_id, question, state,"
            " type, probabilities, expected, action, latency_ms, replay_of)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.get("id") or f"run-{int(time.time() * 1000)}",
                float(item.get("ts") or time.time()),
                item.get("backend"),
                item.get("question_id"),
                _to_json(item.get("question")),
                _to_json(item.get("state")),
                item.get("type"),
                _to_json(item.get("probabilities")),
                item.get("expected"),
                item.get("action"),
                float(item.get("latency_ms") or 0.0),
                item.get("replay_of"),
            ),
        )
        c.execute(
            "DELETE FROM runs WHERE id IN ("
            "  SELECT id FROM runs ORDER BY ts DESC LIMIT -1 OFFSET ?)",
            (MAX_RUNS,),
        )
    return item


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": r["id"],
        "ts": r["ts"],
        "backend": r["backend"],
        "question_id": r["question_id"],
        "question": _from_json(r["question"]),
        "state": _from_json(r["state"]),
        "type": r["type"],
        "probabilities": _from_json(r["probabilities"]) or {},
        "expected": r["expected"],
        "action": r["action"],
        "latency_ms": r["latency_ms"],
        "replay_of": r["replay_of"],
    }


def list_runs(limit: int = 50, offset: int = 0,
              backend: str | None = None) -> tuple[int, list[dict[str, Any]]]:
    with _conn() as c:
        where = " WHERE backend = ?" if backend else ""
        params: tuple = (backend,) if backend else ()
        total = c.execute(f"SELECT COUNT(*) FROM runs{where}", params).fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM runs{where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            (*params, max(1, min(1000, limit)), max(0, offset)),
        ).fetchall()
    return total, [_row(r) for r in rows]


def get(run_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _row(r) if r else None


def delete(run_id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM runs WHERE id=?", (run_id,))
        return cur.rowcount > 0


def clear() -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM runs")
        return cur.rowcount


def count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
