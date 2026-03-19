from __future__ import annotations

from sqlalchemy.types import JSON, TypeDecorator


try:
    from pgvector.sqlalchemy import Vector as PgVector

    PGVECTOR_INSTALLED = True

    def vector_column_type(dim: int):
        return PgVector(dim).with_variant(JSON(), "sqlite")

except Exception:
    PGVECTOR_INSTALLED = False

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
        return JsonVector()
