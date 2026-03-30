from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg2
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.database.connection import DATABASE_URL, database_health, init_db  # noqa: E402


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _psycopg2_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    scheme = parsed.scheme.split("+", 1)[0]
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _target_db_name(database_url: str) -> str:
    database_name = urlsplit(database_url).path.lstrip("/")
    if not database_name:
        raise RuntimeError("DATABASE_URL must include a database name.")
    return database_name


def _admin_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL must use a PostgreSQL driver.")

    admin_db = os.getenv("POSTGRES_ADMIN_DB", "postgres")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{admin_db}", parsed.query, parsed.fragment))


def _ensure_database_exists(database_url: str) -> None:
    target_db = _target_db_name(database_url)
    admin_url = _psycopg2_url(_admin_database_url(database_url))

    connection = psycopg2.connect(admin_url)
    try:
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
    finally:
        connection.close()


def _ensure_pgvector_extension(database_url: str) -> None:
    connection = psycopg2.connect(_psycopg2_url(database_url))
    try:
        connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        connection.close()


def _run_migrations(database_url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def main() -> int:
    try:
        if not _env_flag("POSTGRES_SKIP_CREATE_DB"):
            _ensure_database_exists(DATABASE_URL)
        _ensure_pgvector_extension(DATABASE_URL)
        _run_migrations(DATABASE_URL)
        init_db()
        health = database_health()
    except Exception as exc:
        print(f"PostgreSQL bootstrap failed: {exc}")
        print(
            "Make sure the PostgreSQL server is running, the target database exists, "
            "and the pgvector extension is available to the server."
        )
        print("If you created the database manually in pgAdmin, rerun with POSTGRES_SKIP_CREATE_DB=1.")
        return 1

    if not health.get("ok"):
        print("PostgreSQL bootstrap completed, but health is still failing:")
        print(health)
        return 1

    print("PostgreSQL bootstrap completed successfully.")
    print(health)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
