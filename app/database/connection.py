import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.database.vector import PGVECTOR_INSTALLED


load_dotenv()

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_postgres_url() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = quote_plus(os.getenv("POSTGRES_PASSWORD", "postgres"))
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "tender_rag")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def _default_sqlite_url() -> str:
    database_path = Path(os.getenv("SQLITE_DATABASE_PATH", PROJECT_ROOT / "data" / "tender_rag.db"))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path}"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _has_explicit_postgres_config() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
        )
    )


def _resolve_database_url() -> str:
    explicit_database_url = os.getenv("DATABASE_URL")
    if explicit_database_url:
        return explicit_database_url

    if _has_explicit_postgres_config():
        return _default_postgres_url()

    return _default_sqlite_url()


DATABASE_URL = _resolve_database_url()
print(f"DATABASE_URL: {DATABASE_URL}")

Base = declarative_base()


def _is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def _is_postgres(database_url: str) -> bool:
    return database_url.startswith("postgresql")


def _build_connect_args(database_url: str) -> dict:
    if _is_sqlite(database_url):
        return {"check_same_thread": False}
    return {}


def _configure_engine(database_url: str) -> None:
    global DATABASE_URL, engine, SessionLocal

    DATABASE_URL = database_url
    engine = create_engine(
        DATABASE_URL,
        connect_args=_build_connect_args(DATABASE_URL),
        future=True,
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


def _can_fallback_to_sqlite() -> bool:
    return os.getenv("ALLOW_SQLITE_FALLBACK") == "1"

    explicit_database_url = os.getenv("DATABASE_URL")
    if not explicit_database_url:
        return True

    if not _is_postgres(explicit_database_url):
        return False

    try:
        parsed_url = make_url(explicit_database_url)
    except Exception:
        return False

    return (parsed_url.host or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _switch_to_sqlite_fallback() -> None:
    fallback_url = _default_sqlite_url()
    if DATABASE_URL == fallback_url:
        return

    try:
        engine.dispose()
    except Exception:
        pass

    _configure_engine(fallback_url)


_configure_engine(DATABASE_URL)


def _masked_database_url(database_url: str) -> str:
    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return database_url


def _startup_migrations_enabled() -> bool:
    return _env_flag("RUN_ALEMBIC_MIGRATIONS_ON_STARTUP", False)


def get_applied_migration_revision() -> str | None:
    try:
        with engine.begin() as connection:
            if _is_sqlite(DATABASE_URL):
                table_name = connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
                ).scalar()
                if table_name != "alembic_version":
                    return None
            else:
                table_name = connection.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
                if table_name is None:
                    return None

            return connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    except Exception:
        return None


def run_database_migrations(target_revision: str = "head") -> str | None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, target_revision)
    engine.dispose()
    return get_applied_migration_revision()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def validate_database_or_raise() -> None:
    with engine.begin() as connection:
        connection.execute(text("SELECT 1"))
        if _is_postgres(DATABASE_URL):
            if not PGVECTOR_INSTALLED:
                raise RuntimeError(
                    "The Python package `pgvector` is not installed. "
                    "Install requirements.txt before starting the app."
                )
            try:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                
                # Verify that any existing vector columns match the EMBEDDING_DIM
                # This prevents "inhomogeneous embedding" errors at runtime.
                # Table: document_chunks, column: embedding
                result = connection.execute(text(
                    "SELECT atttypmod FROM pg_attribute "
                    "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
                )).scalar()
                
                if result is not None and result > 0 and result != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"CRITICAL: Database vector dimension mismatch. "
                        f"DB expects {result}, but app is configured for EMBEDDING_DIM={EMBEDDING_DIM}. "
                        f"You must either reset the database or update EMBEDDING_DIM in .env."
                    )
            except Exception as exc:
                if "mismatch" in str(exc):
                    raise
                raise RuntimeError(
                    "PostgreSQL is reachable but pgvector is unavailable or needs configuration. "
                    "Error: " + str(exc)
                ) from exc


def _ensure_postgres_indexes() -> None:
    if not _is_postgres(DATABASE_URL):
        return

    statements = [
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_ivfflat "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_summary_embedding_ivfflat "
        "ON resume_search_index USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_fulltext "
        "ON resume_search_index USING gin (to_tsvector('english', coalesce(summary_text, '')))",
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_skills_gin "
        "ON resume_search_index USING gin (skills_normalized)",
        "CREATE INDEX IF NOT EXISTS ix_resume_search_index_domains_gin "
        "ON resume_search_index USING gin (domains)",
        "CREATE INDEX IF NOT EXISTS ix_documents_metadata_gin "
        "ON documents USING gin (metadata_json)",
    ]

    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except Exception as exc:
                print(f"Warning: Could not create index: {exc}")


def init_db() -> None:
    from app.models import db_models  # noqa: F401

    if _is_postgres(DATABASE_URL) and _startup_migrations_enabled():
        run_database_migrations()

    validate_database_or_raise()

    Base.metadata.create_all(bind=engine)
    _ensure_postgres_indexes()



def database_health() -> dict:
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            extension_ok = True
            extension_name = None
            if _is_postgres(DATABASE_URL):
                extension_name = connection.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
                extension_ok = extension_name == "vector"

        alembic_revision = get_applied_migration_revision()
        return {
            "ok": extension_ok,
            "database_url": _masked_database_url(DATABASE_URL),
            "database_backend": "postgresql" if _is_postgres(DATABASE_URL) else "sqlite",
            "pgvector_enabled": extension_ok if _is_postgres(DATABASE_URL) else False,
            "pgvector_python_package": PGVECTOR_INSTALLED,
            "embedding_dim": EMBEDDING_DIM,
            "alembic_revision": alembic_revision,
            "startup_migrations_enabled": _startup_migrations_enabled(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "database_url": _masked_database_url(DATABASE_URL),
            "database_backend": "postgresql" if _is_postgres(DATABASE_URL) else "sqlite",
            "pgvector_enabled": False,
            "pgvector_python_package": PGVECTOR_INSTALLED,
            "embedding_dim": EMBEDDING_DIM,
            "alembic_revision": get_applied_migration_revision(),
            "startup_migrations_enabled": _startup_migrations_enabled(),
            "error": str(exc),
        }


def vacuum_sqlite_database() -> bool:
    if not _is_sqlite(DATABASE_URL) or not DATABASE_URL.startswith("sqlite:///"):
        return False

    database_path = DATABASE_URL.removeprefix("sqlite:///")
    if not database_path or database_path == ":memory:":
        return False

    database_path = os.path.abspath(database_path)
    if not os.path.exists(database_path):
        return False

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        connection.execute("VACUUM;")
        connection.commit()
    finally:
        connection.close()

    return True
