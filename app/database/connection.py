import os
import sqlite3
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.database.vector import PGVECTOR_INSTALLED


load_dotenv()

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/tender_rag",
)

Base = declarative_base()


def _is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def _is_postgres(database_url: str) -> bool:
    return database_url.startswith("postgresql")


def _build_connect_args(database_url: str) -> dict:
    if _is_sqlite(database_url):
        return {"check_same_thread": False}
    return {}


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
                dimension = connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).scalar()
                if dimension != "vector":
                    raise RuntimeError("pgvector extension is not enabled in the configured PostgreSQL database.")
            except Exception as exc:
                raise RuntimeError(
                    "PostgreSQL is reachable but pgvector is unavailable. "
                    "Install/enable the extension before starting the app."
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
            connection.execute(text(statement))


def init_db() -> None:
    from app.models import db_models  # noqa: F401

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

        return {
            "ok": extension_ok,
            "database_url": DATABASE_URL,
            "database_backend": "postgresql" if _is_postgres(DATABASE_URL) else "sqlite",
            "pgvector_enabled": extension_ok if _is_postgres(DATABASE_URL) else False,
            "pgvector_python_package": PGVECTOR_INSTALLED,
            "embedding_dim": EMBEDDING_DIM,
        }
    except Exception as exc:
        return {
            "ok": False,
            "database_url": DATABASE_URL,
            "database_backend": "postgresql" if _is_postgres(DATABASE_URL) else "sqlite",
            "pgvector_enabled": False,
            "pgvector_python_package": PGVECTOR_INSTALLED,
            "embedding_dim": EMBEDDING_DIM,
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
