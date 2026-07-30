"""Persistence for Lingua.

Two backends, selected automatically:

- **Supabase Postgres** (when `SUPABASE_DB_URL` is set — the real production
  path): users, progress, and every other row live in a durable, external
  database, so a Fly restart, redeploy, or machine replacement never loses
  a session's underlying data.
- **SQLite** (when it isn't set): a local file, used for local dev without a
  Supabase project and for the test suite, which stays fully offline and
  fast — each test gets its own throwaway file via `reset_for_tests`.

Every call site elsewhere in the app (`srs.py`, `routers/*.py`) uses the same
`db.cursor()` context manager and `?`-style placeholders regardless of which
backend is active — `_CursorProxy` below translates placeholders for Postgres
so none of those call sites need to know which engine they're talking to.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from .config import settings

logger = logging.getLogger("lingua.db")

# RLock, not Lock: cursor()'s reconnect-and-retry path re-enters this lock
# from the same thread (see cursor() below) — a plain Lock would deadlock.
_lock = threading.RLock()

_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    native_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'A1',
    interests TEXT NOT NULL DEFAULT '[]',
    xp INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    hearts INTEGER NOT NULL DEFAULT 5,
    gems INTEGER NOT NULL DEFAULT 0,
    streak_freezes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_active_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocab_progress (
    user_id TEXT NOT NULL,
    vocab_key TEXT NOT NULL,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_result TEXT NOT NULL DEFAULT '',
    mistake_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, vocab_key)
);

CREATE TABLE IF NOT EXISTS lesson_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    score REAL NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unit_mastery (
    user_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    best_score REAL NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    mastered INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, unit_id)
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    native_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'A1',
    interests TEXT NOT NULL DEFAULT '[]',
    xp INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    hearts INTEGER NOT NULL DEFAULT 5,
    gems INTEGER NOT NULL DEFAULT 0,
    streak_freezes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_active_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocab_progress (
    user_id TEXT NOT NULL,
    vocab_key TEXT NOT NULL,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_result TEXT NOT NULL DEFAULT '',
    mistake_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, vocab_key)
);

CREATE TABLE IF NOT EXISTS lesson_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    score REAL NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unit_mastery (
    user_id TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    best_score REAL NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    mastered INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, unit_id)
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vocab_progress_due ON vocab_progress(user_id, due_at);
CREATE INDEX IF NOT EXISTS idx_conversation_log_user ON conversation_log(user_id, id);
"""


def _is_postgres() -> bool:
    return bool(settings.supabase_db_url)


class _CursorProxy:
    """Wraps a driver cursor so every call site can keep using `?`
    placeholders and dict-like row access regardless of which engine is
    live. psycopg's dict_row factory already returns plain dicts (so
    `row["col"]` and `dict(row)` work unchanged); this only needs to
    translate placeholder syntax for Postgres."""

    __slots__ = ("_cur", "_translate")

    def __init__(self, cur: Any, translate: bool) -> None:
        self._cur = cur
        self._translate = translate

    def execute(self, query: str, params: tuple = ()) -> Any:
        if self._translate:
            query = query.replace("?", "%s")
        return self._cur.execute(query, params)

    def executescript(self, script: str) -> Any:
        return self._cur.execute(script)

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def fetchall(self) -> Any:
        return self._cur.fetchall()

    def close(self) -> None:
        self._cur.close()


def _connect_sqlite() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_postgres() -> Any:
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(settings.supabase_db_url, row_factory=dict_row, autocommit=False)
    return conn


def _migrate_sqlite(conn: sqlite3.Connection) -> None:
    """Adds columns/indexes introduced after a table already existed on disk.
    CREATE TABLE IF NOT EXISTS alone won't retrofit a pre-existing users.db."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "email" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "gems" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN gems INTEGER NOT NULL DEFAULT 0")
    if "streak_freezes" not in existing_cols:
        conn.execute("ALTER TABLE users ADD COLUMN streak_freezes INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
    conn.commit()


def _migrate_postgres(conn: Any) -> None:
    """Postgres supports IF NOT EXISTS on ALTER TABLE directly, so no
    introspection dance is needed like the SQLite path above."""
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gems INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS streak_freezes INTEGER NOT NULL DEFAULT 0")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
    conn.commit()


_conn: Any = None


def _exec_statements(conn: Any, script: str) -> None:
    """Runs each `;`-separated statement individually rather than handing the
    whole script to one execute() call — psycopg doesn't reliably support
    multi-statement batches the way sqlite3's executescript() does."""
    with conn.cursor() as cur:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)


def _new_postgres_connection() -> Any:
    conn = _connect_postgres()
    _exec_statements(conn, _SCHEMA_POSTGRES)
    conn.commit()
    _migrate_postgres(conn)
    logger.info("Connected to Supabase Postgres — data persists across restarts/redeploys.")
    return conn


def _new_sqlite_connection() -> Any:
    conn = _connect_sqlite()
    conn.executescript(_SCHEMA_SQLITE)
    conn.commit()
    _migrate_sqlite(conn)
    logger.warning(
        "Using local SQLite (%s). Fine for local dev/tests; a real deploy should configure "
        "SUPABASE_DB_URL so data survives restarts.",
        settings.db_path,
    )
    return conn


def _new_connection() -> Any:
    if not _is_postgres():
        return _new_sqlite_connection()
    try:
        return _new_postgres_connection()
    except Exception:
        logger.exception(
            "Could not connect to SUPABASE_DB_URL — falling back to local SQLite for this "
            "process. Data will NOT persist across restarts until this is fixed. Check the "
            "connection string (see README's Supabase section)."
        )
        # Stop retrying Postgres for the rest of this process; a restart (e.g. after fixing
        # the secret) tries again fresh, since this only clears the in-memory setting.
        object.__setattr__(settings, "supabase_db_url", "")
        return _new_sqlite_connection()


def _is_alive(conn: Any) -> bool:
    try:
        with conn.cursor() as probe:
            probe.execute("SELECT 1")
        conn.commit()
        return True
    except Exception:
        return False


def get_conn() -> Any:
    global _conn
    with _lock:
        # Supabase's pooler can drop idle connections; a stale connection only
        # errors on the next query, not on acquiring it — so check liveness
        # proactively rather than trying to retry a caller's query after the
        # fact (which could double-run side effects if execute() had already
        # partially run).
        if _conn is not None and _is_postgres() and not _is_alive(_conn):
            logger.warning("Postgres connection stale — reconnecting.")
            with contextlib.suppress(Exception):
                _conn.close()
            _conn = None
        if _conn is None:
            _conn = _new_connection()
    return _conn


@contextlib.contextmanager
def cursor() -> Iterator[_CursorProxy]:
    conn = get_conn()
    translate = _is_postgres()
    with _lock:
        cur = conn.cursor()
        proxy = _CursorProxy(cur, translate)
        try:
            yield proxy
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def today_str() -> str:
    return datetime.now(UTC).date().isoformat()


def row_to_dict(row: Any) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    if "interests" in d:
        d["interests"] = json.loads(d["interests"] or "[]")
    return d


def reset_for_tests(db_path: str) -> None:
    """Used by the test-suite to point at an isolated temp SQLite file.
    Tests never set SUPABASE_DB_URL, so this always exercises the SQLite
    path — the offline, no-external-dependency test guarantee is unchanged."""
    global _conn
    object.__setattr__(settings, "db_path", db_path)
    object.__setattr__(settings, "supabase_db_url", "")
    _conn = None
