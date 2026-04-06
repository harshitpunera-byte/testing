from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
from sqlalchemy import case, desc, func, literal, select

from app.database import connection as db_connection
from app.database.connection import _is_postgres, session_scope
from app.database.vector import PGVECTOR_INSTALLED
from app.models.db_models import Document, DocumentChunk, ResumeProfile, ResumeSearchIndex
from app.rag.embeddings import EMBEDDING_DIM, create_embedding, create_embeddings
from app.services.document_repository import get_index_chunks


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
RRF_K = 60


def _normalize_vector(vector: list[float] | np.ndarray) -> list[float]:
    array = np.asarray(vector, dtype="float32").reshape(-1)
    if array.shape[0] != EMBEDDING_DIM:
        raise ValueError(f"Embedding dimension mismatch. Expected {EMBEDDING_DIM}, received {array.shape[0]}.")
    return array.tolist()


def embed_text(text: str) -> np.ndarray:
    if not isinstance(text, str):
        raise TypeError("embed_text expects a string")
    return np.asarray(create_embedding(text), dtype="float32")


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, EMBEDDING_DIM), dtype="float32")
    return np.asarray(create_embeddings(texts), dtype="float32")


def index_has_data(index_name: str) -> bool:
    with session_scope() as db:
        count = db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.document_type == index_name, Document.processing_status == "stored")
        ) or 0
        return int(count) > 0


def invalidate_index(index_name: str) -> None:
    return None


def store_document_chunks(index_name: str, chunks: list[dict], filename: str = "unknown.pdf") -> int:
    clean_chunks = [chunk for chunk in chunks if str(chunk.get("text", "")).strip()]
    return len(clean_chunks)


def _chunk_row_to_result(row: Any) -> dict:
    chunk = row[0] if isinstance(row, tuple) else row
    original_filename = getattr(row, "original_file_name", None)
    document_type = getattr(row, "document_type", None)
    metadata = chunk.metadata_json or {}
    return {
        "filename": metadata.get("filename", original_filename),
        "text": chunk.content,
        "chunk_id": chunk.chunk_id,
        "chunk_index": chunk.chunk_index,
        "document_id": chunk.document_id,
        "document_type": metadata.get("document_type", document_type),
        "section": chunk.section_title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "embedding_backend": chunk.embedding_backend,
        "metadata_json": metadata,
    }


def _tokenize_for_search(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(str(text).lower())


def _keyword_score(query_text: str, chunk_text: str) -> float:
    query = str(query_text or "").strip().lower()
    text = str(chunk_text or "").strip().lower()
    if not query or not text:
        return 0.0

    query_tokens = set(_tokenize_for_search(query))
    text_tokens = set(_tokenize_for_search(text))
    if not query_tokens or not text_tokens:
        return 0.0

    overlap = query_tokens & text_tokens
    if not overlap:
        return 0.0

    score = len(overlap) / len(query_tokens)
    if query in text:
        score += 1.0
    return score


def _cosine_distance(a: np.ndarray, b: np.ndarray | list[float] | None) -> float:
    if b is None:
        return 1.0
    b_arr = np.asarray(b, dtype="float32")
    if b_arr.size == 0:
        return 1.0
    numerator = float(np.dot(a, b_arr))
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b_arr))
    if denominator == 0:
        return 1.0
    return 1.0 - (numerator / denominator)


