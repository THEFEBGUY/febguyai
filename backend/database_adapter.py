from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""


class DatabaseService:
    """Small database adapter layer.

    Phase 0.7 keeps the app data plane on SQLite for stability. Postgres is
    connected and health-checked here so the next migration can move table
    repositories one by one without spreading provider logic through main.py.
    """

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.requested_provider = self._normalize_provider(settings.provider)

    @staticmethod
    def _normalize_provider(provider: str | None) -> str:
        value = (provider or "sqlite").strip().lower()
        if value in {"postgresql", "supabase"}:
            return "postgres"
        if value in {"sqlite", "postgres", "auto"}:
            return value
        return "sqlite"

    def sqlite_connect(self) -> sqlite3.Connection:
        self.settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.settings.sqlite_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def postgres_connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        if not self.settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(
            self.settings.database_url,
            connect_timeout=max(1, int(self.settings.connect_timeout or 5)),
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
            with self.postgres_connect() as conn:
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
        sqlite = self.sqlite_health()
        postgres = self.postgres_health()

        # Current CRUD still uses SQLite SQL. Provider preference is recorded
        # here, but active app data stays SQLite until repository migration.
        active_provider = "sqlite" if sqlite.get("available") else "unavailable"

        return {
            "active_provider": active_provider,
            "requested_provider": self.requested_provider,
            "sqlite_available": bool(sqlite.get("available")),
            "postgres_configured": bool(postgres.get("configured")),
            "postgres_connected": bool(postgres.get("connected")),
            "sqlite": sqlite,
            "postgres": postgres,
            "supabase": self.supabase_status(),
            "migration_mode": "sqlite_active_postgres_ready"
            if postgres.get("connected")
            else "sqlite_active_postgres_pending",
        }
