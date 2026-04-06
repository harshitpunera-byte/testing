from __future__ import annotations
import os
from sqlalchemy.types import JSON, TypeDecorator

# Lazy loading to prevent startup hangs should pgvector be problematic on this environment
_PGVECTOR_CLASS = None
_PGVECTOR_PROBED = False

def _get_pgvector_class():
    global _PGVECTOR_CLASS, _PGVECTOR_PROBED
    if _PGVECTOR_PROBED:
        return _PGVECTOR_CLASS
    
    _PGVECTOR_PROBED = True
    # Probe for library
    try:
        from pgvector.sqlalchemy import Vector as PgVector
        _PGVECTOR_CLASS = PgVector
    except ImportError:
        _PGVECTOR_CLASS = None
    return _PGVECTOR_CLASS

class JsonVector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value, dialect):
        return value

def vector_column_type(dim: int):
    cls = _get_pgvector_class()
    if cls is not None:
        return cls(dim).with_variant(JSON(), "sqlite")
    return JsonVector()

# Keep this for compatibility but make it a property or check function if possible
# For now, let's just make it check once lazily
def is_pgvector_installed():
    return _get_pgvector_class() is not None

PGVECTOR_INSTALLED = is_pgvector_installed()