def _semantic_search_postgres(index_name: str, query_vector: list[float], top_k: int, document_id: int | None = None) -> list[dict]:
    with session_scope() as db:
        distance_expr = DocumentChunk.embedding.cosine_distance(query_vector)
        statement = (
            select(DocumentChunk, Document.original_file_name, Document.document_type, distance_expr.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.document_type == index_name,
                Document.processing_status == "stored",
                DocumentChunk.embedding.is_not(None),
            )
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
            
        rows = db.execute(statement.order_by(distance_expr.asc()).limit(top_k)).all()

    results = []
    for chunk, original_file_name, document_type, distance in rows:
        item = _chunk_row_to_result((chunk,))
        item["filename"] = (chunk.metadata_json or {}).get("filename", original_file_name)
        item["document_type"] = (chunk.metadata_json or {}).get("document_type", document_type)
        item["distance"] = float(distance)
        results.append(item)
    return results


def _semantic_search_fallback(
    index_name: str,
    query_vector: np.ndarray,
    top_k: int,
    document_id: int | None = None,
) -> list[dict]:
    chunks = get_index_chunks(index_name, document_id=document_id)
    if not chunks:
        return []

    q_arr = np.asarray(query_vector, dtype="float32")
    q_norm = np.linalg.norm(q_arr)
    if q_norm == 0:
        q_norm = 1.0

    embeddings = []
    valid_chunks = []
    for chunk in chunks:
        emb = chunk.get("embedding")
        if emb is not None:
            # Defensive check: Ensure embedding length matches EMBEDDING_DIM
            if isinstance(emb, (list, np.ndarray)) and len(emb) == EMBEDDING_DIM:
                embeddings.append(emb)
                valid_chunks.append(dict(chunk))

    if not embeddings:
        return []

    emb_matrix = np.asarray(embeddings, dtype="float32")
    emb_norms = np.linalg.norm(emb_matrix, axis=1)
    
    # Avoid zero division
    emb_norms[emb_norms == 0] = 1.0

    dot_products = np.dot(emb_matrix, q_arr)
    distances = 1.0 - (dot_products / (emb_norms * q_norm))

    scored = []
    for i, dist in enumerate(distances):
        item = valid_chunks[i]
        item["distance"] = float(dist)
        scored.append(item)

    scored.sort(key=lambda item: item.get("distance", math.inf))
    return scored[:top_k]


def search_index(index_name: str, query_text: str, top_k: int = 3, document_id: int | None = None):
    if not query_text or not query_text.strip():
        return []

    query_vector = embed_text(query_text)
    if _is_postgres(db_connection.DATABASE_URL) and PGVECTOR_INSTALLED:
        return _semantic_search_postgres(index_name, _normalize_vector(query_vector), top_k, document_id=document_id)
    return _semantic_search_fallback(index_name, query_vector, top_k, document_id=document_id)


def search_index_hybrid(
    index_name: str,
    query_text: str,
    top_k: int = 6,
    semantic_multiplier: int = 4,
    lexical_multiplier: int = 8,
    document_id: int | None = None,
):
    if not query_text or not query_text.strip():
        return []

    semantic_limit = max(top_k, top_k * semantic_multiplier)
    semantic_results = search_index(index_name, query_text, top_k=semantic_limit, document_id=document_id)

    # Note: Keyword score is still global or handled later, 
    # but we ensure the base pool contains only relevant docs.
    chunks = get_index_chunks(index_name, document_id=document_id)
    lexical_scored = []
    for idx, item in enumerate(chunks):
        score = _keyword_score(query_text, item.get("text", ""))
        if score > 0:
            lexical_scored.append((score, idx, item))
    lexical_scored.sort(key=lambda entry: (entry[0], -len(str(entry[2].get("text", "")))), reverse=True)

    lexical_results = []
    for score, idx, item in lexical_scored[: max(top_k, top_k * lexical_multiplier)]:
        row = dict(item)
        row["keyword_score"] = float(score)
        row["index"] = idx
        lexical_results.append(row)

    fused_results: dict[tuple[Any, Any, Any], dict[str, Any]] = {}

    for rank, result in enumerate(semantic_results, start=1):
        key = (result.get("document_id"), result.get("filename"), result.get("chunk_id"))
        entry = fused_results.setdefault(key, dict(result))
        entry["semantic_rank"] = rank
        entry["retrieval_score"] = entry.get("retrieval_score", 0.0) + (1.0 / (RRF_K + rank))

    for rank, result in enumerate(lexical_results, start=1):
        key = (result.get("document_id"), result.get("filename"), result.get("chunk_id"))
        entry = fused_results.setdefault(key, dict(result))
        for field, value in result.items():
            entry.setdefault(field, value)
        entry["keyword_rank"] = rank
        entry["retrieval_score"] = entry.get("retrieval_score", 0.0) + (1.0 / (RRF_K + rank))

    ranked = sorted(
        fused_results.values(),
        key=lambda item: (
            item.get("retrieval_score", 0.0),
            item.get("keyword_score", 0.0),
            -item.get("distance", float("inf")),
        ),
        reverse=True,
    )
    return ranked[:top_k]


def get_document_chunks(
    index_name: str,
    filename: str | None = None,
    limit: int | None = None,
    document_id: int | None = None,
):
    with session_scope() as db:
        statement = (
            select(DocumentChunk, Document.original_file_name, Document.document_type)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.document_type == index_name)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
        elif filename is not None:
            statement = statement.where(Document.original_file_name == filename)
        else:
            return []

        if limit is not None:
            statement = statement.limit(limit)

        rows = db.execute(statement).all()
        return [
            {
                **_chunk_row_to_result((chunk,)),
                "filename": (chunk.metadata_json or {}).get("filename", original_file_name),
                "document_type": (chunk.metadata_json or {}).get("document_type", document_type),
            }
            for chunk, original_file_name, document_type in rows
        ]


def get_chunk_window(
    index_name: str,
    *,
    center_chunk_id: int | None,
    window: int = 1,
    filename: str | None = None,
    document_id: int | None = None,
) -> list[dict]:
    if center_chunk_id is None:
        return []

    lower_bound = center_chunk_id - max(0, window)
    upper_bound = center_chunk_id + max(0, window)

    with session_scope() as db:
        statement = (
            select(DocumentChunk, Document.original_file_name, Document.document_type)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.document_type == index_name,
                DocumentChunk.chunk_id >= lower_bound,
                DocumentChunk.chunk_id <= upper_bound,
            )
            .order_by(DocumentChunk.chunk_id.asc())
        )
        if document_id is not None:
            statement = statement.where(DocumentChunk.document_id == document_id)
        elif filename is not None:
            statement = statement.where(Document.original_file_name == filename)

        rows = db.execute(statement).all()
        return [
            {
                **_chunk_row_to_result((chunk,)),
                "filename": (chunk.metadata_json or {}).get("filename", original_file_name),
                "document_type": (chunk.metadata_json or {}).get("document_type", document_type),
            }
            for chunk, original_file_name, document_type in rows
        ]


