from app.database.connection import database_health


def test_database_health_shape():
    health = database_health()

    assert "ok" in health
    assert "database_backend" in health
    assert "embedding_dim" in health
