from __future__ import annotations

import sqlite3
import queue
import threading
import uuid as uuid_module
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

try:
    import psycopg
except Exception:
    psycopg = None


@dataclass(frozen=True)
class DatabaseSettings:
    sqlite_path: Path
    database_url: str = ""
    provider: str = "sqlite"
    connect_timeout: int = 5
    statement_timeout_ms: int = 5000
    lock_timeout_ms: int = 3000
    pool_max_size: int = 5
    pool_timeout: int = 5
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""


class DatabaseService:
    """Small database adapter layer.

    The app's repository code is intentionally SQLite-shaped. This adapter
    keeps local SQLite untouched while allowing production Postgres/Supabase
    to satisfy the same connection, row, and placeholder expectations.
    """

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.requested_provider = self._normalize_provider(settings.provider)
        self._pool_lock = threading.Lock()
        self._postgres_pool: queue.LifoQueue[Any] | None = None
        self._postgres_pool_open_connections = 0

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        value = (provider or "sqlite").strip().lower()
        if value in {"postgresql", "supabase"}:
            return "postgres"
        if value in {"sqlite", "postgres", "auto"}:
            return value
        return "sqlite"

    @property
    def active_provider(self) -> str:
        if self.requested_provider == "auto":
            return "postgres" if self.settings.database_url else "sqlite"
        return self.requested_provider

    def is_sqlite_active(self) -> bool:
        return self.active_provider == "sqlite"

    def is_postgres_active(self) -> bool:
        return self.active_provider == "postgres"

    def connect(self):
        if self.is_postgres_active():
            if self._postgres_pool_max_size() > 0:
                return PostgresCompatConnection(
                    self.acquire_postgres_connection(),
                    release=self.release_postgres_connection,
                )
            return PostgresCompatConnection(self.postgres_connect())
        return self.sqlite_connect()

    def sqlite_connect(self) -> sqlite3.Connection:
        self.settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.settings.sqlite_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def postgres_connect(self, connect_timeout: int | None = None):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        if not self.settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        timeout = (
            self.settings.connect_timeout
            if connect_timeout is None
            else connect_timeout
        )
        connect_kwargs: dict[str, Any] = {
            "connect_timeout": max(1, int(timeout or 5)),
            "prepare_threshold": None,
        }
        options = self._postgres_connect_options()
        if options:
            connect_kwargs["options"] = options
        conn = psycopg.connect(self.settings.database_url, **connect_kwargs)
        try:
            conn.prepare_threshold = None
        except Exception:
            pass
        return conn

    def _postgres_connect_options(self) -> str:
        options = ["-c search_path=public"]
        if self.settings.statement_timeout_ms:
            options.append(
                f"-c statement_timeout={max(1, int(self.settings.statement_timeout_ms))}"
            )
        if self.settings.lock_timeout_ms:
            options.append(
                f"-c lock_timeout={max(1, int(self.settings.lock_timeout_ms))}"
            )
        return " ".join(options)

    def _postgres_pool_max_size(self) -> int:
        return max(0, int(self.settings.pool_max_size or 0))

    def _postgres_pool_timeout(self) -> int:
        return max(1, int(self.settings.pool_timeout or self.settings.connect_timeout or 5))

    def _ensure_postgres_pool(self) -> queue.LifoQueue[Any]:
        if self._postgres_pool is None:
            with self._pool_lock:
                if self._postgres_pool is None:
                    self._postgres_pool = queue.LifoQueue(
                        maxsize=max(1, self._postgres_pool_max_size())
                    )
        return self._postgres_pool

    @staticmethod
    def _postgres_connection_usable(conn: Any) -> bool:
        return not bool(getattr(conn, "closed", False))

    def acquire_postgres_connection(self):
        pool = self._ensure_postgres_pool()
        while True:
            try:
                conn = pool.get_nowait()
            except queue.Empty:
                break
            if self._postgres_connection_usable(conn):
                return conn
            self._discard_postgres_connection(conn)

        should_open = False
        with self._pool_lock:
            if self._postgres_pool_open_connections < self._postgres_pool_max_size():
                self._postgres_pool_open_connections += 1
                should_open = True

        if should_open:
            try:
                return self.postgres_connect()
            except Exception:
                with self._pool_lock:
                    self._postgres_pool_open_connections = max(
                        0,
                        self._postgres_pool_open_connections - 1,
                    )
                raise

        while True:
            conn = pool.get(timeout=self._postgres_pool_timeout())
            if self._postgres_connection_usable(conn):
                return conn
            self._discard_postgres_connection(conn)

    def release_postgres_connection(self, conn: Any, reusable: bool) -> None:
        if not reusable or not self._postgres_connection_usable(conn):
            self._discard_postgres_connection(conn)
            return
        pool = self._ensure_postgres_pool()
        try:
            pool.put_nowait(conn)
        except queue.Full:
            self._discard_postgres_connection(conn)

    def _discard_postgres_connection(self, conn: Any) -> None:
        try:
            conn.close()
        except Exception:
            pass
        with self._pool_lock:
            self._postgres_pool_open_connections = max(
                0,
                self._postgres_pool_open_connections - 1,
            )

    def supabase_status(self) -> dict[str, bool]:
        return {
            "url_configured": bool(self.settings.supabase_url),
            "anon_key_configured": bool(self.settings.supabase_anon_key),
            "service_role_key_configured": bool(self.settings.supabase_service_role_key),
            "database_url_configured": bool(self.settings.database_url),
        }

    def sqlite_health(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "available": False,
            "configured": True,
        }
        try:
            with self.sqlite_connect() as conn:
                conn.execute("SELECT 1").fetchone()
            status["available"] = True
            status["status"] = "available"
        except Exception as exc:
            status["status"] = "error"
            status["error_type"] = type(exc).__name__
            status["message"] = "SQLite is unavailable. Check local data directory permissions."
        return status

    def postgres_health(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "configured": bool(self.settings.database_url),
            "driver": "psycopg" if psycopg is not None else "missing",
            "connected": False,
        }

        if not self.settings.database_url:
            status["status"] = "not_configured"
            return status

        if psycopg is None:
            status["status"] = "driver_missing"
            status["message"] = "Install psycopg from backend requirements, then restart the backend."
            return status

        try:
            health_timeout = min(2, max(1, int(self.settings.connect_timeout or 5)))
            with self.postgres_connect(connect_timeout=health_timeout) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            status["status"] = "connected"
            status["connected"] = True
        except Exception as exc:
            status["status"] = "error"
            status["error_type"] = type(exc).__name__
            status["message"] = (
                "Could not connect to Supabase Postgres. "
                "Check DATABASE_URL, network access, and Supabase pooler settings."
            )
        return status

    def safe_health(self) -> dict[str, Any]:
        sqlite = self.sqlite_health() if self.is_sqlite_active() else {
            "available": False,
            "configured": True,
            "status": "inactive",
        }
        postgres = self.postgres_health()
        active_provider = self.active_provider
        active_available = (
            bool(sqlite.get("available"))
            if active_provider == "sqlite"
            else bool(postgres.get("connected"))
        )

        return {
            "active_provider": active_provider if active_available else "unavailable",
            "requested_provider": self.requested_provider,
            "database_url_required": active_provider == "postgres",
            "sqlite_available": bool(sqlite.get("available")),
            "postgres_configured": bool(postgres.get("configured")),
            "postgres_connected": bool(postgres.get("connected")),
            "sqlite": sqlite,
            "postgres": postgres,
            "supabase": self.supabase_status(),
            "migration_mode": "postgres_active"
            if active_provider == "postgres"
            else "sqlite_active",
        }


