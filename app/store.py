"""SQLite storage. Full prompts and replies are never saved, only a short snippet and metadata."""
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()
_db: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    saved_usd REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS developers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE,
    swaps_allowed INTEGER NOT NULL DEFAULT 1,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_roasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    developer_id INTEGER,
    prompt_id TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL,
    issues TEXT NOT NULL DEFAULT '[]',
    ideal_model TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS dev_time (
    developer_id INTEGER PRIMARY KEY,
    seconds REAL NOT NULL DEFAULT 0
);
"""
# Added after the first release, so existing databases need them too.
CALL_COLUMNS = {
    "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
    "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
    "developer_id": "INTEGER",
    "prompt_id": "TEXT NOT NULL DEFAULT ''",
    "request_class": "TEXT NOT NULL DEFAULT ''",
    "prompt_snippet": "TEXT NOT NULL DEFAULT ''",
    "task_kind": "TEXT NOT NULL DEFAULT ''",
    "ideal_model": "TEXT NOT NULL DEFAULT ''",
    "decided_by": "TEXT NOT NULL DEFAULT ''",
    "simulated": "INTEGER NOT NULL DEFAULT 0",
}


def _migrate() -> None:
    existing = {row["name"] for row in _db.execute("PRAGMA table_info(calls)")}
    for name, definition in CALL_COLUMNS.items():
        if name not in existing:
            _db.execute(f"ALTER TABLE calls ADD COLUMN {name} {definition}")
    _db.execute("UPDATE OR IGNORE settings SET key = 'use_recommended' WHERE key = 'auto_downshift'")
    _db.execute("DELETE FROM settings WHERE key = 'auto_downshift'")
    _db.execute("CREATE INDEX IF NOT EXISTS calls_prompt ON calls (prompt_id)")


def init(path: str | None = None) -> None:
    global _db
    path = path or config.settings.db_path
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock:
        if _db is not None:
            _db.close()
        _db = sqlite3.connect(path, check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.executescript(SCHEMA)
        _migrate()
        _db.commit()


def _get(key: str, default: str) -> str:
    row = _db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _set(key: str, value: str) -> None:
    _db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_settings() -> dict:
    with _lock:
        return {
            "budget_usd": float(_get("budget_usd", str(config.DEFAULT_BUDGET_USD))),
            "use_recommended": _get("use_recommended", "0") == "1",
            "level": int(_get("level", str(config.DEFAULT_LEVEL))),
            "simulated": _get("simulated", "0") == "1",
        }


def update_settings(
    budget_usd: float | None = None,
    use_recommended: bool | None = None,
    level: int | None = None,
    simulated: bool | None = None,
) -> None:
    with _lock:
        if budget_usd is not None:
            _set("budget_usd", repr(budget_usd))
        if use_recommended is not None:
            _set("use_recommended", "1" if use_recommended else "0")
        if level is not None:
            _set("level", str(level))
        if simulated is not None:
            _set("simulated", "1" if simulated else "0")
        _db.commit()


def lifetime_spend() -> float:
    with _lock:
        return float(_get("lifetime_spend", "0"))


def add_call(**row) -> dict:
    row.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with _lock:
        cursor = _db.execute(
            f"INSERT INTO calls ({columns}) VALUES ({marks})", tuple(row.values())
        )
        # Simulated amounts are estimates, not money, so they never count toward the hard cap.
        if row.get("cost_usd") and not row.get("simulated"):
            _set("lifetime_spend", repr(float(_get("lifetime_spend", "0")) + row["cost_usd"]))
        _db.commit()
        saved = _db.execute("SELECT * FROM calls WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(saved)


def list_calls(limit: int = 100) -> list[dict]:
    """Newest first. A limit of -1 returns everything."""
    with _lock:
        rows = _db.execute("SELECT * FROM calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def prompt_decision(prompt_id: str) -> dict | None:
    """The first rated call of a prompt, whose decision the prompt's later tool rounds reuse."""
    with _lock:
        row = _db.execute(
            "SELECT * FROM calls WHERE prompt_id = ? AND ideal_model != '' ORDER BY id LIMIT 1",
            (prompt_id,),
        ).fetchone()
    return dict(row) if row else None


def totals() -> dict:
    with _lock:
        row = _db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS spent, "
            "COALESCE(SUM(saved_usd), 0) AS saved, "
            "COUNT(*) AS calls, "
            "COALESCE(SUM(status IN ('Blocked by budget', 'Demo limit reached', 'Loop stopped')), 0) "
            "AS blocked FROM calls"
        ).fetchone()
    return dict(row)


def reset() -> None:
    """Clear the demo. The lifetime spend total stays, so reset can't bypass the hard cap."""
    with _lock:
        _db.execute("DELETE FROM calls")
        _db.execute("DELETE FROM dev_time")
        _db.execute("DELETE FROM live_roasts")
        _db.execute("DELETE FROM settings WHERE key IN ('budget_usd', 'use_recommended', 'level')")
        _db.commit()


def _hash(token: str) -> str:
    # Tokens are long and random, so a fast hash is enough here.
    return hashlib.sha256(token.encode()).hexdigest()


def add_developer(name: str) -> tuple[dict, str]:
    """Create a developer. The token is returned once and only its hash is kept."""
    token = f"cd_{secrets.token_urlsafe(32)}"
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _lock:
        _db.execute(
            "INSERT INTO developers (name, token_hash, created) VALUES (?, ?, ?)",
            (name, _hash(token), created),
        )
        _db.commit()
        row = _db.execute("SELECT * FROM developers WHERE name = ?", (name,)).fetchone()
    return dict(row), token


def developer_by_token(token: str) -> dict | None:
    with _lock:
        row = _db.execute(
            "SELECT * FROM developers WHERE token_hash = ?", (_hash(token),)
        ).fetchone()
    return dict(row) if row else None


def get_developer(developer_id: int) -> dict | None:
    with _lock:
        row = _db.execute("SELECT * FROM developers WHERE id = ?", (developer_id,)).fetchone()
    return dict(row) if row else None


def list_developers() -> list[dict]:
    with _lock:
        rows = _db.execute("SELECT * FROM developers ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def set_swaps_allowed(name: str, allowed: bool) -> bool:
    with _lock:
        cursor = _db.execute(
            "UPDATE developers SET swaps_allowed = ? WHERE name = ?", (int(allowed), name)
        )
        _db.commit()
    return cursor.rowcount > 0


def add_live_roast(issues: list[str], **row) -> None:
    row["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row["issues"] = json.dumps(issues)
    columns, marks = ", ".join(row), ", ".join("?" for _ in row)
    with _lock:
        _db.execute(f"INSERT INTO live_roasts ({columns}) VALUES ({marks})", tuple(row.values()))
        _db.commit()


def list_live_roasts(limit: int = 20) -> list[dict]:
    """Newest first."""
    with _lock:
        rows = _db.execute(
            "SELECT * FROM live_roasts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{**dict(row), "issues": json.loads(row["issues"])} for row in rows]


def add_dev_time(developer_id: int, seconds: float) -> None:
    with _lock:
        _db.execute(
            "INSERT INTO dev_time (developer_id, seconds) VALUES (?, ?) "
            "ON CONFLICT(developer_id) DO UPDATE SET seconds = seconds + excluded.seconds",
            (developer_id, seconds),
        )
        _db.commit()


def measured_dev_time() -> dict[int, float]:
    with _lock:
        rows = _db.execute("SELECT developer_id, seconds FROM dev_time").fetchall()
    return {row["developer_id"]: row["seconds"] for row in rows}