def search_resume_profiles_semantic(query_text: str, top_k: int = 10, profile_ids: list[int] | None = None) -> list[dict]:
    query_embedding = embed_text(query_text)
    if _is_postgres(db_connection.DATABASE_URL) and PGVECTOR_INSTALLED:
        query_vector = _normalize_vector(query_embedding)
        with session_scope() as db:
            distance_expr = ResumeSearchIndex.summary_embedding.cosine_distance(query_vector)
            statement = (
                select(ResumeSearchIndex, ResumeProfile, Document, distance_expr.label("distance"))
                .join(ResumeProfile, ResumeProfile.id == ResumeSearchIndex.resume_profile_id)
                .join(Document, Document.id == ResumeProfile.document_id)
                .where(
                    Document.processing_status == "stored",
                    Document.document_type == "resume",
                    ResumeSearchIndex.summary_embedding.is_not(None),
                )
            )
            if profile_ids:
                statement = statement.where(ResumeProfile.id.in_(profile_ids))
            statement = statement.order_by(distance_expr.asc()).limit(top_k)
            rows = db.execute(statement).all()

        return [
            {
                "resume_profile_id": profile.id,
                "document_id": document.id,
                "candidate_name": profile.candidate_name,
                "normalized_title": profile.normalized_title,
                "skills": search_row.skills_normalized or [],
                "summary_text": search_row.summary_text,
                "review_status": document.review_status,
                "canonical_data_ready": document.canonical_data_ready,
                "uses_unreviewed_data": not document.canonical_data_ready,
                "distance": float(distance),
                "semantic_score": max(0.0, 1.0 - float(distance)),
            }
            for search_row, profile, document, distance in rows
        ]

    with session_scope() as db:
        statement = (
            select(ResumeSearchIndex, ResumeProfile, Document)
            .join(ResumeProfile, ResumeProfile.id == ResumeSearchIndex.resume_profile_id)
            .join(Document, Document.id == ResumeProfile.document_id)
            .where(Document.processing_status == "stored", Document.document_type == "resume")
        )
        if profile_ids:
            statement = statement.where(ResumeProfile.id.in_(profile_ids))
        rows = db.execute(statement).all()

    scored = []
    for search_row, profile, document in rows:
        distance = _cosine_distance(query_embedding, search_row.summary_embedding)
        scored.append(
            {
                "resume_profile_id": profile.id,
                "document_id": document.id,
                "candidate_name": profile.candidate_name,
                "normalized_title": profile.normalized_title,
                "skills": search_row.skills_normalized or [],
                "summary_text": search_row.summary_text,
                "review_status": document.review_status,
                "canonical_data_ready": document.canonical_data_ready,
                "uses_unreviewed_data": not document.canonical_data_ready,
                "distance": float(distance),
                "semantic_score": max(0.0, 1.0 - float(distance)),
            }
        )
    scored.sort(key=lambda item: item["distance"])
    return scored[:top_k]
