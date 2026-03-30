import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_DB_DIR = ROOT / ".pytest-data"
TEST_DB_PATH = TEST_DB_DIR / "test.db"

TEST_DB_DIR.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_sessionstart(session):
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    from app.database.connection import init_db

    init_db()


def pytest_sessionfinish(session, exitstatus):
    from app.database.connection import engine

    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
