
import os
os.environ["DATABASE_URL"] = "sqlite:///tender_rag.db"

from app.database.connection import init_db

if __name__ == "__main__":
    print(f"Initializing database using: {os.environ['DATABASE_URL']}")
    init_db()
    print("Database initialized successfully.")
