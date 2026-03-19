import os

from app.database.connection import database_health, init_db
from app.rag.embeddings import create_embedding


def main() -> None:
    print("DATABASE_URL =", os.getenv("DATABASE_URL"))
    init_db()
    health = database_health()
    print("health =", health)
    vector = create_embedding("python fastapi postgres")
    print("embedding_dim =", len(vector))


if __name__ == "__main__":
    main()
