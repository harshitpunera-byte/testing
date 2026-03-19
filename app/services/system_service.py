import os
import shutil

from app.database.connection import database_health, vacuum_sqlite_database
from app.services.document_repository import delete_all_documents


UPLOAD_DIRS = (
    "uploads/tenders",
    "uploads/resumes",
)

VECTOR_DIR = "vector_store"
PRESERVED_FILENAMES = {
    "__init__.py",
    ".gitkeep",
}


def _clear_directory(path: str, preserve_filenames: set[str] | None = None) -> int:
    if not os.path.isdir(path):
        return 0

    removed_entries = 0
    preserve_filenames = preserve_filenames or set()

    for entry in os.scandir(path):
        if entry.name in preserve_filenames:
            continue

        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
            removed_entries += 1
            continue

        os.remove(entry.path)
        removed_entries += 1

    return removed_entries


def clear_application_data() -> dict:
    deleted_rows = delete_all_documents()

    upload_entries_deleted = 0
    for path in UPLOAD_DIRS:
        upload_entries_deleted += _clear_directory(path, preserve_filenames=PRESERVED_FILENAMES)

    vector_entries_deleted = _clear_directory(VECTOR_DIR, preserve_filenames=PRESERVED_FILENAMES)
    database_compacted = vacuum_sqlite_database()

    return {
        "message": "Application database cleared successfully.",
        **deleted_rows,
        "upload_entries_deleted": upload_entries_deleted,
        "vector_entries_deleted": vector_entries_deleted,
        "database_compacted": database_compacted,
    }


def get_system_health() -> dict:
    health = database_health()
    health["uploads_dirs"] = list(UPLOAD_DIRS)
    return health
