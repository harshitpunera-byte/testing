from app.database.connection import database_health


def test_database_health_shape():
    health = database_health()

    assert "ok" in health
    assert "database_backend" in health
    assert "embedding_dim" in health
    assert "alembic_revision" in health
    assert "startup_migrations_enabled" in health
    assert "***" in health["database_url"] or health["database_backend"] == "sqlite"