class CompatRow(Mapping[str, Any]):
    def __init__(self, columns: Iterable[str], values: Iterable[Any]):
        self._columns = list(columns)
        self._values = tuple(self._normalize_value(value) for value in values)
        self._index = {column: index for index, column in enumerate(self._columns)}

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, uuid_module.UUID):
            return str(value)
        return value

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self) -> list[str]:
        return list(self._columns)


class PostgresCompatCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns: list[str] = []

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def execute(self, sql: str, params: Iterable[Any] | None = None):
        translated_sql, translated_params = translate_sql(sql, params)
        self._cursor.execute(translated_sql, translated_params)
        self._columns = [
            column.name for column in (self._cursor.description or [])
        ]
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return CompatRow(self._columns, row)

    def fetchall(self) -> list[CompatRow]:
        return [CompatRow(self._columns, row) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()


class PostgresCompatConnection:
    def __init__(self, conn, release=None):
        self._conn = conn
        self._release = release
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        reusable = False
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            reusable = True
        except Exception:
            reusable = False
            if exc_type is None:
                raise
        finally:
            self._finish(reusable)
        return False

    def _finish(self, reusable: bool) -> None:
        if self._closed:
            return
        self._closed = True
        if self._release:
            self._release(self._conn, reusable)
            return
        self._conn.close()

    def execute(self, sql: str, params: Iterable[Any] | None = None) -> PostgresCompatCursor:
        cursor = PostgresCompatCursor(self._conn.cursor())
        try:
            return cursor.execute(sql, params)
        except Exception:
            cursor.close()
            raise

    def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]) -> PostgresCompatCursor:
        cursor = PostgresCompatCursor(self._conn.cursor())
        translated_sql, _ = translate_sql(sql, None)
        try:
            cursor._cursor.executemany(translated_sql, list(seq_of_params))
            return cursor
        except Exception:
            cursor.close()
            raise

    def executescript(self, script: str) -> None:
        for statement in split_sql_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        reusable = False
        try:
            self._conn.commit()
            reusable = True
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
        finally:
            self._finish(reusable)


def translate_sql(sql: str, params: Iterable[Any] | None) -> tuple[str, Iterable[Any] | None]:
    stripped = sql.strip()
    pragma_table = parse_pragma_table_info(stripped)
    if pragma_table:
        return (
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
                AND table_name = %s
            ORDER BY ordinal_position
            """,
            (pragma_table,),
        )
    return replace_sqlite_placeholders(sql), params


def parse_pragma_table_info(sql: str) -> str | None:
    lowered = sql.lower()
    prefix = "pragma table_info("
    if not lowered.startswith(prefix) or not lowered.endswith(")"):
        return None
    table_name = sql[len(prefix):-1].strip().strip('"').strip("'")
    if not table_name.replace("_", "").isalnum():
        return None
    return table_name


def replace_sqlite_placeholders(sql: str) -> str:
    output: list[str] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not in_double:
            output.append(char)
            if in_single and index + 1 < len(sql) and sql[index + 1] == "'":
                output.append(sql[index + 1])
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            output.append(char)
            in_double = not in_double
        elif char == "?" and not in_single and not in_double:
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


def split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(script):
        char = script[index]
        current.append(char)
        if char == "'" and not in_double:
            if in_single and index + 1 < len(script) and script[index + 1] == "'":
                current.append(script[index + 1])
                index += 2
                continue
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements
